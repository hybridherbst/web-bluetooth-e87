<script lang="ts">
  import { formatDuration, formatBytes } from './lib/utils'
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
  } from './lib/image-processing'
  import { parseAviFrames, readAviFps } from './lib/avi-preview'
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
    type UploadMode,
    type E87SmallFileEntry,
    type E87FileBrowseEntry,
  } from './lib/e87-protocol'
  import { buildMjpgAvi } from './avi-builder'
  import type { PatternDef } from './pattern-generators'
  import QRCode from 'qrcode'

  import AviPlayer from './lib/AviPlayer.svelte'
  import UploadProgress from './lib/UploadProgress.svelte'
  import ImageMode from './lib/ImageMode.svelte'
  import SequenceMode from './lib/SequenceMode.svelte'
  import VideoMode from './lib/VideoMode.svelte'
  import PatternMode from './lib/PatternMode.svelte'
  import LiveTransformCanvas from './lib/LiveTransformCanvas.svelte'
  import PreviewModeSwitch from './lib/PreviewModeSwitch.svelte'
  import QrMode from './lib/QrMode.svelte'

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

  let status = $state('Disconnected')
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

  let uploadMode: UploadMode = $state((saved.uploadMode ?? 'pattern') as UploadMode)
  let selectedFile: File | null = $state(null)
  let selectedFiles: File[] = $state([])
  let previewUrl: string | null = $state(null)

  let videoFps = $state(n(saved.videoFps, 12))
  let sequenceFps = $state(n(saved.sequenceFps, 1))
  let videoTrimStart = $state(0)
  let videoTrimEnd = $state(0)
  let videoDuration = $state(0)
  let patternFrameCount = $state(n(saved.patternFrameCount, 60))
  let patternFps = $state(n(saved.patternFps, 12))
  let selectedPattern: PatternDef | null = $state(null)
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
      const resized = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.9 })
      return new Uint8Array(await resized.arrayBuffer())
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
      status = 'Web Bluetooth is not available in this browser.'
      log(status)
      return
    }
    isConnecting = true
    try {
      status = 'Requesting device...'
      const nextConn = await connectE87(log)
      batteryLevel = nextConn.batteryLevel
      batteryUpdatedAt = nextConn.batteryUpdatedAt
      // Auto-read battery via Qix 9E protocol
      try {
        const result = await refreshBatteryE87(nextConn, log)
        batteryLevel = result.level
        batteryUpdatedAt = result.updatedAt
      } catch { /* best effort */ }
      // Auto-read screen info
      try {
        const info = await getScreenInfoE87(nextConn, log)
        applyScreenInfo(info)
      } catch { /* best effort */ }
      conn = nextConn
      status = `Connected: ${nextConn.device.name ?? 'Unknown device'}`
    } catch (error) {
      status = `Connection failed: ${(error as Error).message}`
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
    status = 'Disconnected'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      status = 'Not connected.'
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
      await prepareImageLiveFrames()
    }
  }

  async function setMultipleFiles(event: Event): Promise<void> {
    resetVideoScrubber()
    const input = event.target as HTMLInputElement
    const files = input.files
    if (!files || files.length === 0) return
    selectedFiles = Array.from(files)
    clearPreparedState()
    clearAviPreview()
    revokePreviewUrl()
    previewUrl = null
    log(`Selected ${selectedFiles.length} images for sequence`)
    await prepareSequenceLiveFrames()
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
    }
  }

  function selectPattern(pat: PatternDef): void {
    selectedPattern = pat
    clearPreparedState()
    clearAviPreview()
  }

  function switchMode(mode: UploadMode): void {
    uploadMode = mode
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

    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.92 })
    return new Uint8Array(await blob.arrayBuffer())
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
      } else if (uploadMode === 'pattern') {
        if (!selectedPattern) throw new Error('No pattern selected')
        isGeneratingPattern = true
        const patternFramesRaw = await selectedPattern.generate({ frames: patternFrameCount, fps: patternFps })
        const patternFrames = await normalizePatternFramesForOutput(patternFramesRaw)
        avi = buildMjpgAvi(patternFrames, { fps: patternFps })
        label = `${selectedPattern.name} — ${patternFrameCount} frames @ ${patternFps}fps`
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
      log(`Preview failed: ${(err as Error).message}`)
    } finally {
      isGeneratingPreview = false
      isGeneratingPattern = false
    }
  }

  // ─── Get upload bytes ───

  async function getUploadBytes(): Promise<Uint8Array> {
    if (preparedPayload) {
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
    if (uploadMode === 'pattern') {
      if (!selectedPattern) throw new Error('No pattern selected.')
      const patternFramesRaw = await selectedPattern.generate({ frames: patternFrameCount, fps: patternFps })
      const patternFrames = await normalizePatternFramesForOutput(patternFramesRaw)
      return buildMjpgAvi(patternFrames, { fps: patternFps })
    }
    if (uploadMode === 'qr') {
      return generateQrJpegBytes()
    }
    throw new Error(`Unknown upload mode: ${uploadMode}`)
  }

  function resolveUploadModeForDevice(): UploadMode {
    if (uploadMode === 'qr') return 'image'
    if (preparedIsStillImage) return 'image'
    return uploadMode
  }

  async function downloadGenerated(): Promise<void> {
    try {
      const payload = await getUploadBytes()
      const deviceMode = resolveUploadModeForDevice()
      const ext = deviceMode === 'image' ? 'jpg' : 'avi'
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
      log(`Download failed: ${(err as Error).message}`)
    }
  }

  // ─── Upload orchestration ───

  async function startUpload(): Promise<void> {
    if (!conn) {
      status = 'Not connected.'
      return
    }
    if (uploadMode === 'image' && !selectedFile && !preparedPayload) {
      status = 'Select an image.'
      return
    }
    if (uploadMode === 'images' && selectedFiles.length === 0) {
      status = 'Select images for the sequence.'
      return
    }
    if (uploadMode === 'video' && !selectedFile) {
      status = 'Select a video file.'
      return
    }
    if (uploadMode === 'pattern' && !selectedPattern) {
      status = 'Select a pattern.'
      return
    }
    if (uploadMode === 'qr' && !qrUrl.trim()) {
      status = 'Enter a URL for QR mode.'
      return
    }

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
      status = `Upload completed in ${elapsed}.`
    } catch (error) {
      status = `Upload failed: ${(error as Error).message}`
      log(status)
    } finally {
      isWriting = false
    }
  }

  function cancelWrite(): void {
    cancelRequested = true
    log('Cancel requested.')
  }
