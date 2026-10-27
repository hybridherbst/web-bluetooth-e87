<script lang="ts">
  import { onMount } from 'svelte'
  import BadgeDevices from './lib/BadgeDevices.svelte'
  import FormatGuide from './lib/FormatGuide.svelte'
  import { formatDuration, formatBytes } from '../lib/utils'
  import {
    MAX_UPLOAD_BYTES,
    E87_IMAGE_WIDTH,
    E87_IMAGE_HEIGHT,
    previewBitmapToJpeg,
    previewBitmapsToAvi,
    imageFileToPreviewBitmap,
    imagesToPreviewBitmaps,
    videoToPreviewBitmaps,
    type TransformSettings,
    type OutputFrameSize,
  } from '../lib/image-processing'
  import { parseAviFrames, readAviFps } from '../lib/avi-preview'
  import {
    connectE87,
    disconnectE87,
    writeFileE87,
    refreshBatteryE87,
    listSmallFilesE87,
    readSmallFileE87,
    deleteSmallFileE87,
    getTargetInfoE87,
    getTargetFeatureMapE87,
    getSysInfoE87,
    browseFilesE87,
    stopBrowseE87,
    getScreenInfoE87,
    type E87Connection,
    type UploadMode as DeviceUploadMode,
    type E87SmallFileEntry,
    type E87FileBrowseEntry,
  } from '../lib/e87-protocol'
  import { buildMjpgAvi } from '../avi-builder'
  import { canvasToBadgeJpeg } from '../lib/image-encoding'
  import type { PatternDef } from '../pattern-generators'
  import QRCode from 'qrcode'

  import AviPlayer from './lib/AviPlayer.svelte'
  import UploadProgress from './lib/UploadProgress.svelte'
  import ImageMode from './lib/ImageMode.svelte'
  import SequenceMode from './lib/SequenceMode.svelte'
  import VideoMode from './lib/VideoMode.svelte'
  import PatternMode from './lib/PatternMode.svelte'
  import LiveTransformCanvas from './lib/LiveTransformCanvas.svelte'
  import TextMode from './lib/TextMode.svelte'
  import { FASHION_PATTERNS, generateTextFrames, type TextSettings } from './studio-generators'
  import QrMode from './lib/QrMode.svelte'

  type UploadMode = DeviceUploadMode | 'text'
  type PreviewMode = 'live' | 'preview'
  type QrCellStyle = 'square' | 'round' | 'squircle'
  type QrOutsideMode = 'on' | 'off'
  type ScreenInfo = {
    width: number
    height: number
    pictureWidth: number
    pictureHeight: number
    memory: number
  }

  type SavedSettings = {
    textSettings?: TextSettings
    uploadMode?: UploadMode
    interChunkDelayMs?: number
    videoFps?: number
    sequenceFps?: number
    patternFrameCount?: number
    patternFps?: number
    qrUrl?: string
    qrDarkColor?: string
    qrLightColor?: string
    qrDotStyle?: QrCellStyle
    qrOutsideMode?: QrOutsideMode
    qrZoom?: number
    qrRotation?: number
    imageBackdropColor?: string
    imagePreviewMode?: PreviewMode
    sequencePreviewMode?: PreviewMode
    videoPreviewMode?: PreviewMode
    imageScale?: number
    imagePanX?: number
    imagePanY?: number
    sequenceScale?: number
    sequencePanX?: number
    sequencePanY?: number
    videoScale?: number
    videoPanX?: number
    videoPanY?: number
  }

  const SETTINGS_STORAGE_KEY = 'badgeWriterSettings.v2'

  function loadSettings(): SavedSettings {
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
      return raw ? JSON.parse(raw) as SavedSettings : {}
    } catch {
      return {}
    }
  }

  function pm(value: unknown, fallback: PreviewMode): PreviewMode {
    return value === 'live' || value === 'preview' ? value : fallback
  }

  function n(value: unknown, fallback: number): number {
    return typeof value === 'number' && Number.isFinite(value) ? value : fallback
  }

  function s(value: unknown, fallback: string): string {
    return typeof value === 'string' ? value : fallback
  }

  const saved = loadSettings()

  const debugMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('debug')

  let conn: E87Connection | null = $state(null)
  let isConnecting = $state(false)
  let isWriting = $state(false)
  let cancelRequested = $state(false)
  let interChunkDelayMs = $state(n(saved.interChunkDelayMs, 0))

  let helpDialog: HTMLDialogElement
  let activeBadge = $state<{ name: string; mac: string; id: string } | null>(null)
  let previewError = $state('')
  let textSettings = $state<TextSettings>(saved.textSettings ?? { text: 'Привет, мир!', size: 68, speed: 170, color: '#c0ee91', background: '#000000', font: 'sans', direction: 'left', glow: false })
  let lastTextSignature = ''
  let status = $state('Не подключён')
  let batteryLevel: number | null = $state(null)
  let batteryUpdatedAt = $state('')
  let screenWidth = $state<number | null>(null)
  let screenHeight = $state<number | null>(null)
  let pictureWidth = $state(E87_IMAGE_WIDTH)
  let pictureHeight = $state(E87_IMAGE_HEIGHT)

  let isDeviceOpsBusy = $state(false)
  let smallFiles: E87SmallFileEntry[] = $state([])
  let browseEntries: E87FileBrowseEntry[] = $state([])
  let selectedSmallFileKey = $state('')
  let smallFileReadText = $state('')
  let rcspInfoText = $state('')

  let logs: string[] = $state([])

  let uploadMode: UploadMode = $state((saved.uploadMode ?? 'image') as UploadMode)
  let selectedFile: File | null = $state(null)
  let selectedFiles: File[] = $state([])
  let previewUrl: string | null = $state(null)

  let videoFps = $state(n(saved.videoFps, 12))
  let sequenceFps = $state(n(saved.sequenceFps, 1))
  let videoTrimStart = $state(0)
  let videoTrimEnd = $state(0)
  let videoDuration = $state(0)
  let patternFrameCount = $state(n(saved.patternFrameCount, 90))
  let patternFps = $state(n(saved.patternFps, 15))
  let selectedPattern: PatternDef | null = $state(FASHION_PATTERNS[0])
  let qrUrl = $state(s(saved.qrUrl, 'https://example.com'))
  let qrDarkColor = $state(s(saved.qrDarkColor, '#111111'))
  let qrLightColor = $state(s(saved.qrLightColor, '#f5f7ff'))
  let qrDotStyle: QrCellStyle = $state((saved.qrDotStyle ?? 'round') as QrCellStyle)
  let qrOutsideMode: QrOutsideMode = $state((saved.qrOutsideMode ?? 'on') as QrOutsideMode)
  let qrZoom = $state(n(saved.qrZoom, 1.08))
  let qrRotation = $state(Math.round(n(saved.qrRotation, 0) / 45) * 45)
  let imageBackdropColor = $state(s(saved.imageBackdropColor, '#000000'))

  let aviPreviewFrames: ImageBitmap[] = $state([])
  let aviPreviewFps = $state(12)
  let isGeneratingPreview = $state(false)
  let isGeneratingQr = $state(false)
  let isGeneratingPattern = $state(false)
  let preparedPayload: Uint8Array | null = $state(null)
  let preparedPayloadLabel = $state('')
  let preparedIsStillImage = $state(false)
  let aviPlayer: AviPlayer | null = $state(null)

  let imagePreviewMode: PreviewMode = $state(pm(saved.imagePreviewMode, 'live'))
  let sequencePreviewMode: PreviewMode = $state(pm(saved.sequencePreviewMode, 'live'))
  let videoPreviewMode: PreviewMode = $state(pm(saved.videoPreviewMode, 'live'))

  let imageLiveFrames: ImageBitmap[] = $state([])
  let sequenceLiveFrames: ImageBitmap[] = $state([])
  let videoLiveFrames: ImageBitmap[] = $state([])

  let imageScale = $state(n(saved.imageScale, 1))
  let imagePanX = $state(n(saved.imagePanX, 0))
  let imagePanY = $state(n(saved.imagePanY, 0))
  let sequenceScale = $state(n(saved.sequenceScale, 1))
  let sequencePanX = $state(n(saved.sequencePanX, 0))
  let sequencePanY = $state(n(saved.sequencePanY, 0))
  let videoScale = $state(n(saved.videoScale, 1))
  let videoPanX = $state(n(saved.videoPanX, 0))
  let videoPanY = $state(n(saved.videoPanY, 0))

  let videoCacheSignature = $state('')
  let autoPreviewSignature = $state('')
  let qrAutoSignature = $state('')

  let videoScrubFrame: ImageBitmap | null = $state(null)
  let isVideoScrubbing = $state(false)
  let videoScrubUrl: string | null = $state(null)
  let videoScrubElement: HTMLVideoElement | null = $state(null)
  let videoScrubRequestId = $state(0)

  let progress = $state(0)
  let progressLabel = $state('')
  let uploadStartTime = $state(0)
  let sentBytesForEta = $state(0)
  let totalBytesForEta = $state(0)

  onMount(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (isWriting) { event.preventDefault(); event.returnValue = '' }
    }
    window.addEventListener('beforeunload', beforeUnload)
    const stop = window.e87Desktop?.onCloseBlocked(() => { status = 'Идёт передача. Дождитесь завершения или нажмите «Остановить».' })
    return () => { window.removeEventListener('beforeunload', beforeUnload); void stop?.then(fn => fn()) }
  })

  // ─── Logging ───

  function log(message: string): void {
    const ts = new Date().toLocaleTimeString()
    logs = [`[${ts}] ${message}`, ...logs].slice(0, 250)
  }

  function applyScreenInfo(info: ScreenInfo | null): void {
    if (!info) return
    screenWidth = info.width
    screenHeight = info.height
    const hasScreenSize = Number.isFinite(info.width) && info.width > 0 && Number.isFinite(info.height) && info.height > 0
    const hasPictureSize = Number.isFinite(info.pictureWidth) && info.pictureWidth > 0 && Number.isFinite(info.pictureHeight) && info.pictureHeight > 0

    if (hasScreenSize) {
      pictureWidth = Math.max(1, Math.round(info.width))
      pictureHeight = Math.max(1, Math.round(info.height))
      log(`Output frame size set to ${pictureWidth}x${pictureHeight} (from screen size; picture=${info.pictureWidth}x${info.pictureHeight}).`)
      return
    }

    if (hasPictureSize) {
      pictureWidth = Math.max(1, Math.round(info.pictureWidth))
      pictureHeight = Math.max(1, Math.round(info.pictureHeight))
      log(`Output frame size set to ${pictureWidth}x${pictureHeight} (from picture size).`)
    }
  }

  function getOutputFrameSize(): OutputFrameSize {
    return {
      width: pictureWidth,
      height: pictureHeight,
    }
  }

  async function resizeJpegToOutput(jpegBytes: Uint8Array, output: OutputFrameSize): Promise<Uint8Array> {
    if (output.width === 368 && output.height === 368) return jpegBytes
    const blob = new Blob([new Uint8Array(jpegBytes)], { type: 'image/jpeg' })
    const bitmap = await createImageBitmap(blob)
    try {
      const canvas = new OffscreenCanvas(output.width, output.height)
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('Could not create 2D canvas context.')
      ctx.fillStyle = 'black'
      ctx.fillRect(0, 0, output.width, output.height)
      ctx.drawImage(bitmap, 0, 0, output.width, output.height)
      return canvasToBadgeJpeg(canvas, 0.9)
    } finally {
      bitmap.close()
    }
  }

  async function normalizePatternFramesForOutput(frames: Uint8Array[]): Promise<Uint8Array[]> {
    const output = getOutputFrameSize()
    if (output.width === 368 && output.height === 368) return frames
    const resized: Uint8Array[] = []
    for (let i = 0; i < frames.length; i++) {
      resized.push(await resizeJpegToOutput(frames[i], output))
    }
    return resized
  }

  // ─── Connection ───

  async function connect(): Promise<void> {
    if (!('bluetooth' in navigator)) {
      status = 'Bluetooth недоступен в этой системе.'
      log(status)
      return
    }
    isConnecting = true
    try {
      status = 'Выберите значок в окне подключения…'
      const nextConn = await connectE87(log)
      batteryLevel = nextConn.batteryLevel
      batteryUpdatedAt = nextConn.batteryUpdatedAt
      // Auto-read screen info
      try {
        const info = await getScreenInfoE87(nextConn, log)
        applyScreenInfo(info)
      } catch { /* best effort */ }
      conn = nextConn
      nextConn.device.addEventListener('gattserverdisconnected', () => {
        if (conn !== nextConn) return
        conn = null
        batteryLevel = null
        status = 'Связь со значком потеряна. Подключитесь снова.'
      }, { once: true })
      status = `Подключён · ${nextConn.device.name ?? 'E87'}`
    } catch (error) {
      status = (error as Error).message.includes('User cancelled') ? 'Не подключён' : `Не удалось подключиться: ${(error as Error).message}`
      log(status)
      conn = null
      batteryLevel = null
      batteryUpdatedAt = ''
    } finally {
      isConnecting = false
    }
  }

  async function disconnect(): Promise<void> {
    cancelRequested = true
    if (conn) {
      await disconnectE87(conn, log)
      conn = null
    }
    batteryLevel = null
    batteryUpdatedAt = ''
    screenWidth = null
    screenHeight = null
    pictureWidth = E87_IMAGE_WIDTH
    pictureHeight = E87_IMAGE_HEIGHT
    status = 'Не подключён'
    progress = 0
    progressLabel = ''
    smallFiles = []
    browseEntries = []
    selectedSmallFileKey = ''
    smallFileReadText = ''
    log('Disconnected.')
  }

  // ─── Device utility actions ───

  function smallFileKey(file: E87SmallFileEntry): string {
    return `${file.type}:${file.id}`
  }

  function getSelectedSmallFile(): E87SmallFileEntry | null {
    if (!selectedSmallFileKey) return null
    return smallFiles.find((f) => smallFileKey(f) === selectedSmallFileKey) ?? null
  }

  async function refreshBattery(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    try {
      const result = await refreshBatteryE87(conn, log)
      batteryLevel = result.level
      batteryUpdatedAt = result.updatedAt
      if (result.level === null) {
        status = 'Battery service unavailable on this device.'
      }
    } catch (error) {
      status = `Battery read failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function listSmallFiles(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    smallFileReadText = ''
    try {
      const items = await listSmallFilesE87(conn, log)
      smallFiles = items
      if (items.length === 0) {
        status = 'No small files reported by device.'
        selectedSmallFileKey = ''
      } else {
        status = `Found ${items.length} small file(s).`
        if (!getSelectedSmallFile()) {
          selectedSmallFileKey = smallFileKey(items[0])
        }
      }
    } catch (error) {
      status = `List files failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function browseFiles(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    try {
      // Try files first, then folders if empty
      let results = await browseFilesE87(conn, log, { type: 1, readNum: 50 })
      if (results.length === 0) {
        results = await browseFilesE87(conn, log, { type: 0, readNum: 50 })
      }
      browseEntries = results
      const total = results.length
      rcspInfoText = JSON.stringify({
        command: 'FileBrowseCmd',
        totalEntries: total,
        entries: results,
      }, null, 2)
      status = total > 0 ? `FileBrowse: found ${total} entries.` : 'FileBrowse: no entries found on any storage.'
    } catch (error) {
      status = `FileBrowse failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function queryScreenInfo(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    try {
      const info = await getScreenInfoE87(conn, log)
      applyScreenInfo(info)
      rcspInfoText = JSON.stringify({
        command: 'GetScreenInfoCmd',
        info,
      }, null, 2)
      status = info ? `Screen: ${info.width}x${info.height} (pic ${info.pictureWidth}x${info.pictureHeight})` : 'ScreenInfo: no response.'
    } catch (error) {
      status = `ScreenInfo failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function readSelectedSmallFile(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    const item = getSelectedSmallFile()
    if (!item) {
      status = 'No file selected.'
      return
    }

    isDeviceOpsBusy = true
    try {
      const { data, crc16 } = await readSmallFileE87(conn, item, log)
      const asText = new TextDecoder().decode(data)
      const crcInfo = crc16 === null ? 'n/a' : `0x${crc16.toString(16).padStart(4, '0')}`
      smallFileReadText = `type=${item.typeName} id=${item.id} size=${data.length} crc=${crcInfo}\n\n${asText}`
      status = `Read ${data.length} byte(s) from ${item.typeName}#${item.id}.`
    } catch (error) {
      status = `Read file failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function deleteSelectedSmallFile(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    const item = getSelectedSmallFile()
    if (!item) {
      status = 'No file selected.'
      return
    }

    isDeviceOpsBusy = true
    try {
      await deleteSmallFileE87(conn, item, log)
      const removedKey = smallFileKey(item)
      smallFiles = smallFiles.filter((f) => smallFileKey(f) !== removedKey)
      selectedSmallFileKey = smallFiles.length ? smallFileKey(smallFiles[0]) : ''
      smallFileReadText = ''
      status = `Deleted ${item.typeName}#${item.id}.`
    } catch (error) {
      status = `Delete file failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function getTargetFeatureMap(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    try {
      const res = await getTargetFeatureMapE87(conn, log)
      rcspInfoText = JSON.stringify({
        command: 'GetTargetFeatureMapCmd',
        maskHex: `0x${res.mask.toString(16).padStart(8, '0')}`,
        supported: res.mask !== 0,
        raw: res.raw,
      }, null, 2)
      status = res.mask !== 0
        ? `FeatureMap: 0x${res.mask.toString(16).padStart(8, '0')}`
        : 'FeatureMap: not supported by this device.'
    } catch (error) {
      status = `GetTargetFeatureMapCmd failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function getTargetInfo(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    try {
      const res = await getTargetInfoE87(conn, log)
      rcspInfoText = JSON.stringify({
        command: 'GetTargetInfoCmd',
        requestMaskHex: `0x${res.requestMask.toString(16)}`,
        requestPlatform: res.requestPlatform,
        attrs: res.attrs,
        payloadHex: res.payload,
        rawBodyHex: res.raw,
      }, null, 2)
      status = 'GetTargetInfoCmd completed.'
    } catch (error) {
      status = `GetTargetInfoCmd failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  async function getSysInfo(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    isDeviceOpsBusy = true
    try {
      const res = await getSysInfoE87(conn, log)
      const batteryAttr = res.attrs.find((a) => a.type === 0)
      const batteryGuess = batteryAttr?.decoded ?? batteryAttr?.dataHex ?? null
      rcspInfoText = JSON.stringify({
        command: 'GetSysInfoCmd',
        functionHex: `0x${res.function.toString(16)}`,
        batteryGuess,
        attrs: res.attrs,
        rawPayloadHex: res.raw,
      }, null, 2)
      if (batteryAttr?.decoded?.endsWith('%')) {
        const n = Number.parseInt(batteryAttr.decoded, 10)
        if (Number.isFinite(n)) {
          batteryLevel = n
          batteryUpdatedAt = new Date().toLocaleTimeString()
        }
      }
      status = 'GetSysInfoCmd completed.'
    } catch (error) {
      status = `GetSysInfoCmd failed: ${(error as Error).message}`
      log(status)
    } finally {
      isDeviceOpsBusy = false
    }
  }

  // ─── File handling ───

  function revokePreviewUrl() {
    if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
  }

  function clearFrames(frames: ImageBitmap[]): void {
    frames.forEach((frame) => frame.close())
  }

  function clearAviPreview(): void {
    aviPlayer?.stop()
    clearFrames(aviPreviewFrames)
    aviPreviewFrames = []
  }

  function clearPreparedState(): void {
    preparedPayload = null
    preparedPayloadLabel = ''
    preparedIsStillImage = false
  }

  function makeBlob(bytes: Uint8Array, type: string): Blob {
    return new Blob([new Uint8Array(bytes)], { type })
  }

  $effect(() => {
    if (typeof window === 'undefined') return
    const persist: SavedSettings = {
      uploadMode,
      textSettings,
      interChunkDelayMs,
      videoFps,
      sequenceFps,
      patternFrameCount,
      patternFps,
      qrUrl,
      qrDarkColor,
      qrLightColor,
      qrDotStyle,
      qrOutsideMode,
      qrZoom,
      qrRotation,
      imageBackdropColor,
      imagePreviewMode,
      sequencePreviewMode,
      videoPreviewMode,
      imageScale,
      imagePanX,
      imagePanY,
      sequenceScale,
      sequencePanX,
      sequencePanY,
      videoScale,
      videoPanX,
      videoPanY,
    }
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(persist))
  })

  function resetVideoScrubber(): void {
    videoScrubRequestId += 1
    if (videoScrubFrame) {
      videoScrubFrame.close()
      videoScrubFrame = null
    }
    if (videoScrubUrl) {
      URL.revokeObjectURL(videoScrubUrl)
      videoScrubUrl = null
    }
    videoScrubElement = null
    isVideoScrubbing = false
  }

  async function ensureVideoScrubber(): Promise<HTMLVideoElement> {
    if (videoScrubElement && videoScrubUrl) return videoScrubElement
    if (!selectedFile) throw new Error('No selected video for scrubbing.')

    videoScrubUrl = URL.createObjectURL(selectedFile)
    const video = document.createElement('video')
    video.muted = true
    video.playsInline = true
    video.preload = 'auto'
    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => reject(new Error('Could not initialize scrubber video.'))
      video.src = videoScrubUrl!
    })
    videoScrubElement = video
    return video
  }

  async function updateVideoScrubFrame(time: number): Promise<void> {
    const reqId = ++videoScrubRequestId
    if (!selectedFile) return

    try {
      const video = await ensureVideoScrubber()
      const t = Math.max(0, Math.min(videoDuration || video.duration || 0, time))
      video.currentTime = t
      await new Promise<void>((resolve) => { video.onseeked = () => resolve() })
      if (reqId !== videoScrubRequestId) return

      const size = 512
      const canvas = new OffscreenCanvas(size, size)
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const srcFullW = video.videoWidth
      const srcFullH = video.videoHeight
      const minDim = Math.min(srcFullW, srcFullH)
      const cropX = (srcFullW - minDim) / 2
      const cropY = (srcFullH - minDim) / 2

      ctx.fillStyle = 'black'
      ctx.fillRect(0, 0, size, size)
      ctx.drawImage(video, cropX, cropY, minDim, minDim, 0, 0, size, size)
      const bmp = await createImageBitmap(canvas)
      if (reqId !== videoScrubRequestId) {
        bmp.close()
        return
      }
      if (videoScrubFrame) videoScrubFrame.close()
      videoScrubFrame = bmp
    } catch (err) {
      log(`Scrub frame failed: ${(err as Error).message}`)
    }
  }

  function onVideoScrubStart(): void {
    isVideoScrubbing = true
  }

  function onVideoScrubFrame(time: number): void {
    updateVideoScrubFrame(time).catch((err) => log(`Scrub preview error: ${(err as Error).message}`))
  }

  function onVideoScrubEnd(): void {
    isVideoScrubbing = false
  }

  async function prepareImageLiveFrames(): Promise<void> {
    clearFrames(imageLiveFrames)
    imageLiveFrames = []
    if (!selectedFile) return
    imageLiveFrames = [await imageFileToPreviewBitmap(selectedFile)]
  }

  async function prepareSequenceLiveFrames(): Promise<void> {
    clearFrames(sequenceLiveFrames)
    sequenceLiveFrames = []
    if (selectedFiles.length === 0) return
    sequenceLiveFrames = await imagesToPreviewBitmaps(selectedFiles)
  }

  async function prepareVideoLiveFrames(): Promise<void> {
    clearFrames(videoLiveFrames)
    videoLiveFrames = []
    if (!selectedFile || videoDuration <= 0) return
    videoLiveFrames = await videoToPreviewBitmaps(selectedFile, {
      fps: videoFps,
      trimStart: videoTrimStart,
      trimEnd: videoTrimEnd,
    }, log)
  }

  async function setFile(event: Event): Promise<void> {
    resetVideoScrubber()
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    selectedFile = file
    clearPreparedState()
    clearAviPreview()
    revokePreviewUrl()
    previewUrl = null
    if (file) {
      log(`Selected: ${file.name}`)
      try { await prepareImageLiveFrames() } catch { status = 'Не удалось открыть картинку. Используйте PNG, JPG или WebP.'; selectedFile = null; log(status) }
    }
  }

  async function setMultipleFiles(event: Event): Promise<void> {
    resetVideoScrubber()
    const input = event.target as HTMLInputElement
    const files = input.files
    if (!files || files.length === 0) return
    selectedFiles = Array.from(files).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    clearPreparedState()
    clearAviPreview()
    revokePreviewUrl()
    previewUrl = null
    log(`Selected ${selectedFiles.length} images for sequence`)
    try { await prepareSequenceLiveFrames() } catch { status = 'Один из файлов не удалось открыть. Используйте PNG, JPG или WebP.'; selectedFiles = []; log(status) }
  }

  async function setVideoFile(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    resetVideoScrubber()
    selectedFile = file
    clearPreparedState()
    clearAviPreview()
    revokePreviewUrl()
    previewUrl = null
    videoTrimStart = 0
    videoTrimEnd = 0
    videoDuration = 0
    videoCacheSignature = ''

    clearFrames(videoLiveFrames)
    videoLiveFrames = []

    if (file) {
      log(`Selected video: ${file.name} (${formatBytes(file.size)})`)
      const v = document.createElement('video')
      try {
      v.preload = 'metadata'
      await new Promise<void>((resolve, reject) => {
        v.onloadedmetadata = () => {
          videoDuration = v.duration
          videoTrimEnd = Math.min(v.duration, 10)
          URL.revokeObjectURL(v.src)
          resolve()
        }
        v.onerror = () => reject(new Error('Failed to read video metadata'))
        v.src = URL.createObjectURL(file)
      })
      await prepareVideoLiveFrames()
      } catch {
        URL.revokeObjectURL(v.src)
        selectedFile = null
        videoDuration = 0
        status = 'Видео не открылось. Попробуйте MP4/H.264 или WebM/VP8.'
        log(status)
      }
    }
  }

  function selectPattern(pat: PatternDef): void {
    selectedPattern = pat
    clearPreparedState()
    clearAviPreview()
  }

  function switchMode(mode: UploadMode): void {
    uploadMode = mode
    previewError = ''
    if (mode === 'text') lastTextSignature = ''
    if (mode === 'qr') qrAutoSignature = ''
    clearAviPreview()
    clearPreparedState()
    revokePreviewUrl()
    previewUrl = null
    if (mode !== 'video') {
      isVideoScrubbing = false
    }
  }

  function getTransform(mode: UploadMode): TransformSettings {
    if (mode === 'image') return {
      scale: imageScale,
      panX: imagePanX,
      panY: imagePanY,
      backdropColor: imageBackdropColor,
    }
    if (mode === 'images') return { scale: sequenceScale, panX: sequencePanX, panY: sequencePanY }
    if (mode === 'video') return { scale: videoScale, panX: videoPanX, panY: videoPanY }
    return { scale: 1, panX: 0, panY: 0 }
  }

  $effect(() => {
    if (!selectedFile || videoDuration <= 0) return
    if (uploadMode !== 'video') return

    const signature = [
      selectedFile.name,
      selectedFile.size,
      selectedFile.lastModified,
      videoTrimStart.toFixed(2),
      videoTrimEnd.toFixed(2),
      videoFps,
    ].join('|')

    if (signature === videoCacheSignature) return
    const timeout = setTimeout(() => {
      videoCacheSignature = signature
      prepareVideoLiveFrames().catch((err) => log(`Video cache failed: ${(err as Error).message}`))
    }, 260)

    return () => clearTimeout(timeout)
  })

  $effect(() => {
    if (uploadMode !== 'qr' || isWriting || isGeneratingQr) return
    const targetUrl = qrUrl.trim()
    if (!targetUrl) return

    const signature = [
      targetUrl,
      qrDarkColor,
      qrLightColor,
      qrDotStyle,
      qrOutsideMode,
      qrZoom.toFixed(3),
      qrRotation.toFixed(1),
    ].join('|')
    if (signature === qrAutoSignature) return

    const timeout = setTimeout(() => {
      qrAutoSignature = signature
      generateQr()
    }, 120)

    return () => clearTimeout(timeout)
  })

  $effect(() => {
    return () => {
      resetVideoScrubber()
    }
  })

  $effect(() => {
    if (isWriting || isGeneratingPreview || uploadMode === 'pattern' || uploadMode === 'qr') return

    if (uploadMode === 'image' && imagePreviewMode === 'preview' && imageLiveFrames.length > 0 && selectedFile) {
      const signature = [
        'image',
        selectedFile.name,
        selectedFile.size,
        selectedFile.lastModified,
        imageScale.toFixed(3),
        imagePanX.toFixed(3),
        imagePanY.toFixed(3),
      ].join('|')
      if (signature === autoPreviewSignature) return
      const timeout = setTimeout(() => {
        autoPreviewSignature = signature
        generatePreview()
      }, 120)
      return () => clearTimeout(timeout)
    }

    if (uploadMode === 'images' && sequencePreviewMode === 'preview' && sequenceLiveFrames.length > 0) {
      const filesSig = selectedFiles.map((f) => `${f.name}:${f.size}:${f.lastModified}`).join(',')
      const signature = [
        'images',
        filesSig,
        sequenceFps,
        sequenceScale.toFixed(3),
        sequencePanX.toFixed(3),
        sequencePanY.toFixed(3),
      ].join('|')
      if (signature === autoPreviewSignature) return
      const timeout = setTimeout(() => {
        autoPreviewSignature = signature
        generatePreview()
      }, 180)
      return () => clearTimeout(timeout)
    }

    if (uploadMode === 'video' && videoPreviewMode === 'preview' && videoLiveFrames.length > 0 && selectedFile) {
      const signature = [
        'video',
        selectedFile.name,
        selectedFile.size,
        selectedFile.lastModified,
        videoTrimStart.toFixed(2),
        videoTrimEnd.toFixed(2),
        videoFps,
        videoScale.toFixed(3),
        videoPanX.toFixed(3),
        videoPanY.toFixed(3),
      ].join('|')
      if (signature === autoPreviewSignature) return
      const timeout = setTimeout(() => {
        autoPreviewSignature = signature
        generatePreview()
      }, 220)
      return () => clearTimeout(timeout)
    }
  })

  // ─── Pattern still-image generation ───

  async function generatePatternStill(): Promise<void> {
    if (!selectedPattern) return
    isGeneratingPattern = true
    isGeneratingPreview = true
    clearPreparedState()
    clearAviPreview()

    try {
      // Generate a handful of frames and pick one from the middle for a representative still
      const sampleFrames = Math.max(patternFrameCount, 30)
      const allFrames = await selectedPattern.generate({ frames: sampleFrames, fps: patternFps })
      // Pick a frame ~40% through — usually more visually interesting than exact center
      const pickIdx = Math.floor(sampleFrames * 0.4)
      const stillJpeg = await resizeJpegToOutput(allFrames[pickIdx], getOutputFrameSize())

      preparedPayload = stillJpeg
      preparedIsStillImage = true
      preparedPayloadLabel = `${selectedPattern.name} still — ${formatBytes(stillJpeg.length)}`

      // Show as preview image
      revokePreviewUrl()
      previewUrl = URL.createObjectURL(makeBlob(stillJpeg, 'image/jpeg'))
      log(`Still ready: ${selectedPattern.name} (frame ${pickIdx + 1}/${sampleFrames}), ${formatBytes(stillJpeg.length)}`)
    } catch (err) {
      log(`Still generation failed: ${(err as Error).message}`)
    } finally {
      isGeneratingPattern = false
      isGeneratingPreview = false
    }
  }

  function hashString(input: string): number {
    let hash = 2166136261
    for (let i = 0; i < input.length; i++) {
      hash ^= input.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
    return hash >>> 0
  }

  function createRng(seed: number): () => number {
    let t = seed >>> 0
    return () => {
      t += 0x6D2B79F5
      let r = Math.imul(t ^ (t >>> 15), t | 1)
      r ^= r + Math.imul(r ^ (r >>> 7), r | 61)
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296
    }
  }

  function drawStyledCell(
    ctx: OffscreenCanvasRenderingContext2D,
    x: number,
    y: number,
    size: number,
    style: QrCellStyle,
    color: string,
  ): void {
    ctx.fillStyle = color
    if (style === 'square') {
      ctx.fillRect(x, y, size, size)
      return
    }
    if (style === 'round') {
      const r = size / 2
      ctx.beginPath()
      ctx.arc(x + r, y + r, r, 0, Math.PI * 2)
      ctx.fill()
      return
    }

    const radius = size * 0.32
    ctx.beginPath()
    ctx.moveTo(x + radius, y)
    ctx.lineTo(x + size - radius, y)
    ctx.quadraticCurveTo(x + size, y, x + size, y + radius)
    ctx.lineTo(x + size, y + size - radius)
    ctx.quadraticCurveTo(x + size, y + size, x + size - radius, y + size)
    ctx.lineTo(x + radius, y + size)
    ctx.quadraticCurveTo(x, y + size, x, y + size - radius)
    ctx.lineTo(x, y + radius)
    ctx.quadraticCurveTo(x, y, x + radius, y)
    ctx.closePath()
    ctx.fill()
  }

  async function generateQrJpegBytes(): Promise<Uint8Array> {
    const targetUrl = qrUrl.trim()
    if (!targetUrl) throw new Error('Enter a URL for QR generation.')

    const qr = QRCode.create(targetUrl, { errorCorrectionLevel: 'M' })
    const moduleCount = qr.modules.size
    const output = getOutputFrameSize()
    const canvas = new OffscreenCanvas(output.width, output.height)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Could not create QR canvas context.')

    const qrCanvasBg = '#d8dbe4'
    ctx.fillStyle = qrCanvasBg
    ctx.fillRect(0, 0, output.width, output.height)

    const motif = Math.max(1, Math.floor(Math.min(output.width, output.height) * (332 / 368)))
    const quietModules = 2
    const outerBandModules = 10
    const totalGridModules = moduleCount + (quietModules + outerBandModules) * 2
    const modulePx = Math.max(1, Math.floor(motif / totalGridModules))
    const gridPx = modulePx * totalGridModules
    const qrPx = moduleCount * modulePx
    const quietPx = quietModules * modulePx

    const seed = hashString([
      targetUrl,
      qrDarkColor,
      qrLightColor,
      qrDotStyle,
      qrOutsideMode,
      qrZoom.toFixed(3),
      qrRotation.toFixed(1),
    ].join('|'))
    const rng = createRng(seed)

    ctx.save()
    ctx.translate(output.width / 2, output.height / 2)
    ctx.rotate((qrRotation * Math.PI) / 180)
    ctx.scale(qrZoom, qrZoom)

    // Center the integer-sized grid so module pitch is exact and derived from QR data.
    const gridOffset = -gridPx / 2

    const coreWithQuietModules = moduleCount + quietModules * 2
    const innerHalf = (coreWithQuietModules * modulePx) / 2
    const cellSize = modulePx * 0.9
    const cellInset = (modulePx - cellSize) / 2

    const center = totalGridModules / 2
    const outerStart = 0
    const outerEndExclusive = totalGridModules
    const coreStart = outerBandModules
    const coreEndExclusive = totalGridModules - outerBandModules
    const qrStart = outerBandModules + quietModules

    if (qrOutsideMode === 'on') {
      for (let row = outerStart; row < outerEndExclusive; row++) {
        for (let col = outerStart; col < outerEndExclusive; col++) {
          const inCore = row >= coreStart && row < coreEndExclusive && col >= coreStart && col < coreEndExclusive
          if (inCore) continue

          const x = gridOffset + col * modulePx
          const y = gridOffset + row * modulePx
          const color = rng() > 0.5 ? qrDarkColor : qrLightColor
          drawStyledCell(ctx, x + cellInset, y + cellInset, cellSize, qrDotStyle, color)
        }
      }
    }

    for (let row = 0; row < moduleCount; row++) {
      for (let col = 0; col < moduleCount; col++) {
        const isDark = qr.modules.get(row, col)
        const x = gridOffset + (qrStart + col) * modulePx
        const y = gridOffset + (qrStart + row) * modulePx
        const color = isDark ? qrDarkColor : qrLightColor
        drawStyledCell(ctx, x + cellInset, y + cellInset, cellSize, qrDotStyle, color)
      }
    }

    ctx.restore()

    return canvasToBadgeJpeg(canvas, 0.92)
  }

  async function generateQr(): Promise<void> {
    isGeneratingQr = true
    clearPreparedState()
    clearAviPreview()
    try {
      const jpeg = await generateQrJpegBytes()
      preparedPayload = jpeg
      preparedIsStillImage = true
      preparedPayloadLabel = `QR image — ${formatBytes(jpeg.length)}`
      revokePreviewUrl()
      previewUrl = URL.createObjectURL(makeBlob(jpeg, 'image/jpeg'))
    } catch {
      // Keep QR auto-regeneration silent to avoid log clutter.
    } finally {
      isGeneratingQr = false
    }
  }

  // ─── Preview generation ───

  async function generatePreview(): Promise<void> {
    previewError = ''
    isGeneratingPreview = true
    clearPreparedState()
    clearAviPreview()
    revokePreviewUrl()
    previewUrl = null

    try {
      let avi: Uint8Array
      let label: string

      if (uploadMode === 'image') {
        if (imageLiveFrames.length === 0) throw new Error('No image selected')
        const imageJpeg = await previewBitmapToJpeg(imageLiveFrames[0], getTransform('image'), getOutputFrameSize())
        preparedPayload = imageJpeg
        preparedIsStillImage = true
        preparedPayloadLabel = `Image preview — ${formatBytes(imageJpeg.length)}`
        previewUrl = URL.createObjectURL(makeBlob(imageJpeg, 'image/jpeg'))
        log(`Image preview ready: ${formatBytes(imageJpeg.length)}`)
        return
      }

      if (uploadMode === 'images') {
        if (sequenceLiveFrames.length === 0) throw new Error('No images selected')
        avi = await previewBitmapsToAvi(sequenceLiveFrames, sequenceFps, getTransform('images'), log, getOutputFrameSize())
        label = `${sequenceLiveFrames.length} cached images @ ${sequenceFps}fps`
      } else if (uploadMode === 'video') {
        if (videoLiveFrames.length === 0) throw new Error('No video selected')
        avi = await previewBitmapsToAvi(videoLiveFrames, videoFps, getTransform('video'), log, getOutputFrameSize())
        label = `Video ${videoTrimStart.toFixed(1)}s–${videoTrimEnd.toFixed(1)}s @ ${videoFps}fps`
      } else if (uploadMode === 'text') {
        const frames = await normalizePatternFramesForOutput(await generateTextFrames({ ...textSettings }))
        avi = buildMjpgAvi(frames, { fps: 15, ...getOutputFrameSize() })
        label = `Бегущая строка · ${(frames.length / 15).toFixed(1)} с`
      } else if (uploadMode === 'pattern') {
        if (!selectedPattern) throw new Error('No pattern selected')
        isGeneratingPattern = true
        const patternFramesRaw = await selectedPattern.generate({ frames: patternFrameCount, fps: patternFps })
        const patternFrames = await normalizePatternFramesForOutput(patternFramesRaw)
        avi = buildMjpgAvi(patternFrames, { fps: patternFps, ...getOutputFrameSize() })
        label = `${selectedPattern.name} · ${(patternFrameCount / patternFps).toFixed(1)} с`
        isGeneratingPattern = false
      } else {
        throw new Error('Preview only for sequence/video/pattern modes')
      }

      if (avi.length > MAX_UPLOAD_BYTES) {
        log(`⚠️ Generated AVI is ${formatBytes(avi.length)} — exceeds ${formatBytes(MAX_UPLOAD_BYTES)} limit!`)
      }

      aviPreviewFps = readAviFps(avi)
      aviPreviewFrames = await parseAviFrames(avi)
      preparedPayload = avi
      preparedPayloadLabel = `${label} — ${formatBytes(avi.length)}`
      log(`Preview ready: ${aviPreviewFrames.length} frames @ ${aviPreviewFps}fps, ${formatBytes(avi.length)}`)

      // Let component mount, then start playback
      requestAnimationFrame(() => aviPlayer?.startPreview())
    } catch (err) {
      previewError = (err as Error).message
      log(`Preview failed: ${previewError}`)
    } finally {
      isGeneratingPreview = false
      isGeneratingPattern = false
    }
  }

  $effect(() => {
    if (uploadMode !== 'text' || isWriting || isGeneratingPreview) return
    const signature = JSON.stringify(textSettings) + `:${pictureWidth}:${pictureHeight}`
    if (signature === lastTextSignature) return
    clearPreparedState()
    const timer = setTimeout(() => {
      lastTextSignature = signature
      void generatePreview()
    }, 450)
    return () => clearTimeout(timer)
  })

  let busy = $derived(isWriting || isGeneratingPreview || isGeneratingPattern || isGeneratingQr)
  let hasContent = $derived(uploadMode === 'image' ? imageLiveFrames.length > 0 : uploadMode === 'images' ? sequenceLiveFrames.length > 0 : uploadMode === 'video' ? videoLiveFrames.length > 0 : !!preparedPayload)

  // ─── Get upload bytes ───

  async function getUploadBytes(): Promise<Uint8Array> {
    if (preparedPayload && ['pattern', 'text', 'qr'].includes(uploadMode)) {
      log(`Using prepared payload: ${formatBytes(preparedPayload.length)}`)
      return preparedPayload
    }

    if (uploadMode === 'image') {
      if (imageLiveFrames.length === 0 && selectedFile) await prepareImageLiveFrames()
      if (imageLiveFrames.length === 0) throw new Error('No image selected.')
      return previewBitmapToJpeg(imageLiveFrames[0], getTransform('image'), getOutputFrameSize())
    }
    if (uploadMode === 'images') {
      if (sequenceLiveFrames.length === 0 && selectedFiles.length > 0) await prepareSequenceLiveFrames()
      if (sequenceLiveFrames.length === 0) throw new Error('No sequence selected.')
      return previewBitmapsToAvi(sequenceLiveFrames, sequenceFps, getTransform('images'), log, getOutputFrameSize())
    }
    if (uploadMode === 'video') {
      if (videoLiveFrames.length === 0 && selectedFile) await prepareVideoLiveFrames()
      if (videoLiveFrames.length === 0) throw new Error('No video frames cached.')
      return previewBitmapsToAvi(videoLiveFrames, videoFps, getTransform('video'), log, getOutputFrameSize())
    }
    if (uploadMode === 'text') {
      const frames = await normalizePatternFramesForOutput(await generateTextFrames({ ...textSettings }))
      return buildMjpgAvi(frames, { fps: 15, ...getOutputFrameSize() })
    }
    if (uploadMode === 'pattern') {
      if (!selectedPattern) throw new Error('No pattern selected.')
      const patternFramesRaw = await selectedPattern.generate({ frames: patternFrameCount, fps: patternFps })
      const patternFrames = await normalizePatternFramesForOutput(patternFramesRaw)
      return buildMjpgAvi(patternFrames, { fps: patternFps, ...getOutputFrameSize() })
    }
    if (uploadMode === 'qr') {
      return generateQrJpegBytes()
    }
    throw new Error(`Unknown upload mode: ${uploadMode}`)
  }

  function resolveUploadModeForDevice(): DeviceUploadMode {
    if (uploadMode === 'text') return 'video'
    if (uploadMode === 'qr') return 'image'
    if (preparedIsStillImage) return 'image'
    return uploadMode
  }

  async function downloadGenerated(): Promise<void> {
    try {
      const payload = await getUploadBytes()
      const deviceMode = resolveUploadModeForDevice()
      const ext = deviceMode === 'image' ? 'jpg' : 'avi'
      if (window.e87Desktop) {
        if (await window.e87Desktop.savePayload(payload, ext)) log(`Saved ${ext.toUpperCase()} (${formatBytes(payload.length)})`)
        return
      }
      const mime = deviceMode === 'image' ? 'image/jpeg' : 'video/x-msvideo'
      const blob = makeBlob(payload, mime)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `badge-${uploadMode}-${Date.now()}.${ext}`
      link.click()
      URL.revokeObjectURL(url)
      log(`Downloaded generated ${ext.toUpperCase()} (${formatBytes(payload.length)})`)
    } catch (err) {
      previewError = (err as Error).message
      log(`Download failed: ${previewError}`)
    }
  }

  // ─── Upload orchestration ───

  async function startUpload(): Promise<void> {
    if (!conn) {
      status = 'Сначала подключите значок.'
      return
    }
    if (uploadMode === 'image' && !selectedFile && !preparedPayload) {
      status = 'Выберите изображение.'
      return
    }
    if (uploadMode === 'images' && selectedFiles.length === 0) {
      status = 'Выберите кадры для слайд-шоу.'
      return
    }
    if (uploadMode === 'video' && !selectedFile) {
      status = 'Выберите видео.'
      return
    }
    if (uploadMode === 'pattern' && !selectedPattern) {
      status = 'Выберите эффект.'
      return
    }
    if (uploadMode === 'qr' && !qrUrl.trim()) {
      status = 'Введите ссылку для QR-кода.'
      return
    }

    await window.e87Desktop?.setTransferActive(true)
    isWriting = true
    cancelRequested = false
    progress = 0
    progressLabel = 'Starting...'
    sentBytesForEta = 0
    totalBytesForEta = 0
    uploadStartTime = 0

    try {
      aviPlayer?.stop()
      const payload = await getUploadBytes()
      const uploadModeForDevice = resolveUploadModeForDevice()

      if (payload.length > MAX_UPLOAD_BYTES) {
        throw new Error(`File too large: ${formatBytes(payload.length)} exceeds ${formatBytes(MAX_UPLOAD_BYTES)} limit.`)
      }

      if (uploadModeForDevice === 'image') {
        revokePreviewUrl()
        previewUrl = URL.createObjectURL(makeBlob(payload, 'image/jpeg'))
      }

      uploadStartTime = Date.now()
      totalBytesForEta = payload.length

      await writeFileE87({
        conn: conn!,
        payload,
        uploadMode: uploadModeForDevice,
        interChunkDelayMs,
        cancelRequested: () => cancelRequested,
        onProgress: (bytesSent, totalBytes, chunksSent, totalChunks) => {
          sentBytesForEta = bytesSent
          const pct = Math.min(100, Math.round((bytesSent / totalBytes) * 100))
          progress = pct
          progressLabel = `${pct}% — ${formatBytes(bytesSent)} / ${formatBytes(totalBytes)} — chunk ${chunksSent}/${totalChunks}`
        },
        log,
      })

      progress = 100
      const elapsed = formatDuration((Date.now() - uploadStartTime) / 1000)
      status = `Готово! Значок получил файл за ${elapsed}.`
    } catch (error) {
      status = `Ошибка передачи: ${(error as Error).message}`
      log(status)
    } finally {
      isWriting = false
      await window.e87Desktop?.setTransferActive(false)
    }
  }

  function cancelWrite(): void {
    cancelRequested = true
    log('Cancel requested.')
  }
</script>

<main class="app">
  <header class="app-header">
    <div class="brand"><span class="brand-mark"><span></span></span><h1>E87 <span>Studio</span></h1></div>
    <div class="header-actions">
      {#if conn}<div class="connected-label"><strong>{activeBadge?.name || conn.device.name}</strong><code>{activeBadge?.mac || 'MAC скрыт ОС'}{batteryLevel !== null ? ` · ${batteryLevel}%` : ''}</code></div>{/if}
      <BadgeDevices connected={!!conn} onSelect={(profile) => activeBadge = profile} />
      {#if conn}<button class="quiet-button" onclick={disconnect} disabled={busy}>Отключить</button>
      {:else}<button class="primary connect-button" onclick={connect} disabled={isConnecting || busy}>{isConnecting ? 'Поиск…' : 'Подключить'}</button>{/if}
      <button class="help-button" title="Подключение и форматы файлов" aria-label="Справка" onclick={() => helpDialog.showModal()}>?</button>
    </div>
  </header>
  <nav class="mode-tabs" aria-label="Тип контента">
    {#each [{id:'image',label:'Картинка'},{id:'text',label:'Бегущая строка'},{id:'pattern',label:'Эффекты'},{id:'images',label:'Слайд-шоу'},{id:'video',label:'Видео'},{id:'qr',label:'QR-код'}] as mode}
      <button class:active={uploadMode === mode.id} aria-pressed={uploadMode === mode.id} onclick={() => switchMode(mode.id as UploadMode)} disabled={busy}>{mode.label}</button>
    {/each}
  </nav>
  <div class="content-area">
    <section class="control-pane" aria-label="Настройки контента">
      {#if uploadMode === 'pattern'}
        <PatternMode outputKey={`${pictureWidth}:${pictureHeight}`} isWriting={isWriting} {isGeneratingPreview} {isGeneratingPattern} {selectedPattern} bind:patternFrameCount bind:patternFps onSelectPattern={selectPattern} onGeneratePreview={generatePreview} onGenerateStill={generatePatternStill} />
      {:else if uploadMode === 'text'}
        <TextMode bind:settings={textSettings} disabled={busy} />
      {:else if uploadMode === 'image'}
        <ImageMode isWriting={busy} {selectedFile} bind:backdropColor={imageBackdropColor} onSelectFile={setFile} />
        <p class="format-hint">PNG · JPG · WebP · BMP</p>
      {:else if uploadMode === 'images'}
        <SequenceMode isWriting={busy} {selectedFiles} bind:sequenceFps onSelectFiles={setMultipleFiles} />
        <p class="format-hint">Кадры идут по имени файла: 01, 02, 03…</p>
      {:else if uploadMode === 'video'}
        <VideoMode isWriting={busy} {selectedFile} bind:videoFps bind:videoTrimStart bind:videoTrimEnd {videoDuration} onSelectVideo={setVideoFile} onScrubStart={onVideoScrubStart} onScrubFrame={onVideoScrubFrame} onScrubEnd={onVideoScrubEnd} />
        <p class="format-hint">MP4 / H.264 · WebM · до 10 секунд</p>
      {:else if uploadMode === 'qr'}
        <QrMode isWriting={busy} bind:qrUrl bind:qrDarkColor bind:qrLightColor bind:qrDotStyle bind:qrOutsideMode bind:qrZoom bind:qrRotation />
      {/if}
    </section>
    <section class="preview-stage" aria-label="Предпросмотр значка">
      {#if uploadMode === 'image' && imageLiveFrames.length > 0}
        <LiveTransformCanvas frames={imageLiveFrames} fps={1} backdropColor={imageBackdropColor} bind:scale={imageScale} bind:panX={imagePanX} bind:panY={imagePanY} disabled={busy} />
      {:else if uploadMode === 'images' && sequenceLiveFrames.length > 0}
        <LiveTransformCanvas frames={sequenceLiveFrames} fps={sequenceFps} bind:scale={sequenceScale} bind:panX={sequencePanX} bind:panY={sequencePanY} disabled={busy} />
      {:else if uploadMode === 'video' && videoLiveFrames.length > 0}
        <LiveTransformCanvas frames={videoScrubFrame && isVideoScrubbing ? [videoScrubFrame] : videoLiveFrames} fps={videoFps} bind:scale={videoScale} bind:panX={videoPanX} bind:panY={videoPanY} disabled={busy} />
      {:else if (uploadMode === 'pattern' || uploadMode === 'text') && aviPreviewFrames.length > 0}
        <AviPlayer bind:this={aviPlayer} frames={aviPreviewFrames} fps={aviPreviewFps} />
      {:else if previewUrl && (uploadMode === 'qr' || uploadMode === 'pattern')}
        <img class="still-preview" src={previewUrl} alt="Предпросмотр на круглом значке" />
      {:else}
        <div class="empty-badge"><span>✳</span></div>
      {/if}
      <div class="preview-caption">{busy && !isWriting ? 'Создаём…' : `${pictureWidth} × ${pictureHeight}`}{preparedPayload && !busy ? ` · ${formatBytes(preparedPayload.length)}` : ''}</div>
      {#if ['image', 'images', 'video'].includes(uploadMode) && hasContent}<p class="format-hint">Мышь — сдвиг · колесо — масштаб</p>{/if}
    </section>
  </div>
  {#if previewError}<p class="form-error" role="alert">{previewError}</p>{/if}
  {#if preparedPayload && preparedPayload.length > MAX_UPLOAD_BYTES}<p class="form-error" role="alert">Файл больше 2 МБ. Уменьшите длительность или частоту кадров.</p>{/if}
  <footer class="upload-actions">
    <div class="status" role="status">{status === 'Не подключён' ? '' : status}</div>
    {#if isWriting}<button class="quiet-button" onclick={cancelWrite}>Остановить</button>{/if}
    <button class="quiet-button" onclick={downloadGenerated} disabled={busy || !hasContent}>Сохранить</button>
    <button class="primary" onclick={startUpload} disabled={!conn || busy || !hasContent || !!previewError || (!!preparedPayload && preparedPayload.length > MAX_UPLOAD_BYTES)}>{isWriting ? 'Передаём…' : 'На значок ↗'}</button>
  </footer>
  {#if isWriting || progressLabel}<UploadProgress {isWriting} {progress} {progressLabel} {uploadStartTime} sentBytes={sentBytesForEta} totalBytes={totalBytesForEta} />{/if}
  <details class="logs"><summary>Журнал</summary><ul>{#each logs as entry}<li>{entry}</li>{:else}<li>Пока пусто.</li>{/each}</ul></details>
</main>
<dialog bind:this={helpDialog} class="device-dialog help-dialog">
  <div class="dialog-header"><h2>Подключение и файлы</h2><button class="icon-button" aria-label="Закрыть справку" onclick={() => helpDialog.close()}>×</button></div>
  <ol class="help-steps"><li>Откройте на значке экран Bluetooth с QR-кодом.</li><li>Отключите его от ZRun и браузера, нажмите «Подключить».</li><li>Выберите контент и отправьте. Для нескольких E87 сохраните разные имена и MAC с их экранов.</li></ol>
  <FormatGuide mode={uploadMode} width={pictureWidth} height={pictureHeight} />
  <p class="format-hint">E87 Studio 1.0 · обработка локально.<br />Основано на web-bluetooth-e87 · Felix Herbst · MIT.</p>
</dialog>
