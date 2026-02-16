<script lang="ts">
  const E87_IMAGE_WIDTH = 368
  const E87_IMAGE_HEIGHT = 368
  const E87_DATA_CHUNK_SIZE = 490
  const E87_TARGET_IMAGE_BYTES = 16000

  import { getRandomAuthData, getEncryptedAuthData } from './jl-auth'
  import { buildMjpgAvi } from './avi-builder'

  type UploadMode = 'image' | 'images' | 'video'

  const SERVICE_CANDIDATES: BluetoothServiceUUID[] = [
    0xae00,
    '0000ae00-0000-1000-8000-00805f9b34fb',
    0xfd00,
    '0000fd00-0000-1000-8000-00805f9b34fb',
    'c2e6fd00-e966-1000-8000-bef9c223df6a',
  ]

  const WRITE_CHAR_CANDIDATES: BluetoothCharacteristicUUID[] = [
    0xae01,
    '0000ae01-0000-1000-8000-00805f9b34fb',
  ]

  const CONTROL_CHAR_CANDIDATES: BluetoothCharacteristicUUID[] = [
    'c2e6fd02-e966-1000-8000-bef9c223df6a',
  ]

  const NOTIFY_CHAR_CANDIDATES: BluetoothCharacteristicUUID[] = [
    0xae02,
    '0000ae02-0000-1000-8000-00805f9b34fb',
    'c2e6fd01-e966-1000-8000-bef9c223df6a',
    'c2e6fd03-e966-1000-8000-bef9c223df6a',
    'c2e6fd05-e966-1000-8000-bef9c223df6a',
  ]

  type E87Frame = {
    flag: number
    cmd: number
    length: number
    body: Uint8Array
  }

  let device: BluetoothDevice | null = $state(null)
  let server: BluetoothRemoteGATTServer | null = $state(null)
  let characteristic: BluetoothRemoteGATTCharacteristic | null = $state(null)
  let controlCharacteristic: BluetoothRemoteGATTCharacteristic | null = $state(null)
  let notifyCharacteristics: BluetoothRemoteGATTCharacteristic[] = $state([])

  let isConnecting = $state(false)
  let isWriting = $state(false)
  let cancelRequested = $state(false)

  let interChunkDelayMs = $state(0)
  let useDefaultImage = $state(true)

  let status = $state('Disconnected')
  let progress = $state(0)
  let progressLabel = $state('')
  let batteryLevel: number | null = $state(null)
  let batteryUpdatedAt = $state('')

  let logs: string[] = $state([])
  let previewUrl: string | null = $state('/captured_image.jpg')
  let selectedFile: File | null = $state(null)
  let selectedFiles: File[] = $state([])
  let uploadMode: UploadMode = $state('image')
  let videoFps = $state(12)
  const notificationQueue: Uint8Array[] = []

  // Auto-responder for cmd 0x20 (FILE_COMPLETE).
  // The device expects a response within ~100ms. Our polling loop is too slow,
  // so we respond directly in the notification handler for near-zero latency.
  let fileCompleteAutoRespond = false
  let fileCompleteHandled = false

  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  function log(message: string): void {
    const ts = new Date().toLocaleTimeString()
    logs = [`[${ts}] ${message}`, ...logs].slice(0, 250)
  }

  function setFile(event: Event): void {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    selectedFile = file
    useDefaultImage = false
    if (file) {
      log(`Selected: ${file.name}`)
      if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
      previewUrl = URL.createObjectURL(file)
    }
  }

  function setMultipleFiles(event: Event): void {
    const input = event.target as HTMLInputElement
    const files = input.files
    if (!files || files.length === 0) return
    selectedFiles = Array.from(files)
    useDefaultImage = false
    log(`Selected ${selectedFiles.length} images for sequence`)
    if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
    previewUrl = URL.createObjectURL(selectedFiles[0])
  }

  function setVideoFile(event: Event): void {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    selectedFile = file
    useDefaultImage = false
    if (file) {
      log(`Selected video: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`)
      if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
      previewUrl = URL.createObjectURL(file)
    }
  }

  function selectDefaultImage(): void {
    useDefaultImage = true
    selectedFile = null
    if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
    previewUrl = '/captured_image.jpg'
    log('Using default captured image (ground-truth from packet capture).')
  }

  function toHex(bytes: Uint8Array): string {
    return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  }

  function hexToBytes(hex: string): Uint8Array {
    const clean = hex.replace(/[^0-9a-fA-F]/g, '')
    if (clean.length % 2 !== 0) throw new Error(`Invalid hex string length: ${hex}`)
    const out = new Uint8Array(clean.length / 2)
    for (let i = 0; i < clean.length; i += 2) {
      out[i / 2] = Number.parseInt(clean.slice(i, i + 2), 16)
    }
    return out
  }

  function crc16xmodem(data: Uint8Array): number {
    let crc = 0x0000
    for (let i = 0; i < data.length; i++) {
      crc ^= data[i] << 8
      for (let j = 0; j < 8; j++) {
        if (crc & 0x8000) {
          crc = ((crc << 1) ^ 0x1021) & 0xffff
        } else {
          crc = (crc << 1) & 0xffff
        }
      }
    }
    return crc
  }

  function parseE87Frame(data: Uint8Array): E87Frame | null {
    if (data.length < 8) return null
    if (data[0] !== 0xfe || data[1] !== 0xdc || data[2] !== 0xba) return null
    if (data[data.length - 1] !== 0xef) return null
    const flag = data[3]
    const cmd = data[4]
    const length = (data[5] << 8) | data[6]
    const body = data.slice(7, data.length - 1)
    if (body.length !== length) return null
    return { flag, cmd, length, body }
  }

  function buildE87Frame(flag: number, cmd: number, body: Uint8Array): Uint8Array {
    const out = new Uint8Array(3 + 1 + 1 + 2 + body.length + 1)
    out[0] = 0xfe; out[1] = 0xdc; out[2] = 0xba
    out[3] = flag & 0xff
    out[4] = cmd & 0xff
    out[5] = (body.length >> 8) & 0xff
    out[6] = body.length & 0xff
    out.set(body, 7)
    out[out.length - 1] = 0xef
    return out
  }

  function queuePreview(): string {
    const tail = notificationQueue.slice(Math.max(0, notificationQueue.length - 6))
    if (!tail.length) return 'no queued notifications'
    return tail
      .map((raw) => {
        const f = parseE87Frame(raw)
        if (f) return `frame(flag=0x${f.flag.toString(16)},cmd=0x${f.cmd.toString(16)},len=${f.length})`
        return `raw(${raw.length}):${toHex(raw.slice(0, Math.min(8, raw.length)))}`
      })
      .join(', ')
  }

  async function waitForNotificationFrame(
    predicate: (frame: E87Frame) => boolean,
    timeoutMs = 8000,
    waitLabel = 'matching E87 frame'
  ): Promise<E87Frame> {
    log(`Waiting for ${waitLabel}...`)
    const started = Date.now()
    while (Date.now() - started < timeoutMs) {
      for (let i = 0; i < notificationQueue.length; i += 1) {
        const raw = notificationQueue[i]
        const frame = parseE87Frame(raw)
        if (!frame) continue
        if (predicate(frame)) {
          notificationQueue.splice(i, 1)
          return frame
        }
      }
      await sleep(20)
    }
    throw new Error(`Timeout waiting for ${waitLabel}. Recent notifications: ${queuePreview()}`)
  }

  async function waitForRawNotification(
    predicate: (raw: Uint8Array) => boolean,
    timeoutMs = 2000,
    waitLabel = 'matching raw notification'
  ): Promise<Uint8Array> {
    log(`Waiting for ${waitLabel}...`)
    const started = Date.now()
    while (Date.now() - started < timeoutMs) {
      for (let i = 0; i < notificationQueue.length; i += 1) {
        const raw = notificationQueue[i]
        if (predicate(raw)) {
          notificationQueue.splice(i, 1)
          return raw
        }
      }
      await sleep(20)
    }
    throw new Error(`Timeout waiting for ${waitLabel}. Recent notifications: ${queuePreview()}`)
  }

  function buildFilePathResponse(deviceSeq: number): Uint8Array {
    const now20 = new Date()
    const dateStr = `${now20.getFullYear()}${String(now20.getMonth() + 1).padStart(2, '0')}${String(now20.getDate()).padStart(2, '0')}${String(now20.getHours()).padStart(2, '0')}${String(now20.getMinutes()).padStart(2, '0')}${String(now20.getSeconds()).padStart(2, '0')}`
    const ext = uploadMode === 'image' ? '.jpg' : '.avi'
    const devicePath = `\u555C${dateStr}${ext}`
    const pathUtf16 = new Uint8Array(devicePath.length * 2 + 2)
    for (let ci = 0; ci < devicePath.length; ci++) {
      const code = devicePath.charCodeAt(ci)
      pathUtf16[ci * 2] = code & 0xff
      pathUtf16[ci * 2 + 1] = (code >> 8) & 0xff
    }
    const resp = new Uint8Array(2 + pathUtf16.length)
    resp[0] = 0x00
    resp[1] = deviceSeq
    resp.set(pathUtf16, 2)
    return resp
  }

  function onNotification(event: Event): void {
    const target = event.target as BluetoothRemoteGATTCharacteristic
    const value = target.value
    if (!value) return
    const raw = new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength))
    notificationQueue.push(raw)
    if (notificationQueue.length > 200) notificationQueue.shift()
    const frame = parseE87Frame(raw)
    if (frame) {
      log(`RX frame flag=0x${frame.flag.toString(16)} cmd=0x${frame.cmd.toString(16)} len=${frame.length}`)

      // Auto-respond to cmd 0x20 (FILE_COMPLETE) with near-zero latency.
      // The device has a tight timeout (~100ms) for this response.
      // Capture shows: RX cmd=0x20 flag=0xC0 body=[seq] → TX cmd=0x20 flag=0x00 body=[0x00, seq, path...]
      if (fileCompleteAutoRespond && frame.cmd === 0x20 && frame.flag === 0xc0 && !fileCompleteHandled) {
        fileCompleteHandled = true
        const deviceSeq = frame.body[0] ?? 0
        const respBody = buildFilePathResponse(deviceSeq)
        const respFrame = buildE87Frame(0x00, 0x20, respBody)
        log(`AUTO-RESPOND cmd 0x20: seq=${deviceSeq}, sending path response (${respFrame.length} bytes)`)
        // Fire-and-forget write — must not await in sync handler
        if (characteristic) {
          characteristic.writeValueWithoutResponse(respFrame).then(() => {
            log('cmd 0x20 auto-response sent successfully.')
          }).catch((err: unknown) => {
            log(`cmd 0x20 auto-response failed: ${(err as Error).message}`)
          })
        }
      }
    } else {
      log(`RX notify (${raw.length} bytes): ${toHex(raw.slice(0, Math.min(24, raw.length)))}`)
    }
  }

  async function findCharacteristics(
    targetServer: BluetoothRemoteGATTServer
  ): Promise<{
    write: BluetoothRemoteGATTCharacteristic
    control: BluetoothRemoteGATTCharacteristic
    notify: BluetoothRemoteGATTCharacteristic[]
  }> {
    const normalize = (value: string | number): string => {
      if (typeof value === 'number') return value.toString(16).padStart(4, '0').toLowerCase()
      return value.toLowerCase().replace(/[^0-9a-f]/g, '')
    }
    const matchUuid = (uuid: string, candidates: Array<string | number>): boolean => {
      const normUuid = normalize(uuid)
      return candidates.some((c) => normUuid.includes(normalize(c)))
    }

    const primaryServices = await targetServer.getPrimaryServices()
    const services: BluetoothRemoteGATTService[] = [...primaryServices]
    for (const primary of primaryServices) {
      try {
        const included = await primary.getIncludedServices()
        if (included.length) {
          log(`Primary ${primary.uuid} has ${included.length} included service(s).`)
          services.push(...included)
        }
      } catch { /* ignore */ }
    }

    const dedupedServices: BluetoothRemoteGATTService[] = []
    const seenServiceUuids = new Set<string>()
    for (const s of services) {
      if (seenServiceUuids.has(s.uuid)) continue
      seenServiceUuids.add(s.uuid)
      dedupedServices.push(s)
    }

    const writable: Array<{ char: BluetoothRemoteGATTCharacteristic; serviceUuid: string }> = []
    const notifiable: Array<{ char: BluetoothRemoteGATTCharacteristic; serviceUuid: string }> = []
    for (const service of dedupedServices) {
      const chars = await service.getCharacteristics()
      log(`Service ${service.uuid} exposes ${chars.length} characteristic(s).`)
      for (const c of chars) {
        const p = c.properties
        if (p.write || p.writeWithoutResponse) {
          writable.push({ char: c, serviceUuid: service.uuid })
          log(`  writable: ${c.uuid} (write=${Boolean(p.write)}, wnr=${Boolean(p.writeWithoutResponse)})`)
        }
        if (p.notify || p.indicate) {
          notifiable.push({ char: c, serviceUuid: service.uuid })
          log(`  notify: ${c.uuid} (notify=${Boolean(p.notify)}, indicate=${Boolean(p.indicate)})`)
        }
      }
    }

    const selectedWrite = writable.find((e) => matchUuid(e.char.uuid, WRITE_CHAR_CANDIDATES))
    if (!selectedWrite) {
      const seen = writable.map((w) => `${w.char.uuid}@${w.serviceUuid}`).join(', ') || 'none'
      throw new Error(`E87 requires AE01 data writer; discovered: ${seen}`)
    }
    const selectedControl = writable.find((e) => matchUuid(e.char.uuid, CONTROL_CHAR_CANDIDATES))
    if (!selectedControl) {
      const seen = writable.map((w) => `${w.char.uuid}@${w.serviceUuid}`).join(', ') || 'none'
      throw new Error(`E87 requires FD02 control writer; discovered: ${seen}`)
    }

    const preferredNotifies = notifiable.filter((e) => matchUuid(e.char.uuid, NOTIFY_CHAR_CANDIDATES))
    const selectedNotify = preferredNotifies.length ? preferredNotifies : notifiable

    log(`Selected write: ${selectedWrite.char.uuid}`)
    log(`Selected control: ${selectedControl.char.uuid}`)
    for (const n of selectedNotify) log(`Selected notify: ${n.char.uuid}`)

    return {
      write: selectedWrite.char,
      control: selectedControl.char,
      notify: selectedNotify.map((n) => n.char),
    }
  }

  async function connect(): Promise<void> {
    if (!('bluetooth' in navigator)) {
      status = 'Web Bluetooth is not available in this browser.'
      log(status)
      return
    }
    isConnecting = true
    try {
      status = 'Requesting device...'
      device = await navigator.bluetooth.requestDevice({
        filters: [{ namePrefix: 'E87' }],
        optionalServices: SERVICE_CANDIDATES,
      })

      status = `Connecting to ${device.name ?? 'device'}...`
      server = (await device.gatt?.connect()) ?? null
      if (!server) throw new Error('No GATT server available.')

      const chars = await findCharacteristics(server)
      characteristic = chars.write
      controlCharacteristic = chars.control
      notifyCharacteristics = chars.notify

      try {
        const batteryService = await server.getPrimaryService(0x180f)
        const batteryChar = await batteryService.getCharacteristic(0x2a19)
        const value = await batteryChar.readValue()
        batteryLevel = value.getUint8(0)
        batteryUpdatedAt = new Date().toLocaleTimeString()
        log(`Battery: ${batteryLevel}%`)
      } catch {
        batteryLevel = null
        batteryUpdatedAt = ''
      }

      notificationQueue.length = 0
      for (const c of notifyCharacteristics) {
        c.addEventListener('characteristicvaluechanged', onNotification)
        await c.startNotifications()
      }
      log(`Notification channel ready (${notifyCharacteristics.length} characteristic(s)).`)

      status = `Connected: ${device.name ?? 'Unknown device'}`
    } catch (error) {
      status = `Connection failed: ${(error as Error).message}`
      log(status)
      controlCharacteristic = null
      batteryLevel = null
      batteryUpdatedAt = ''
      characteristic = null
      server = null
      device = null
    } finally {
      isConnecting = false
    }
  }

  async function disconnect(): Promise<void> {
    cancelRequested = true
    for (const c of notifyCharacteristics) {
      try {
        c.removeEventListener('characteristicvaluechanged', onNotification)
        await c.stopNotifications()
      } catch { /* ignore */ }
    }
    if (server?.connected) server.disconnect()
    notificationQueue.length = 0
    controlCharacteristic = null
    batteryLevel = null
    batteryUpdatedAt = ''
    notifyCharacteristics = []
    characteristic = null
    server = null
    device = null
    status = 'Disconnected'
    progress = 0
    progressLabel = ''
    log('Disconnected.')
  }

  async function writeChunk(chunk: Uint8Array): Promise<void> {
    if (!characteristic) throw new Error('Characteristic is not connected.')
    await writeChunkTo(characteristic, chunk)
  }

  async function writeChunkTo(target: BluetoothRemoteGATTCharacteristic, chunk: Uint8Array): Promise<void> {
    const outbound = Uint8Array.from(chunk)
    if (target.properties.writeWithoutResponse && target.writeValueWithoutResponse) {
      await target.writeValueWithoutResponse(outbound)
      return
    }
    await target.writeValue(outbound)
  }

  async function sendE87Frame(flag: number, cmd: number, body: Uint8Array): Promise<void> {
    const frame = buildE87Frame(flag, cmd, body)
    log(`TX frame flag=0x${flag.toString(16)} cmd=0x${cmd.toString(16)} len=${body.length}`)
    await writeChunk(frame)
  }

  async function imageFileTo368JpegBytes(file: File): Promise<Uint8Array> {
    const bitmap = await createImageBitmap(file)
    const srcRatio = bitmap.width / bitmap.height
    const targetRatio = E87_IMAGE_WIDTH / E87_IMAGE_HEIGHT
    let sx = 0, sy = 0, sw = bitmap.width, sh = bitmap.height
    if (srcRatio > targetRatio) {
      sw = Math.round(bitmap.height * targetRatio)
      sx = Math.floor((bitmap.width - sw) / 2)
    } else {
      sh = Math.round(bitmap.width / targetRatio)
      sy = Math.floor((bitmap.height - sh) / 2)
    }

    async function toJpegBlob(quality: number): Promise<Blob | null> {
      if ('OffscreenCanvas' in window) {
        const canvas = new OffscreenCanvas(E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
        const ctx = canvas.getContext('2d')
        if (!ctx) throw new Error('Could not create 2D canvas context.')
        ctx.fillStyle = 'black'
        ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
        ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
        return canvas.convertToBlob({ type: 'image/jpeg', quality })
      }
      const canvas = document.createElement('canvas')
      canvas.width = E87_IMAGE_WIDTH
      canvas.height = E87_IMAGE_HEIGHT
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('Could not create fallback 2D canvas context.')
      ctx.fillStyle = 'black'
      ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
      ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
      return new Promise<Blob | null>((resolve) => {
        canvas.toBlob((result) => resolve(result), 'image/jpeg', quality)
      })
    }

    const qualitySteps = [0.88, 0.8, 0.72, 0.64, 0.56, 0.48, 0.4, 0.34]
    let blob: Blob | null = null
    for (const q of qualitySteps) {
      const candidate = await toJpegBlob(q)
      if (!candidate) continue
      blob = candidate
      if (candidate.size <= E87_TARGET_IMAGE_BYTES) break
    }
    bitmap.close()
    if (!blob) throw new Error('Image conversion failed (no JPEG blob).')
    return new Uint8Array(await blob.arrayBuffer())
  }

  /** Convert a single image file to a 368x368 JPEG at a specific quality (no size targeting). */
  async function imageFileTo368JpegFrame(file: File, quality = 0.88): Promise<Uint8Array> {
    const bitmap = await createImageBitmap(file)
    const srcRatio = bitmap.width / bitmap.height
    const targetRatio = E87_IMAGE_WIDTH / E87_IMAGE_HEIGHT
    let sx = 0, sy = 0, sw = bitmap.width, sh = bitmap.height
    if (srcRatio > targetRatio) {
      sw = Math.round(bitmap.height * targetRatio)
      sx = Math.floor((bitmap.width - sw) / 2)
    } else {
      sh = Math.round(bitmap.width / targetRatio)
      sy = Math.floor((bitmap.height - sh) / 2)
    }
    const canvas = new OffscreenCanvas(E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    bitmap.close()
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality })
    return new Uint8Array(await blob.arrayBuffer())
  }

  /** Convert multiple image files to an MJPG AVI (image sequence, 1fps). */
  async function imagesToAvi(files: File[]): Promise<Uint8Array> {
    log(`Converting ${files.length} images to AVI sequence...`)
    const frames: Uint8Array[] = []
    for (let i = 0; i < files.length; i++) {
      log(`  Processing image ${i + 1}/${files.length}: ${files[i].name}`)
      frames.push(await imageFileTo368JpegFrame(files[i], 0.88))
    }
    const avi = buildMjpgAvi(frames, { fps: 1 })
    log(`AVI built: ${frames.length} frames, ${avi.length} bytes`)
    return avi
  }

  /** Extract frames from a video file at the given fps, resize to 368x368, build AVI. */
  async function videoToAvi(file: File, fps: number): Promise<Uint8Array> {
    log(`Extracting frames from video at ${fps} fps...`)
    const url = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.muted = true
    video.playsInline = true
    video.preload = 'auto'

    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => reject(new Error('Failed to load video'))
      video.src = url
    })

    // Seek to start
    video.currentTime = 0
    await new Promise<void>((r) => { video.onseeked = () => r() })

    const duration = video.duration
    const frameInterval = 1 / fps
    const canvas = new OffscreenCanvas(E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    const ctx = canvas.getContext('2d')!
    const frames: Uint8Array[] = []

    // Calculate source crop for center-crop to 1:1
    const srcRatio = video.videoWidth / video.videoHeight
    let sx = 0, sy = 0, sw = video.videoWidth, sh = video.videoHeight
    if (srcRatio > 1) {
      sw = video.videoHeight
      sx = Math.floor((video.videoWidth - sw) / 2)
    } else if (srcRatio < 1) {
      sh = video.videoWidth
      sy = Math.floor((video.videoHeight - sh) / 2)
    }

    log(`Video: ${video.videoWidth}x${video.videoHeight}, ${duration.toFixed(2)}s, extracting ~${Math.ceil(duration * fps)} frames`)

    for (let t = 0; t < duration; t += frameInterval) {
      video.currentTime = t
      await new Promise<void>((r) => { video.onseeked = () => r() })

      ctx.fillStyle = 'black'
      ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
      ctx.drawImage(video, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)

      const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.88 })
      frames.push(new Uint8Array(await blob.arrayBuffer()))

      if (frames.length % 10 === 0) log(`  Extracted ${frames.length} frames...`)
    }

    URL.revokeObjectURL(url)
    const avi = buildMjpgAvi(frames, { fps })
    log(`AVI built: ${frames.length} frames @ ${fps}fps, ${avi.length} bytes`)
    return avi
  }

  function randomTempName(): string {
    const n = Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0')
    return `${n}.tmp`
  }

  async function getUploadBytes(): Promise<Uint8Array> {
    if (uploadMode === 'image') {
      if (useDefaultImage) {
        log('Loading default captured image (15647 bytes ground-truth)...')
        const resp = await fetch('/captured_image.jpg')
        if (!resp.ok) throw new Error('Failed to load default captured_image.jpg')
        return new Uint8Array(await resp.arrayBuffer())
      }
      if (!selectedFile) throw new Error('No file selected.')
      if (selectedFile.type.startsWith('image/')) {
        return imageFileTo368JpegBytes(selectedFile)
      }
      return new Uint8Array(await selectedFile.arrayBuffer())
    }
    if (uploadMode === 'images') {
      if (selectedFiles.length === 0) throw new Error('No images selected for sequence.')
      return imagesToAvi(selectedFiles)
    }
    if (uploadMode === 'video') {
      if (!selectedFile) throw new Error('No video file selected.')
      return videoToAvi(selectedFile, videoFps)
    }
    throw new Error(`Unknown upload mode: ${uploadMode}`)
  }

  // ════════════════════════════════════════════════════════
  // E87 Upload — verified byte-for-byte against packet capture
  //
  // DATA SEND ORDER (two-part approach):
  //   Part A: jpeg[490:]  → chunked sequentially (N-1 chunks, last one short)
  //   Part B: jpeg[0:490] → sent as FINAL chunk with slot reset to 0
  //
  // This means the JFIF header is the LAST chunk sent, acting as
  // a commit signal. Verified: all 32 chunks match capture CRCs.
  // ════════════════════════════════════════════════════════

  async function writeFileE87(): Promise<void> {
    if (!notifyCharacteristics.length) throw new Error('No notification characteristic available.')
    if (!controlCharacteristic) throw new Error('E87 upload requires FD02 control characteristic.')

    const jpegBytes = await getUploadBytes()
    const isJpeg = jpegBytes[0] === 0xff && jpegBytes[1] === 0xd8
    const isAvi = jpegBytes[0] === 0x52 && jpegBytes[1] === 0x49 && jpegBytes[2] === 0x46 && jpegBytes[3] === 0x46
    const fmtLabel = isJpeg ? 'JPEG' : isAvi ? 'AVI' : 'raw data'
    log(`Prepared payload: ${jpegBytes.length} bytes (${fmtLabel}).`)

    // Update preview to show what we're actually sending
    if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
    previewUrl = URL.createObjectURL(new Blob([jpegBytes], { type: 'image/jpeg' }))

    let seqCounter = 0x00

    // ── AUTH: Jieli RCSP crypto handshake ──
    log('Auth: Starting Jieli RCSP crypto handshake...')
    const randomAuthData = getRandomAuthData()
    log(`Auth TX: [0x00, rand*16] = ${toHex(randomAuthData)}`)
    await writeChunk(randomAuthData)

    const deviceResponse = await waitForRawNotification(
      (raw) => raw.length === 17 && raw[0] === 0x01,
      5000, 'auth device response [0x01, encrypted*16]'
    )
    log(`Auth RX: ${toHex(deviceResponse)}`)

    log('Auth TX: [0x02, pass]')
    await writeChunk(Uint8Array.of(0x02, 0x70, 0x61, 0x73, 0x73))

    const deviceChallenge = await waitForRawNotification(
      (raw) => raw.length === 17 && raw[0] === 0x00,
      5000, 'auth device challenge [0x00, challenge*16]'
    )
    log(`Auth RX challenge: ${toHex(deviceChallenge)}`)

    const encryptedResponse = getEncryptedAuthData(deviceChallenge)
    log(`Auth TX encrypted: ${toHex(encryptedResponse)}`)
    await writeChunk(encryptedResponse)

    const authConfirm = await waitForRawNotification(
      (raw) => raw.length >= 5 && raw[0] === 0x02 && raw[1] === 0x70 && raw[2] === 0x61 && raw[3] === 0x73 && raw[4] === 0x73,
      5000, 'auth pass confirmation'
    )
    log(`Auth SUCCESS: ${toHex(authConfirm)}`)

    // ── PHASE 1: cmd 0x06 (reset auth flag) ──
    log('Phase 1: cmd 0x06 (reset auth flag)...')
    await sendE87Frame(0xc0, 0x06, Uint8Array.of(0x02, 0x00, 0x01))
    seqCounter = 0x01

    try { await writeChunkTo(controlCharacteristic, hexToBytes('9EBD 0B60 0D00 03')) } catch { /* best-effort */ }
    try {
      await waitForNotificationFrame((f) => f.cmd === 0x06, 3000, 'ack cmd 0x06')
      log('cmd 0x06 acked.')
    } catch { log('cmd 0x06 ack not received (continuing).') }

    // ── PHASE 2: FD02 control writes (time + settings) ──
    log('Phase 2: FD02 control writes...')
    const now = new Date()
    const timePayload = new Uint8Array([
      0x9e, 0x45, 0x08, 0x02, 0x07, 0x00,
      now.getFullYear() & 0xff, (now.getFullYear() >> 8) & 0xff,
      now.getMonth() + 1, now.getDate(), 0x00,
      now.getHours(), now.getMinutes(),
    ])
    await writeChunkTo(controlCharacteristic, timePayload)
    await sleep(20)
    await writeChunkTo(controlCharacteristic, hexToBytes('9E20 0816 0100 01'))
    await sleep(20)
    await writeChunkTo(controlCharacteristic, hexToBytes('9EB5 0B29 0100 80'))
    await sleep(200)

    // ── PHASE 3: cmd 0x03 (device info) — best-effort ──
    try {
      log('Phase 3: cmd 0x03 (best-effort)...')
      await sendE87Frame(0xc0, 0x03, Uint8Array.of(seqCounter, 0xff, 0xff, 0xff, 0xff, 0x01))
      seqCounter += 1
      await writeChunkTo(controlCharacteristic, hexToBytes('9ED3 0BC6 0100 01'))
      await sleep(20)
      await writeChunkTo(controlCharacteristic, hexToBytes('9E30 0820 0200 FF07'))
      await waitForNotificationFrame((f) => f.cmd === 0x03, 3000, 'ack cmd 0x03')
    } catch { log('cmd 0x03 not acked (continuing).') }

    // ── PHASE 4: cmd 0x07 (device config) — best-effort ──
    try {
      log('Phase 4: cmd 0x07 (best-effort)...')
      await sendE87Frame(0xc0, 0x07, Uint8Array.of(seqCounter, 0xff, 0xff, 0xff, 0xff, 0xff))
      seqCounter += 1
      await writeChunkTo(controlCharacteristic, hexToBytes('9E2B 08FF 0200 2200'))
      await sleep(40)
      await writeChunkTo(controlCharacteristic, hexToBytes('9E2D 08FF 0200 2400'))
      await waitForNotificationFrame((f) => f.cmd === 0x07, 3000, 'ack cmd 0x07')
    } catch { log('cmd 0x07 not acked (continuing).') }

    // ── PHASE 5: FD02 bootstrap before upload ──
    log('Phase 5: FD02 bootstrap...')
    await writeChunkTo(controlCharacteristic, hexToBytes('9EB5 0B29 0100 80'))
    await sleep(400)
    await writeChunkTo(controlCharacteristic, hexToBytes('9ED3 0BC6 0100 01'))
    try {
      await waitForRawNotification(
        (raw) => raw.length >= 5 && raw[0] === 0x9e && (raw[3] === 0xc7 || raw[2] === 0xc7),
        3000, 'FD01 device info (C7)'
      )
    } catch { log('FD01 C7 not observed (continuing).') }
    await writeChunkTo(controlCharacteristic, hexToBytes('9EF4 0BDC 0100 0C'))
    try {
      await waitForRawNotification(
        (raw) => raw.length >= 4 && raw[0] === 0x9e && raw[1] === 0xe6,
        3000, 'FD03 ready signal (9EE6)'
      )
      log('Device ready signal received.')
    } catch { log('FD03 ready signal not observed (continuing).') }

    // ── PHASE 6: cmd 0x21 (begin upload session) ──
    log('Phase 6: cmd 0x21 (begin upload)...')
    await sendE87Frame(0xc0, 0x21, Uint8Array.of(seqCounter, 0x00))
    seqCounter += 1
    await waitForNotificationFrame((f) => f.cmd === 0x21, 8000, 'ack cmd 0x21')

    // ── PHASE 7: cmd 0x27 (transfer parameters) ──
    log('Phase 7: cmd 0x27 (transfer params)...')
    await sendE87Frame(0xc0, 0x27, Uint8Array.of(seqCounter, 0x00, 0x00, 0x00, 0x00, 0x02, 0x01))
    seqCounter += 1
    await waitForNotificationFrame((f) => f.cmd === 0x27, 8000, 'ack cmd 0x27')

    // ── PHASE 8: cmd 0x1b (file metadata: size, CRC, name) ──
    // Body format: [seq] [size_b3] [size_b2] [size_b1] [size_b0]
    //              [fileCRC_hi] [fileCRC_lo] [rand] [rand]
    //              [name...] [0x00]
    // body[1:5] = 32-bit big-endian file size (verified from extended capture)
    // The device computes CRC-16 XMODEM over the reassembled file
    // and compares it to body[5:7]. Mismatch → status 0x03.
    log('Phase 8: cmd 0x1b (file metadata)...')
    const fileSize = jpegBytes.length
    const tempName = randomTempName()
    const nameBytes = new TextEncoder().encode(tempName)

    // Compute whole-file CRC-16 XMODEM (the device checks this after reassembly)
    const fileCrc = crc16xmodem(jpegBytes)
    log(`Whole-file CRC-16 XMODEM: 0x${fileCrc.toString(16).padStart(4, '0')}`)

    const metaBody = new Uint8Array(3 + 2 + 4 + nameBytes.length + 1)
    metaBody[0] = seqCounter
    seqCounter += 1
    metaBody[1] = (fileSize >> 24) & 0xff
    metaBody[2] = (fileSize >> 16) & 0xff
    metaBody[3] = (fileSize >> 8) & 0xff
    metaBody[4] = fileSize & 0xff
    metaBody[5] = (fileCrc >> 8) & 0xff   // CRC-16 XMODEM high byte
    metaBody[6] = fileCrc & 0xff          // CRC-16 XMODEM low byte
    metaBody[7] = Math.random() * 256 | 0 // random padding
    metaBody[8] = Math.random() * 256 | 0 // random padding
    metaBody.set(nameBytes, 9)
    metaBody[metaBody.length - 1] = 0x00

    await sendE87Frame(0xc0, 0x1b, metaBody)
    const metaAck = await waitForNotificationFrame((f) => f.cmd === 0x1b, 8000, 'ack cmd 0x1b')

    // Read the chunk size the device tells us to use from the 0x1b ack
    // Capture: ack body = [status, seq, chunkSize_hi, chunkSize_lo]
    let chunkSize = E87_DATA_CHUNK_SIZE
    if (metaAck.body.length >= 4) {
      chunkSize = (metaAck.body[2] << 8) | metaAck.body[3]
      log(`Device chunk size from 0x1b ack: ${chunkSize} bytes`)
      if (chunkSize === 0 || chunkSize > 4096) {
        log(`WARNING: unusual chunk size ${chunkSize}, falling back to ${E87_DATA_CHUNK_SIZE}`)
        chunkSize = E87_DATA_CHUNK_SIZE
      }
    }

    // ── PHASE 9: Data transfer ──
    // WIN_ACK offsets are in ORIGINAL image coordinates (verified byte-for-byte
    // against capture CRCs). The device orchestrates the two-part send itself:
    // first it requests img[490:] via windows with nextOffset=490,4410,8330,...
    // then it requests img[0:490] (JFIF header commit) via nextOffset=0.
    // We simply index jpegBytes[nextOffset:] for each window.
    log('Phase 9: Data transfer...')

    const totalChunks = Math.ceil(jpegBytes.length / chunkSize)
    let seq = seqCounter
    let sentChunks = 0
    const fileLabel = useDefaultImage ? 'captured_image.jpg' : (selectedFile?.name ?? 'image')

    log(`Total size: ${jpegBytes.length} bytes, ${totalChunks} chunks`)
    log(`0x1b ack body (${metaAck.body.length} bytes): ${toHex(metaAck.body)}`)

    // Enable auto-responder for cmd 0x20 (FILE_COMPLETE) as fast-path backup.
    fileCompleteAutoRespond = true
    fileCompleteHandled = false

    let totalBytesSent = 0

    // Helper to send a window of chunks at a given offset (into jpegBytes)
    const sendChunksAt = async (offset: number, winSize: number) => {
      let slot = 0
      let bytesSent = 0
      let chunksInWindow = 0
      while (bytesSent < winSize) {
        if (cancelRequested) throw new Error('Write cancelled.')
        const chunkOffset = offset + bytesSent
        if (chunkOffset >= jpegBytes.length) break

        const remaining = Math.min(winSize - bytesSent, jpegBytes.length - chunkOffset)
        const chunkLen = Math.min(chunkSize, remaining)
        const payload = jpegBytes.slice(chunkOffset, chunkOffset + chunkLen)

        const isCommitChunk = offset === 0 && winSize <= chunkSize
        if (isCommitChunk) {
          log(`Sending JFIF header commit chunk (slot=0, ${payload.length} bytes, first4=${toHex(payload.slice(0, 4))})`)
        }

        const crc = crc16xmodem(payload)
        const body = new Uint8Array(5 + payload.length)
        body[0] = seq & 0xff
        body[1] = 0x1d
        body[2] = slot & 0xff
        body[3] = (crc >> 8) & 0xff
        body[4] = crc & 0xff
        body.set(payload, 5)

        // Log diagnostic details for first and commit chunks
        if (sentChunks === 0) {
          log(`FIRST chunk: seq=${seq & 0xff} slot=${slot & 0xff} crc=0x${crc.toString(16).padStart(4, '0')} offset=${chunkOffset} len=${chunkLen}`)
          log(`  body header: ${toHex(body.slice(0, 10))}`)
          log(`  payload first8: ${toHex(payload.slice(0, 8))}`)
        }
        if (isCommitChunk) {
          log(`COMMIT chunk: seq=${seq & 0xff} slot=${slot & 0xff} crc=0x${crc.toString(16).padStart(4, '0')}`)
          log(`  body header: ${toHex(body.slice(0, 10))}`)
        }

        // Fire writes as fast as possible — queue without awaiting each one
        // to mimic the iOS app's sub-millisecond burst writes.
        // We await each write sequentially because Web Bluetooth serializes
        // writes internally, but we remove inter-chunk delays.
        await sendE87Frame(0x80, 0x01, body)

        sentChunks += 1
        totalBytesSent += chunkLen
        chunksInWindow += 1
        progress = Math.min(100, Math.round((sentChunks / totalChunks) * 100))
        progressLabel = `${fileLabel} — chunk ${sentChunks}/${totalChunks}`

        seq = (seq + 1) & 0xff
        slot = (slot + 1) & 0x07
        bytesSent += chunkLen

        // Only add delays for non-commit chunks when explicitly configured
        if (!isCommitChunk && interChunkDelayMs > 0) await sleep(interChunkDelayMs)
      }
      log(`Window done: sent ${chunksInWindow} chunks, ${bytesSent} bytes (total so far: ${totalBytesSent}/${jpegBytes.length})`)
    }

    // Check if the device uses windowed flow control by looking for
    // a WIN_ACK that arrives shortly after the 0x1b ack
    let useWindowing = false
    let firstWinAck: E87Frame | null = null
    try {
      firstWinAck = await waitForNotificationFrame(
        (f) => f.flag === 0x80 && f.cmd === 0x1d,
        2000, 'initial window ack (probing for flow control)'
      )
      useWindowing = true
    } catch {
      log('No window ack received — using streaming mode (no flow control).')
    }

    if (useWindowing && firstWinAck) {
      // ── Windowed mode: send chunks in windows, wait for ack between each ──
      log('Using windowed flow control.')
      let currentAck: E87Frame | null = firstWinAck
      let done = false

      while (!done) {
        if (cancelRequested) throw new Error('Write cancelled.')

        if (currentAck && currentAck.cmd === 0x1d && currentAck.body.length >= 8) {
          const ackSeq = currentAck.body[0]
          const ackStatus = currentAck.body[1]
          const winSize = (currentAck.body[2] << 8) | currentAck.body[3]
          const nextOffset = (currentAck.body[4] << 24) | (currentAck.body[5] << 16) | (currentAck.body[6] << 8) | currentAck.body[7]
          log(`Window ack #${ackSeq}: status=0x${ackStatus.toString(16)} winSize=${winSize} nextOffset=${nextOffset}`)

          if (ackStatus !== 0x00) {
            log(`WARNING: non-zero ack status 0x${ackStatus.toString(16)}`)
          }

          await sendChunksAt(nextOffset, winSize)

          // If this was the commit window (offset=0), log diagnostic info
          if (nextOffset === 0) {
            log(`Commit sent. totalBytesSent=${totalBytesSent}, fileSize=${jpegBytes.length}, match=${totalBytesSent === jpegBytes.length}`)
          }
        }

        // Wait for next window ack, FILE_COMPLETE, or session close.
        // Capture flow: ...WIN_ACK(offset=0) → commit chunk → cmd 0x20 → cmd 0x1c
        const frame = await waitForNotificationFrame(
          (f) => (f.flag === 0x80 && f.cmd === 0x1d) || f.cmd === 0x20 || f.cmd === 0x1c,
          15000, 'window ack, FILE_COMPLETE, or session close'
        )

        if (frame.cmd === 0x20 && frame.flag === 0xc0) {
          // FILE_COMPLETE from device — respond with path
          // Auto-responder may have already handled this; avoid double-response
          const deviceSeq20 = frame.body[0] ?? seq
          log(`Received FILE_COMPLETE cmd 0x20 (seq=${deviceSeq20}). Auto-responded: ${fileCompleteHandled}`)
          if (!fileCompleteHandled) {
            await sendE87Frame(0x00, 0x20, buildFilePathResponse(deviceSeq20))
            fileCompleteHandled = true
            log('Path response sent.')
          }
          log('Waiting for SESSION_CLOSE...')

          // Now wait for cmd 0x1c (SESSION_CLOSE)
          const closeFrame = await waitForNotificationFrame(
            (f) => f.cmd === 0x1c,
            15000, 'session close (cmd 0x1c)'
          )
          done = true
          await handleCompletion(closeFrame, seq)
          break
        }

        if (frame.cmd === 0x1c) {
          done = true
          await handleCompletion(frame, seq)
          break
        }

        currentAck = frame
      }
    } else {
      // ── Streaming mode: send tail then head, no flow control ──
      // Send img[490:] in 490-byte chunks, then img[0:490] as commit
      log('Streaming all chunks (tail then head)...')

      const headSize = Math.min(E87_DATA_CHUNK_SIZE, jpegBytes.length)
      const tailLen = jpegBytes.length - headSize
      const tailChunks = Math.ceil(tailLen / E87_DATA_CHUNK_SIZE)

      // Send tail chunks: img[490:]
      for (let i = 0; i < tailChunks; i++) {
        if (cancelRequested) throw new Error('Write cancelled.')
        const chunkOffset = headSize + i * E87_DATA_CHUNK_SIZE
        const end = Math.min(chunkOffset + E87_DATA_CHUNK_SIZE, jpegBytes.length)
        const payload = jpegBytes.slice(chunkOffset, end)
        const slot = i & 0x07

        const crc = crc16xmodem(payload)
        const body = new Uint8Array(5 + payload.length)
        body[0] = seq & 0xff
        body[1] = 0x1d
        body[2] = slot & 0xff
        body[3] = (crc >> 8) & 0xff
        body[4] = crc & 0xff
        body.set(payload, 5)

        await sendE87Frame(0x80, 0x01, body)
        sentChunks += 1
        progress = Math.min(100, Math.round((sentChunks / totalChunks) * 100))
        progressLabel = `${fileLabel} — chunk ${sentChunks}/${totalChunks}`
        seq = (seq + 1) & 0xff
        if (interChunkDelayMs > 0) await sleep(interChunkDelayMs)
      }

      // Send head (commit) chunk: img[0:490]
      {
        const payload = jpegBytes.slice(0, headSize)
        log(`Sending JFIF header commit chunk (slot=0, ${payload.length} bytes)`)
        const crc = crc16xmodem(payload)
        const body = new Uint8Array(5 + payload.length)
        body[0] = seq & 0xff
        body[1] = 0x1d
        body[2] = 0x00
        body[3] = (crc >> 8) & 0xff
        body[4] = crc & 0xff
        body.set(payload, 5)

        await sendE87Frame(0x80, 0x01, body)
        sentChunks += 1
        progress = 100
        progressLabel = `${fileLabel} — chunk ${sentChunks}/${totalChunks}`
        seq = (seq + 1) & 0xff
      }

      // Wait for completion: cmd 0x20 (FILE_COMPLETE) then cmd 0x1c (SESSION_CLOSE)
      log('All chunks sent. Waiting for completion...')
      try {
        for (let retries = 0; retries < 20; retries++) {
          const frame = await waitForNotificationFrame(
            (f) => (f.flag === 0x80 && f.cmd === 0x1d) || f.cmd === 0x20 || f.cmd === 0x1c,
            15000, 'FILE_COMPLETE or session close'
          )
          if (frame.cmd === 0x1d) {
            const ackStatus = frame.body.length >= 2 ? frame.body[1] : 0xff
            log(`Late window ack (status=0x${ackStatus.toString(16)}) — ignoring.`)
            continue
          }
          if (frame.cmd === 0x20 && frame.flag === 0xc0) {
            const deviceSeq20 = frame.body[0] ?? seq
            log(`Received FILE_COMPLETE cmd 0x20 (seq=${deviceSeq20}). Auto-responded: ${fileCompleteHandled}`)
            if (!fileCompleteHandled) {
              await sendE87Frame(0x00, 0x20, buildFilePathResponse(deviceSeq20))
              fileCompleteHandled = true
              log('Path response sent.')
            }
            log('Waiting for SESSION_CLOSE...')
            const closeFrame = await waitForNotificationFrame(
              (f) => f.cmd === 0x1c, 15000, 'session close (cmd 0x1c)'
            )
            await handleCompletion(closeFrame, seq)
            break
          }
          await handleCompletion(frame, seq)
          break
        }
      } catch { log('No completion handshake received (image may still be applied).') }
    }
  }

  async function handleCompletion(frame: E87Frame, seq: number): Promise<void> {
    const bodyHex = toHex(frame.body)
    const deviceSeq1c = frame.body[0] ?? seq
    const statusByte = frame.body.length >= 2 ? frame.body[1] : 0xff
    const statusNames: Record<number, string> = {
      0x00: 'SUCCESS', 0x01: 'UNKNOWN_ERROR', 0x02: 'BUSY',
      0x03: 'DATA_ERROR/CRC_FAIL', 0x04: 'TIMEOUT', 0x05: 'REJECTED',
    }
    const statusStr = statusNames[statusByte] ?? `0x${statusByte.toString(16)}`

    log(`Received SESSION_CLOSE cmd 0x${frame.cmd.toString(16)}, body: ${bodyHex}`)
    log(`  deviceSeq=${deviceSeq1c}, status=${statusStr} (0x${statusByte.toString(16)})`)
    log(`  cmd 0x20 auto-responded: ${fileCompleteHandled}`)

    if (statusByte !== 0x00) {
      log(`⚠️ Device reported error status ${statusStr}! Transfer may have failed.`)
    }

    // Disable auto-responder
    fileCompleteAutoRespond = false

    // Respond to cmd 0x1c (SESSION_CLOSE)
    // Capture shows: body = [0x00, deviceSeq]
    await sendE87Frame(0x00, 0x1c, Uint8Array.of(0x00, deviceSeq1c))
    log(`Sent cmd 0x1C response${statusByte === 0x00 ? '. Upload complete!' : ' (acknowledging error).'}`)
  }

  async function startUpload(): Promise<void> {
    if (!characteristic) {
      status = 'Not connected.'
      return
    }
    if (uploadMode === 'image' && !useDefaultImage && !selectedFile) {
      status = 'Select an image or use the default.'
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
    isWriting = true
    cancelRequested = false
    progress = 0
    progressLabel = 'Starting...'
    try {
      await writeFileE87()
      progress = 100
      status = 'Upload completed.'
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
  <p class="hint">Web Bluetooth uploader — two-part data send verified against packet capture.</p>

  <section class="panel">
    <div class="row buttons">
      <button on:click={connect} disabled={isConnecting || isWriting}>
        {isConnecting ? 'Connecting...' : 'Connect'}
      </button>
      <button on:click={disconnect} disabled={!server?.connected || isWriting}>Disconnect</button>
      <button class="secondary" on:click={cancelWrite} disabled={!isWriting}>Cancel</button>
    </div>
    <div class="status">Status: {status}</div>
    {#if batteryLevel !== null}
      <div class="status">Battery: {batteryLevel}% <span class="dim">({batteryUpdatedAt})</span></div>
    {/if}
  </section>

  <section class="panel">
    <!-- Upload mode tabs -->
    <div class="row buttons mode-tabs" style="margin-bottom:0.6rem">
      <button class:active={uploadMode === 'image'} on:click={() => uploadMode = 'image'} disabled={isWriting}>
        🖼 Image
      </button>
      <button class:active={uploadMode === 'images'} on:click={() => uploadMode = 'images'} disabled={isWriting}>
        🎞 Sequence
      </button>
      <button class:active={uploadMode === 'video'} on:click={() => uploadMode = 'video'} disabled={isWriting}>
        🎬 Video
      </button>
    </div>

    <!-- Single image mode -->
    {#if uploadMode === 'image'}
      <div class="image-source">
        <div class="row buttons" style="margin-bottom:0.5rem">
          <button class:active={useDefaultImage} on:click={selectDefaultImage} disabled={isWriting}>
            Default (captured)
          </button>
          <label class="file-btn" class:active={!useDefaultImage}>
            Custom image…
            <input type="file" accept="image/*" on:change={setFile} disabled={isWriting} style="display:none" />
          </label>
        </div>
      </div>
      {#if previewUrl}
        <div class="preview">
          <img src={previewUrl} alt="Image to send" />
        </div>
      {/if}

    <!-- Image sequence mode -->
    {:else if uploadMode === 'images'}
      <div class="image-source">
        <label class="file-btn" class:active={selectedFiles.length > 0}>
          Select images…
          <input type="file" accept="image/*" multiple on:change={setMultipleFiles} disabled={isWriting} style="display:none" />
        </label>
        {#if selectedFiles.length > 0}
          <span class="dim" style="margin-left:0.5rem">{selectedFiles.length} images selected</span>
        {/if}
      </div>
      {#if previewUrl && selectedFiles.length > 0}
        <div class="preview">
          <img src={previewUrl} alt="First image in sequence" />
          <p class="dim" style="font-size:0.8rem;margin:0.3rem 0 0">Preview: first of {selectedFiles.length}</p>
        </div>
      {/if}

    <!-- Video mode -->
    {:else if uploadMode === 'video'}
      <div class="image-source">
        <label class="file-btn" class:active={selectedFile !== null && !useDefaultImage}>
          Select video…
          <input type="file" accept="video/*" on:change={setVideoFile} disabled={isWriting} style="display:none" />
        </label>
        {#if selectedFile && !useDefaultImage}
          <span class="dim" style="margin-left:0.5rem">{selectedFile.name}</span>
        {/if}
      </div>
      {#if previewUrl && selectedFile && !useDefaultImage}
        <div class="preview">
          <!-- svelte-ignore a11y_media_has_caption -->
          <video src={previewUrl} style="max-width:180px;max-height:180px;border:1px solid #334;border-radius:6px" controls muted></video>
        </div>
      {/if}
      <div class="settings">
        <label>
          <span>Frame rate (fps)</span>
          <input type="number" min="1" max="30" step="1" bind:value={videoFps} disabled={isWriting} />
        </label>
      </div>
    {/if}

    <div class="settings">
      <label>
        <span>Inter-chunk delay (ms)</span>
        <input type="number" min="0" max="1000" step="1" bind:value={interChunkDelayMs} disabled={isWriting} />
      </label>
    </div>

    <div class="row buttons">
      <button on:click={startUpload} disabled={!server?.connected || isWriting}>
        {isWriting ? 'Uploading…' : 'Upload'}
      </button>
    </div>

    <div class="progress-wrap">
      <div class="progress" style={`width:${progress}%`}></div>
    </div>
    {#if progressLabel}
      <p class="progress-label">{progressLabel}</p>
    {/if}
  </section>

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
    margin: 0;
    font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: linear-gradient(180deg, #09111d 0%, #0f1d34 100%);
    color: #e6f1ff;
    min-height: 100vh;
  }
  .app { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
  h1 { margin: 0 0 0.25rem; font-size: 1.6rem; }
  .hint { margin: 0 0 0.8rem; color: #8badd4; font-size: 0.88rem; }
  .panel {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.8rem;
  }
  .row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.6rem; }
  .mode-tabs { border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.6rem; }
  .status { font-weight: 600; color: #d4e6ff; margin-bottom: 0.15rem; }
  .dim { font-weight: 400; color: #7a9dc5; }
  .settings {
    display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap;
  }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #b0cce8; }
  input, button {
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.07);
    color: #f3f9ff;
    padding: 0.5rem 0.7rem;
    font-size: 0.9rem;
  }
  input[type="number"] { width: 90px; }
  button { cursor: pointer; font-weight: 600; }
  button:hover:not(:disabled) { border-color: rgba(129, 178, 255, 0.9); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.secondary { background: rgba(255, 100, 100, 0.12); }
  button.active, .file-btn.active {
    border-color: rgba(129, 178, 255, 0.9);
    background: rgba(129, 178, 255, 0.14);
  }
  .file-btn {
    display: inline-flex; align-items: center;
    border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.07); color: #f3f9ff;
    padding: 0.5rem 0.7rem; cursor: pointer; font-weight: 600; font-size: 0.9rem;
  }
  .file-btn:hover { border-color: rgba(129, 178, 255, 0.9); }
  .preview { margin: 0.5rem 0; }
  .preview img { max-width: 180px; max-height: 180px; border: 1px solid #334; border-radius: 6px; }
  .progress-wrap {
    width: 100%; height: 10px; border-radius: 99px; overflow: hidden;
    background: rgba(255, 255, 255, 0.1); margin-top: 0.5rem;
  }
  .progress {
    height: 100%; background: linear-gradient(90deg, #6be4ff, #6f95ff);
    transition: width 100ms ease;
  }
  .progress-label { margin: 0.4rem 0 0; color: #9ec0e8; font-size: 0.85rem; }
  .logs h2 { margin: 0 0 0.3rem; font-size: 0.95rem; }
  .logs ul {
    list-style: none; padding: 0; margin: 0;
    max-height: 220px; overflow: auto;
  }
  .logs li {
    color: #b8d4f0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.8rem; line-height: 1.35; padding: 1px 0;
  }
</style>