</script>

<main class="app">
  <h1>E87 / L8 Badge Writer</h1>
  <p class="hint">Web Bluetooth uploader for circular LED badges.</p>

  <!-- ═══ Connection panel ═══ -->
  <section class="panel">
    <div class="row buttons">
      <button onclick={connect} disabled={isConnecting || isWriting}>
        {isConnecting ? '🔄 Connecting…' : '🔗 Connect'}
      </button>
      <button onclick={disconnect} disabled={!conn?.server?.connected || isWriting}>🔌 Disconnect</button>
      <button class="secondary" onclick={cancelWrite} disabled={!isWriting}>🛑 Cancel</button>
    </div>
    <div class="status">Status: {status}</div>
    {#if batteryLevel !== null}
      <div class="status">Battery: {batteryLevel}% <span class="dim">({batteryUpdatedAt})</span></div>
    {/if}

    <div class="settings" style="margin-top:0.5rem">
      <label style="min-width: 280px; flex:1">
        <span>Small files</span>
        <select bind:value={selectedSmallFileKey} disabled={isDeviceOpsBusy || smallFiles.length === 0}>
          <option value="">-- none --</option>
          {#each smallFiles as f}
            <option value={smallFileKey(f)}>{f.typeName} — id {f.id} — {formatBytes(f.size)}</option>
          {/each}
        </select>
      </label>
    </div>
    {#if smallFileReadText}
      <textarea readonly rows="8" value={smallFileReadText}></textarea>
    {/if}
    {#if rcspInfoText}
      <textarea readonly rows="10" value={rcspInfoText}></textarea>
    {/if}
  </section>

  <!-- ═══ Upload panel ═══ -->
  <section class="panel">
    <!-- Mode tabs -->
    <div class="row buttons mode-tabs">
      <button class:active={uploadMode === 'pattern'} onclick={() => switchMode('pattern')} disabled={isWriting}>
        ✨ Pattern
      </button>
      <button class:active={uploadMode === 'image'} onclick={() => switchMode('image')} disabled={isWriting}>
        🖼 Image
      </button>
      <button class:active={uploadMode === 'images'} onclick={() => switchMode('images')} disabled={isWriting}>
        🎞 Sequence
      </button>
      <button class:active={uploadMode === 'video'} onclick={() => switchMode('video')} disabled={isWriting}>
        🎬 Video
      </button>
      <button class:active={uploadMode === 'qr'} onclick={() => switchMode('qr')} disabled={isWriting}>
        🔳 QR
      </button>
    </div>

    {#if uploadMode === 'image'}
      <div class="row buttons" style="margin-bottom:0.5rem">
        <PreviewModeSwitch bind:mode={imagePreviewMode} disabled={isWriting || isGeneratingPreview} />
      </div>
    {:else if uploadMode === 'images'}
      <div class="row buttons" style="margin-bottom:0.5rem">
        <PreviewModeSwitch bind:mode={sequencePreviewMode} disabled={isWriting || isGeneratingPreview} />
      </div>
    {:else if uploadMode === 'video'}
      <div class="row buttons" style="margin-bottom:0.5rem">
        <PreviewModeSwitch bind:mode={videoPreviewMode} disabled={isWriting || isGeneratingPreview} />
      </div>
    {/if}

    <!-- Mode-specific content -->
    {#if uploadMode === 'pattern'}
      <PatternMode
        {isWriting}
        {isGeneratingPreview}
        {isGeneratingPattern}
        {selectedPattern}
        bind:patternFrameCount
        bind:patternFps
        onSelectPattern={selectPattern}
        onGeneratePreview={generatePreview}
        onGenerateStill={generatePatternStill}
      />
    {:else if uploadMode === 'image'}
      <ImageMode
        {isWriting}
        {selectedFile}
        bind:backdropColor={imageBackdropColor}
        onSelectFile={setFile}
      />

      {#if imagePreviewMode === 'live' && imageLiveFrames.length > 0}
        <LiveTransformCanvas
          frames={imageLiveFrames}
          fps={1}
          backdropColor={imageBackdropColor}
          bind:scale={imageScale}
          bind:panX={imagePanX}
          bind:panY={imagePanY}
        />
      {:else if imagePreviewMode === 'preview' && previewUrl}
        <div style="text-align:center;margin:0.5rem 0">
          <img src={previewUrl} alt="Preview" style="max-width:220px;max-height:220px;border:1px solid #334;border-radius:50%;aspect-ratio:1" />
        </div>
      {/if}

      {#if imagePreviewMode === 'preview' && selectedFile}
        <div class="row buttons" style="margin-top:0.4rem">
          <button onclick={generatePreview} disabled={isWriting || isGeneratingPreview}>
            {isGeneratingPreview ? '⚙️ Generating…' : '🧪 Generate Preview'}
          </button>
        </div>
      {/if}
    {:else if uploadMode === 'images'}
      <SequenceMode
        {isWriting}
        {selectedFiles}
        bind:sequenceFps
        onSelectFiles={setMultipleFiles}
      />

      {#if sequencePreviewMode === 'live' && sequenceLiveFrames.length > 0}
        <LiveTransformCanvas
          frames={sequenceLiveFrames}
          fps={sequenceFps}
          bind:scale={sequenceScale}
          bind:panX={sequencePanX}
          bind:panY={sequencePanY}
        />
      {:else if sequencePreviewMode === 'preview'}
        <div class="row buttons" style="margin-top:0.4rem">
          <button onclick={generatePreview} disabled={isWriting || isGeneratingPreview || selectedFiles.length === 0}>
            {isGeneratingPreview ? '⚙️ Generating…' : '🧪 Generate Preview'}
          </button>
        </div>
      {/if}
    {:else if uploadMode === 'video'}
      <VideoMode
        {isWriting}
        {selectedFile}
        bind:videoFps
        bind:videoTrimStart
        bind:videoTrimEnd
        {videoDuration}
        onSelectVideo={setVideoFile}
        onScrubStart={onVideoScrubStart}
        onScrubFrame={onVideoScrubFrame}
        onScrubEnd={onVideoScrubEnd}
      />

      {#if videoScrubFrame && isVideoScrubbing}
        <LiveTransformCanvas
          frames={[videoScrubFrame]}
          fps={videoFps}
          bind:scale={videoScale}
          bind:panX={videoPanX}
          bind:panY={videoPanY}
        />
      {:else if videoPreviewMode === 'live' && videoLiveFrames.length > 0}
        <LiveTransformCanvas
          frames={videoLiveFrames}
          fps={videoFps}
          bind:scale={videoScale}
          bind:panX={videoPanX}
          bind:panY={videoPanY}
        />
      {:else if videoPreviewMode === 'preview'}
        <div class="row buttons" style="margin-top:0.4rem">
          <button onclick={generatePreview} disabled={isWriting || isGeneratingPreview || !selectedFile}>
            {isGeneratingPreview ? '⚙️ Generating…' : '🧪 Generate Preview'}
          </button>
        </div>
      {/if}
    {:else if uploadMode === 'qr'}
      <QrMode
        {isWriting}
        bind:qrUrl
        bind:qrDarkColor
        bind:qrLightColor
        bind:qrDotStyle
        bind:qrOutsideMode
        bind:qrZoom
        bind:qrRotation
      />
      {#if previewUrl}
        <div style="text-align:center;margin:0.5rem 0">
          <img src={previewUrl} alt="QR preview" style="max-width:220px;max-height:220px;border:1px solid #334;border-radius:50%;aspect-ratio:1" />
        </div>
      {/if}
    {/if}

    <!-- Shared AVI preview player -->
    {#if aviPreviewFrames.length > 0 && (
      uploadMode === 'pattern'
      || (uploadMode === 'images' && sequencePreviewMode === 'preview')
      || (uploadMode === 'video' && videoPreviewMode === 'preview' && !isVideoScrubbing)
    )}
      <AviPlayer
        bind:this={aviPlayer}
        frames={aviPreviewFrames}
        fps={aviPreviewFps}
      />
      {#if preparedPayloadLabel}
        <p class="dim payload-info">
          Ready: {preparedPayloadLabel}
          {#if preparedPayload && preparedPayload.length > MAX_UPLOAD_BYTES}
            <span style="color:#ff6666">⚠ {formatBytes(preparedPayload.length)} exceeds {formatBytes(MAX_UPLOAD_BYTES)} limit</span>
          {/if}
        </p>
      {/if}
    {/if}

    {#if previewUrl && preparedPayload && aviPreviewFrames.length === 0 && uploadMode === 'pattern'}
      <div style="text-align:center;margin:0.5rem 0">
        <img src={previewUrl} alt="Pattern still" style="max-width:200px;max-height:200px;border:1px solid #334;border-radius:50%;aspect-ratio:1" />
      </div>
      {#if preparedPayloadLabel}
        <p class="dim payload-info">
          Ready: {preparedPayloadLabel}
        </p>
      {/if}
    {/if}

    <!-- Debug settings -->
    {#if debugMode}
      <div class="settings">
        <label>
          <span>Inter-chunk delay (ms)</span>
          <input type="number" min="0" max="1000" step="1" bind:value={interChunkDelayMs} disabled={isWriting} />
        </label>
      </div>
    {/if}

    <!-- Upload button -->
    <div class="row buttons" style="margin-top:0.5rem">
      <button onclick={startUpload} disabled={!conn || isWriting}>
        {isWriting ? '📡 Sending…' : '📡 Send to Device'}
      </button>
      <button onclick={downloadGenerated} disabled={isWriting}>
        💾 Download
      </button>
    </div>

    <!-- Upload progress -->
    <UploadProgress
      {isWriting}
      {progress}
      {progressLabel}
      {uploadStartTime}
      sentBytes={sentBytesForEta}
      totalBytes={totalBytesForEta}
    />
  </section>

  <!-- ═══ Log panel ═══ -->
  <section class="panel logs">
    <h2>Log</h2>
    <ul>
      {#each logs as entry}
        <li>{entry}</li>
      {/each}
    </ul>
  </section>
</main>

<style>
  :global(body) {
    --base: #3fd2fb;
    --neutral-800: #2a2a2a;
    --neutral-900: #171717;
    --neutral-950: #0f0f0f;
    margin: 0;
    font-family: 'Inter', 'IBM Plex Sans', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: #000;
    color: #fff;
    min-height: 100vh;
  }
  .app {
    width: 100%;
    max-width: 1024px;
    margin: 0 auto;
    padding: 0.85rem;
    box-sizing: border-box;
  }
  h1 { margin: 0 0 0.25rem; font-size: 1.5rem; letter-spacing: -0.01em; }
  .hint { margin: 0 0 0.7rem; color: #a3a3a3; font-size: 0.82rem; }
  .panel {
    background: var(--neutral-900);
    border: 1px solid var(--neutral-800);
    box-shadow: none;
    border-radius: 2px;
    padding: 0.75rem;
    margin-bottom: 0.65rem;
  }
  .row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.5rem; }
  .mode-tabs { border-bottom: 1px solid var(--neutral-800); padding-bottom: 0.5rem; margin-bottom: 0.5rem; }
  .status { font-weight: 600; color: #e9e9ec; margin-bottom: 0.15rem; }
  .dim { font-weight: 400; color: #a3a3a3; }
  .payload-info { font-size: 0.8rem; margin: 0.2rem 0; text-align: center; }
  .settings { display: flex; gap: 0.55rem; margin: 0.5rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span {
    color: #d4d4d4;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
    text-transform: uppercase;
    letter-spacing: -0.08em;
    font-size: 0.72rem;
  }
  input, button {
    border-radius: 2px;
    border: 1px solid var(--neutral-800);
    background: #000;
    color: #f5f5f5;
    padding: 0.52rem 0.62rem;
    font-size: 0.82rem;
  }
  input[type="number"] { width: 90px; max-width: 100%; }
  button {
    cursor: pointer;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: -0.1em;
    color: var(--base);
    background: color-mix(in srgb, var(--base) 8%, transparent);
    border-color: color-mix(in srgb, var(--base) 36%, var(--neutral-800));
  }
  button:hover:not(:disabled) {
    border-color: var(--base);
    background: color-mix(in srgb, var(--base) 20%, transparent);
    box-shadow: none;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.secondary {
    border-color: rgba(255, 77, 77, 0.55);
    background: rgba(255, 77, 77, 0.08);
    color: #ff8f8f;
  }
  button.active {
    border-color: var(--base);
    background: color-mix(in srgb, var(--base) 20%, transparent);
    color: var(--base);
  }
  .logs h2 { margin: 0 0 0.3rem; font-size: 0.95rem; }
  .logs ul {
    list-style: none; padding: 0; margin: 0;
    max-height: 220px; overflow: auto;
  }
  .logs li {
    color: #a3a3a3;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.8rem; line-height: 1.35; padding: 1px 0;
    word-break: break-all;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* ─── Mobile ─── */
  @media (max-width: 600px) {
    .app { padding: 0.5rem; }
    h1 { font-size: 1.2rem; }
    .panel { padding: 0.7rem; border-radius: 2px; }
    .row { gap: 0.4rem; }
    .settings { gap: 0.5rem; }
    .settings label { min-width: 0; flex: 1 1 auto; }
    button { padding: 0.5rem 0.6rem; font-size: 0.85rem; }
    .logs ul { max-height: 160px; }
    .logs li { font-size: 0.7rem; }
  }
</style>
