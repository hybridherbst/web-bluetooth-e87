/**
 * E87 / Jieli RCSP BLE protocol module.
 *
 * Handles device connection, auth handshake, characteristic discovery,
 * and the windowed file upload state machine.
 */

import { getRandomAuthData, getEncryptedAuthData } from '../jl-auth'
import { sleep, toHex, hexToBytes, crc16xmodem, formatBytes } from './utils'

// ─── Constants ───

export const E87_DATA_CHUNK_SIZE = 490

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

// ─── Types ───

export type E87Frame = {
  flag: number
  cmd: number
  length: number
  body: Uint8Array
}

export type UploadMode = 'image' | 'images' | 'video' | 'pattern'

export type UploadProgressCallback = (
  bytesSent: number,
  totalBytes: number,
  chunksSent: number,
  totalChunks: number,
) => void

// ─── Frame parsing / building ───

export function parseE87Frame(data: Uint8Array): E87Frame | null {
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

export function buildE87Frame(flag: number, cmd: number, body: Uint8Array): Uint8Array {
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

// ─── Notification queue helpers ───

function queuePreview(queue: Uint8Array[]): string {
  const tail = queue.slice(Math.max(0, queue.length - 6))
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
  queue: Uint8Array[],
  predicate: (frame: E87Frame) => boolean,
  timeoutMs = 8000,
  waitLabel = 'matching E87 frame',
  log?: (msg: string) => void,
): Promise<E87Frame> {
  log?.(`Waiting for ${waitLabel}...`)
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    for (let i = 0; i < queue.length; i += 1) {
      const raw = queue[i]
      const frame = parseE87Frame(raw)
      if (!frame) continue
      if (predicate(frame)) {
        queue.splice(i, 1)
        return frame
      }
    }
    await sleep(20)
  }
  throw new Error(`Timeout waiting for ${waitLabel}. Recent notifications: ${queuePreview(queue)}`)
}

async function waitForRawNotification(
  queue: Uint8Array[],
  predicate: (raw: Uint8Array) => boolean,
  timeoutMs = 2000,
  waitLabel = 'matching raw notification',
  log?: (msg: string) => void,
): Promise<Uint8Array> {
  log?.(`Waiting for ${waitLabel}...`)
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    for (let i = 0; i < queue.length; i += 1) {
      const raw = queue[i]
      if (predicate(raw)) {
        queue.splice(i, 1)
        return raw
      }
    }
    await sleep(20)
  }
  throw new Error(`Timeout waiting for ${waitLabel}. Recent notifications: ${queuePreview(queue)}`)
}

// ─── Write helpers ───

async function writeChunkTo(target: BluetoothRemoteGATTCharacteristic, chunk: Uint8Array): Promise<void> {
  const outbound = Uint8Array.from(chunk)
  if (target.properties.writeWithoutResponse && target.writeValueWithoutResponse) {
    await target.writeValueWithoutResponse(outbound)
    return
  }
  await target.writeValue(outbound)
}

// ─── Characteristic discovery ───

async function findCharacteristics(
  targetServer: BluetoothRemoteGATTServer,
  log?: (msg: string) => void,
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

  // Try a full primary-services enumeration first (fast path). On Windows
  // the stack can be flaky, so if that fails or returns nothing we fall back
  // to querying the specific candidate services one-by-one.
  let services: BluetoothRemoteGATTService[] = []
  try {
    const primaryServices = await targetServer.getPrimaryServices()
    services = [...primaryServices]
    for (const primary of primaryServices) {
      try {
        const included = await primary.getIncludedServices()
        if (included.length) {
          log?.(`Primary ${primary.uuid} has ${included.length} included service(s).`)
          services.push(...included)
        }
      } catch { /* ignore */ }
    }
  } catch (err) {
    log?.(`Primary services enumeration failed: ${(err as Error).message} — falling back to per-candidate lookup`)
  }

  // Fallback: query candidate service UUIDs individually (more robust on Win)
  if (!services.length) {
    for (const candidate of SERVICE_CANDIDATES) {
      try {
        const s = await targetServer.getPrimaryService(candidate as BluetoothServiceUUID)
        services.push(s)
        log?.(`Found service candidate ${s.uuid}`)
      } catch { /* ignore - candidate not present */ }
    }
  }

  // Dedupe discovered services
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
    log?.(`Service ${service.uuid} exposes ${chars.length} characteristic(s).`)
    for (const c of chars) {
      const p = c.properties
      if (p.write || p.writeWithoutResponse) {
        writable.push({ char: c, serviceUuid: service.uuid })
        log?.(`  writable: ${c.uuid} (write=${Boolean(p.write)}, wnr=${Boolean(p.writeWithoutResponse)})`)
      }
      if (p.notify || p.indicate) {
        notifiable.push({ char: c, serviceUuid: service.uuid })
        log?.(`  notify: ${c.uuid} (notify=${Boolean(p.notify)}, indicate=${Boolean(p.indicate)})`)
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

  log?.(`Selected write: ${selectedWrite.char.uuid}`)
  log?.(`Selected control: ${selectedControl.char.uuid}`)
  for (const n of selectedNotify) log?.(`Selected notify: ${n.char.uuid}`)

  return {
    write: selectedWrite.char,
    control: selectedControl.char,
    notify: selectedNotify.map((n) => n.char),
  }
}

// ─── BLE connection state ───

export interface E87Connection {
  device: BluetoothDevice
  server: BluetoothRemoteGATTServer
  writeChar: BluetoothRemoteGATTCharacteristic
  controlChar: BluetoothRemoteGATTCharacteristic
  notifyChars: BluetoothRemoteGATTCharacteristic[]
  batteryLevel: number | null
  batteryUpdatedAt: string
  notificationQueue: Uint8Array[]
  onNotification: (event: Event) => void
}

export async function connectE87(log?: (msg: string) => void): Promise<E87Connection> {
  if (!('bluetooth' in navigator)) {
    throw new Error('Web Bluetooth is not available in this browser.')
  }

  const device = await navigator.bluetooth.requestDevice({
    filters: [{ namePrefix: 'E87' }],
    optionalServices: SERVICE_CANDIDATES,
  })

  // GATT connect + service discovery can fail on Windows (and sometimes macOS).
  //
  // On Windows, Chrome historically used the cached-mode WinRT
  // GetGattServicesAsync() API which causes the OS BLE stack to drop the
  // connection before GATT discovery completes (Chromium #376885284, fixed in
  // Chrome ≈132 via uncached-mode discovery).  Older Chrome versions still
  // exhibit this: the GATT server reports "connected" momentarily but the
  // underlying radio link is torn down within a few hundred ms.
  //
  // The correct approach (per the official Chrome automatic-reconnect sample
  // and the Chromium BLE team) is:
  //
  //   1.  Call device.gatt.connect() and let the returned promise settle —
  //       do NOT insert a sleep() between connect() and service discovery.
  //       connect() itself is the async handshake; adding a delay only widens
  //       the window for Windows to tear down the link.
  //
  //   2.  Immediately proceed to service/characteristic discovery.  If the
  //       connection was dropped (Windows cached-mode bug or transient radio
  //       issue) this will throw, which we catch and retry.
  //
  //   3.  Use exponential back-off between retries.  Windows needs ~7 s for
  //       its internal BLE cleanup before a fresh connect attempt can succeed.
  //
  //   4.  Fully disconnect before each retry so the OS can release the old
  //       GATT session resources.

  const isWindows = typeof navigator !== 'undefined' && /Windows/i.test(navigator.userAgent)
  const MAX_ATTEMPTS = isWindows ? 5 : 3
  // Exponential back-off base delay (ms).  Windows needs longer gaps because
  // the WinRT BLE stack holds resources for ~7 s after a failed attempt.
  const BASE_DELAY_MS = isWindows ? 2000 : 500

  let server: BluetoothRemoteGATTServer | null = null
  let chars: Awaited<ReturnType<typeof findCharacteristics>> | null = null

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    // Track whether the GATT server fires a disconnect event during this attempt
    let disconnectedDuringAttempt = false

    try {
      log?.(`GATT connect attempt ${attempt}/${MAX_ATTEMPTS}...`)

      // Ensure any stale connection from a previous attempt is fully torn down
      // before asking the OS to connect again.
      if (server) {
        try { server.disconnect() } catch { /* ignore */ }
        server = null
      }

      const onDisconnect = () => {
        disconnectedDuringAttempt = true
        log?.('GATT server reported disconnected event during connect attempt.')
      }

      // ── Step 1: connect() ──
      // The promise returned by connect() resolves once the BLE link is
      // established.  Do NOT add a sleep before service discovery.
      server = (await device.gatt?.connect()) ?? null
      if (!server) throw new Error('No GATT server available.')

      try { server.addEventListener('gattserverdisconnected', onDisconnect) } catch { /* ignore */ }

      // ── Step 2: immediate service / characteristic discovery ──
      // If the Windows cached-mode bug strikes, this will throw because the
      // server is already gone.  That is the correct signal to retry — much
      // more reliable than checking server.connected after an arbitrary sleep.
      chars = await findCharacteristics(server, log)

      try { server.removeEventListener('gattserverdisconnected', onDisconnect) } catch { /* ignore */ }

      // Guard: the discovery call above may have "succeeded" on Windows by
      // returning stale cached data even though the radio link dropped.
      if (disconnectedDuringAttempt || !server.connected) {
        throw new Error('GATT server disconnected during service discovery.')
      }

      log?.(`GATT connected on attempt ${attempt}.`)
      break
    } catch (err) {
      const msg = (err as Error).message
      log?.(`GATT attempt ${attempt} failed: ${msg}`)

      // Tear down cleanly so the OS can release BLE resources
      try { server?.disconnect() } catch { /* ignore */ }
      server = null
      chars = null

      if (attempt === MAX_ATTEMPTS) {
        throw new Error(`Failed to connect after ${MAX_ATTEMPTS} attempts: ${msg}`)
      }

      // Exponential back-off: BASE × 2^(attempt-1)
      // Windows: 2 s → 4 s → 8 s → 16 s  (gives the WinRT stack time to
      //          release the previous GATT session)
      // macOS:   0.5 s → 1 s → 2 s
      const backoff = BASE_DELAY_MS * Math.pow(2, attempt - 1)
      log?.(`Retrying in ${(backoff / 1000).toFixed(1)}s...`)
      await sleep(backoff)
    }
  }

  if (!server || !chars) throw new Error('GATT connection failed.')

  const notificationQueue: Uint8Array[] = []

  let batteryLevel: number | null = null
  let batteryUpdatedAt = ''
  try {
    const batteryService = await server.getPrimaryService(0x180f)
    const batteryChar = await batteryService.getCharacteristic(0x2a19)
    const value = await batteryChar.readValue()
    batteryLevel = value.getUint8(0)
    batteryUpdatedAt = new Date().toLocaleTimeString()
    log?.(`Battery: ${batteryLevel}%`)
  } catch {
    batteryLevel = null
    batteryUpdatedAt = ''
  }

  const onNotification = (event: Event) => {
    const target = event.target as BluetoothRemoteGATTCharacteristic
    const value = target.value
    if (!value) return
    const raw = new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength))
    notificationQueue.push(raw)
    if (notificationQueue.length > 200) notificationQueue.shift()
    // Log incoming data (mirrors the original unified handler)
    const frame = parseE87Frame(raw)
    if (frame) {
      log?.(`RX frame flag=0x${frame.flag.toString(16)} cmd=0x${frame.cmd.toString(16)} len=${frame.length}`)
    } else {
      log?.(`RX notify (${raw.length} bytes): ${toHex(raw.slice(0, Math.min(24, raw.length)))}`)
    }
  }

  for (const c of chars.notify) {
    c.addEventListener('characteristicvaluechanged', onNotification)
    await c.startNotifications()
  }
  log?.(`Notification channel ready (${chars.notify.length} characteristic(s)).`)

  return {
    device,
    server,
    writeChar: chars.write,
    controlChar: chars.control,
    notifyChars: chars.notify,
    batteryLevel,
    batteryUpdatedAt,
    notificationQueue,
    onNotification,
  }
}

export async function disconnectE87(conn: E87Connection, log?: (msg: string) => void): Promise<void> {
  for (const c of conn.notifyChars) {
    try {
      c.removeEventListener('characteristicvaluechanged', conn.onNotification)
      await c.stopNotifications()
    } catch { /* ignore */ }
  }
  if (conn.server?.connected) conn.server.disconnect()
  conn.notificationQueue.length = 0
  log?.('Disconnected.')
}

// ─── File path response builder ───

function buildFilePathResponse(deviceSeq: number, uploadMode: UploadMode): Uint8Array {
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

function randomTempName(): string {
  const n = Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0')
  return `${n}.tmp`
}

// ─── Upload state machine ───

export interface UploadOptions {
  conn: E87Connection
  payload: Uint8Array
  uploadMode: UploadMode
  interChunkDelayMs: number
  cancelRequested: () => boolean
  onProgress: UploadProgressCallback
  log: (msg: string) => void
}

export async function writeFileE87(opts: UploadOptions): Promise<void> {
  const { conn, payload: jpegBytes, uploadMode, interChunkDelayMs, cancelRequested, onProgress, log } = opts
  const { writeChar: characteristic, controlChar: controlCharacteristic, notificationQueue } = conn

  const isJpeg = jpegBytes[0] === 0xff && jpegBytes[1] === 0xd8
  const isAvi = jpegBytes[0] === 0x52 && jpegBytes[1] === 0x49 && jpegBytes[2] === 0x46 && jpegBytes[3] === 0x46
  const fmtLabel = isJpeg ? 'JPEG' : isAvi ? 'AVI' : 'raw data'
  log(`Prepared payload: ${formatBytes(jpegBytes.length)} (${fmtLabel}).`)

  const writeChunk = (chunk: Uint8Array) => writeChunkTo(characteristic, chunk)
  const sendE87Frame = async (flag: number, cmd: number, body: Uint8Array) => {
    const frame = buildE87Frame(flag, cmd, body)
    log(`TX frame flag=0x${flag.toString(16)} cmd=0x${cmd.toString(16)} len=${body.length}`)
    await writeChunk(frame)
  }

  const waitFrame = (
    pred: (f: E87Frame) => boolean,
    timeout = 8000,
    label = 'matching E87 frame',
  ) => waitForNotificationFrame(notificationQueue, pred, timeout, label, log)

  const waitRaw = (
    pred: (raw: Uint8Array) => boolean,
    timeout = 2000,
    label = 'matching raw notification',
  ) => waitForRawNotification(notificationQueue, pred, timeout, label, log)

  let fileCompleteAutoRespond = false
  let fileCompleteHandled = false

  // Auto-responder for cmd 0x20 (FILE_COMPLETE) — the device has a tight
  // timeout (~100ms) so we respond directly in the event handler.
  const autoResponder = (event: Event) => {
    if (!fileCompleteAutoRespond || fileCompleteHandled) return
    const target = event.target as BluetoothRemoteGATTCharacteristic
    const value = target.value
    if (!value) return
    const raw = new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength))
    const frame = parseE87Frame(raw)
    if (frame && frame.cmd === 0x20 && frame.flag === 0xc0) {
      fileCompleteHandled = true
      const deviceSeq = frame.body[0] ?? 0
      const respBody = buildFilePathResponse(deviceSeq, uploadMode)
      const respFrame = buildE87Frame(0x00, 0x20, respBody)
      log(`AUTO-RESPOND cmd 0x20: seq=${deviceSeq}, sending path response (${respFrame.length} bytes)`)
      characteristic.writeValueWithoutResponse(respFrame).then(() => {
        log('cmd 0x20 auto-response sent successfully.')
      }).catch((err: unknown) => {
        log(`cmd 0x20 auto-response failed: ${(err as Error).message}`)
      })
    }
  }

  // Attach auto-responder alongside the queue listener
  for (const c of conn.notifyChars) {
    c.addEventListener('characteristicvaluechanged', autoResponder)
  }

  try {
    let seqCounter = 0x00

    // ── AUTH ──
    log('Auth: Starting Jieli RCSP crypto handshake...')
    const randomAuthData = getRandomAuthData()
    log(`Auth TX: [0x00, rand*16] = ${toHex(randomAuthData)}`)
    await writeChunk(randomAuthData)

    const deviceResponse = await waitRaw(
      (raw) => raw.length === 17 && raw[0] === 0x01,
      5000, 'auth device response [0x01, encrypted*16]'
    )
    log(`Auth RX: ${toHex(deviceResponse)}`)

    log('Auth TX: [0x02, pass]')
    await writeChunk(Uint8Array.of(0x02, 0x70, 0x61, 0x73, 0x73))

    const deviceChallenge = await waitRaw(
      (raw) => raw.length === 17 && raw[0] === 0x00,
      5000, 'auth device challenge [0x00, challenge*16]'
    )
    log(`Auth RX challenge: ${toHex(deviceChallenge)}`)

    const encryptedResponse = getEncryptedAuthData(deviceChallenge)
    log(`Auth TX encrypted: ${toHex(encryptedResponse)}`)
    await writeChunk(encryptedResponse)

    const authConfirm = await waitRaw(
      (raw) => raw.length >= 5 && raw[0] === 0x02 && raw[1] === 0x70 && raw[2] === 0x61 && raw[3] === 0x73 && raw[4] === 0x73,
      5000, 'auth pass confirmation'
    )
    log(`Auth SUCCESS: ${toHex(authConfirm)}`)

    // ── PHASE 1: cmd 0x06 ──
    log('Phase 1: cmd 0x06 (reset auth flag)...')
    await sendE87Frame(0xc0, 0x06, Uint8Array.of(0x02, 0x00, 0x01))
    seqCounter = 0x01

    try { await writeChunkTo(controlCharacteristic, hexToBytes('9EBD 0B60 0D00 03')) } catch { /* best-effort */ }
    try {
      await waitFrame((f) => f.cmd === 0x06, 3000, 'ack cmd 0x06')
      log('cmd 0x06 acked.')
    } catch { log('cmd 0x06 ack not received (continuing).') }

    // ── PHASE 2: FD02 control writes ──
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

    // ── PHASE 3: cmd 0x03 ──
    try {
      log('Phase 3: cmd 0x03 (best-effort)...')
      await sendE87Frame(0xc0, 0x03, Uint8Array.of(seqCounter, 0xff, 0xff, 0xff, 0xff, 0x01))
      seqCounter += 1
      await writeChunkTo(controlCharacteristic, hexToBytes('9ED3 0BC6 0100 01'))
      await sleep(20)
      await writeChunkTo(controlCharacteristic, hexToBytes('9E30 0820 0200 FF07'))
      await waitFrame((f) => f.cmd === 0x03, 3000, 'ack cmd 0x03')
    } catch { log('cmd 0x03 not acked (continuing).') }

    // ── PHASE 4: cmd 0x07 ──
    try {
      log('Phase 4: cmd 0x07 (best-effort)...')
      await sendE87Frame(0xc0, 0x07, Uint8Array.of(seqCounter, 0xff, 0xff, 0xff, 0xff, 0xff))
      seqCounter += 1
      await writeChunkTo(controlCharacteristic, hexToBytes('9E2B 08FF 0200 2200'))
      await sleep(40)
      await writeChunkTo(controlCharacteristic, hexToBytes('9E2D 08FF 0200 2400'))
      await waitFrame((f) => f.cmd === 0x07, 3000, 'ack cmd 0x07')
    } catch { log('cmd 0x07 not acked (continuing).') }

    // ── PHASE 5: FD02 bootstrap ──
    log('Phase 5: FD02 bootstrap...')
    await writeChunkTo(controlCharacteristic, hexToBytes('9EB5 0B29 0100 80'))
    await sleep(400)
    await writeChunkTo(controlCharacteristic, hexToBytes('9ED3 0BC6 0100 01'))
    try {
      await waitRaw(
        (raw) => raw.length >= 5 && raw[0] === 0x9e && (raw[3] === 0xc7 || raw[2] === 0xc7),
        3000, 'FD01 device info (C7)'
      )
    } catch { log('FD01 C7 not observed (continuing).') }
    await writeChunkTo(controlCharacteristic, hexToBytes('9EF4 0BDC 0100 0C'))
    try {
      await waitRaw(
        (raw) => raw.length >= 4 && raw[0] === 0x9e && raw[1] === 0xe6,
        3000, 'FD03 ready signal (9EE6)'
      )
      log('Device ready signal received.')
    } catch { log('FD03 ready signal not observed (continuing).') }

    // ── PHASE 6: cmd 0x21 ──
    log('Phase 6: cmd 0x21 (begin upload)...')
    await sendE87Frame(0xc0, 0x21, Uint8Array.of(seqCounter, 0x00))
    seqCounter += 1
    await waitFrame((f) => f.cmd === 0x21, 8000, 'ack cmd 0x21')

    // ── PHASE 7: cmd 0x27 ──
    log('Phase 7: cmd 0x27 (transfer params)...')
    await sendE87Frame(0xc0, 0x27, Uint8Array.of(seqCounter, 0x00, 0x00, 0x00, 0x00, 0x02, 0x01))
    seqCounter += 1
    await waitFrame((f) => f.cmd === 0x27, 8000, 'ack cmd 0x27')

    // ── PHASE 8: cmd 0x1b (file metadata) ──
    log('Phase 8: cmd 0x1b (file metadata)...')
    const fileSize = jpegBytes.length
    const tempName = randomTempName()
    const nameBytes = new TextEncoder().encode(tempName)

    const fileCrc = crc16xmodem(jpegBytes)
    log(`Whole-file CRC-16 XMODEM: 0x${fileCrc.toString(16).padStart(4, '0')}`)

    const metaBody = new Uint8Array(3 + 2 + 4 + nameBytes.length + 1)
    metaBody[0] = seqCounter
    seqCounter += 1
    metaBody[1] = (fileSize >> 24) & 0xff
    metaBody[2] = (fileSize >> 16) & 0xff
    metaBody[3] = (fileSize >> 8) & 0xff
    metaBody[4] = fileSize & 0xff
    metaBody[5] = (fileCrc >> 8) & 0xff
    metaBody[6] = fileCrc & 0xff
    metaBody[7] = Math.random() * 256 | 0
    metaBody[8] = Math.random() * 256 | 0
    metaBody.set(nameBytes, 9)
    metaBody[metaBody.length - 1] = 0x00

    await sendE87Frame(0xc0, 0x1b, metaBody)
    const metaAck = await waitFrame((f) => f.cmd === 0x1b, 8000, 'ack cmd 0x1b')

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
    log('Phase 9: Data transfer...')

    const totalChunks = Math.ceil(jpegBytes.length / chunkSize)
    let seq = seqCounter
    let sentChunks = 0

    log(`Total size: ${formatBytes(jpegBytes.length)}, ${totalChunks} chunks`)

    fileCompleteAutoRespond = true
    fileCompleteHandled = false

    let totalBytesSent = 0

    const sendChunksAt = async (offset: number, winSize: number) => {
      let slot = 0
      let bytesSent = 0
      let chunksInWindow = 0
      while (bytesSent < winSize) {
        if (cancelRequested()) throw new Error('Write cancelled.')
        const chunkOffset = offset + bytesSent
        if (chunkOffset >= jpegBytes.length) break

        const remaining = Math.min(winSize - bytesSent, jpegBytes.length - chunkOffset)
        const chunkLen = Math.min(chunkSize, remaining)
        const payload = jpegBytes.slice(chunkOffset, chunkOffset + chunkLen)

        const isCommitChunk = offset === 0 && winSize <= chunkSize

        const crc = crc16xmodem(payload)
        const body = new Uint8Array(5 + payload.length)
        body[0] = seq & 0xff
        body[1] = 0x1d
        body[2] = slot & 0xff
        body[3] = (crc >> 8) & 0xff
        body[4] = crc & 0xff
        body.set(payload, 5)

        if (sentChunks === 0) {
          log(`FIRST chunk: seq=${seq & 0xff} slot=${slot & 0xff} crc=0x${crc.toString(16).padStart(4, '0')} offset=${chunkOffset} len=${chunkLen}`)
        }
        if (isCommitChunk) {
          log(`COMMIT chunk: seq=${seq & 0xff} slot=${slot & 0xff} crc=0x${crc.toString(16).padStart(4, '0')}`)
        }

        await sendE87Frame(0x80, 0x01, body)

        sentChunks += 1
        totalBytesSent += chunkLen
        chunksInWindow += 1
        onProgress(totalBytesSent, jpegBytes.length, sentChunks, totalChunks)

        seq = (seq + 1) & 0xff
        slot = (slot + 1) & 0x07
        bytesSent += chunkLen

        if (!isCommitChunk && interChunkDelayMs > 0) await sleep(interChunkDelayMs)
      }
      log(`Window done: sent ${chunksInWindow} chunks, ${formatBytes(bytesSent)} (total: ${formatBytes(totalBytesSent)}/${formatBytes(jpegBytes.length)})`)
    }

    const handleCompletion = async (frame: E87Frame): Promise<void> => {
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

      fileCompleteAutoRespond = false

      await sendE87Frame(0x00, 0x1c, Uint8Array.of(0x00, deviceSeq1c))
      log(`Sent cmd 0x1C response${statusByte === 0x00 ? '. Upload complete!' : ' (acknowledging error).'}`)
    }

    // The device ALWAYS sends a window ack (flag=0x80, cmd=0x1d) to start
    // the windowed transfer.  Previous code had a 2 s timeout here and fell
    // back to a "streaming mode" that blasted all frames immediately with
    // no flow control — that was wrong and the root cause of the burst bug.
    //
    // Give the device a generous timeout (matches other ACK waits) and if
    // it still doesn't arrive, abort cleanly rather than corrupt the
    // transfer with an uncontrolled dump.
    let firstWinAck: E87Frame
    try {
      firstWinAck = await waitFrame(
        (f) => f.flag === 0x80 && f.cmd === 0x1d,
        10000, 'initial window ack (windowed flow control)'
      )
    } catch {
      throw new Error(
        'Device did not send the initial window ACK within 10 s — cannot start data transfer. ' +
        'Please retry the upload.'
      )
    }

    {
      log('Using windowed flow control.')
      let currentAck: E87Frame | null = firstWinAck
      let done = false

      while (!done) {
        if (cancelRequested()) throw new Error('Write cancelled.')

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

          if (nextOffset === 0) {
            log(`Commit sent. totalBytesSent=${formatBytes(totalBytesSent)}, fileSize=${formatBytes(jpegBytes.length)}`)
          }
        }

        const frame = await waitFrame(
          (f) => (f.flag === 0x80 && f.cmd === 0x1d) || f.cmd === 0x20 || f.cmd === 0x1c,
          15000, 'window ack, FILE_COMPLETE, or session close'
        )

        if (frame.cmd === 0x20 && frame.flag === 0xc0) {
          const deviceSeq20 = frame.body[0] ?? seq
          log(`Received FILE_COMPLETE cmd 0x20 (seq=${deviceSeq20}). Auto-responded: ${fileCompleteHandled}`)
          if (!fileCompleteHandled) {
            await sendE87Frame(0x00, 0x20, buildFilePathResponse(deviceSeq20, uploadMode))
            fileCompleteHandled = true
            log('Path response sent.')
          }
          log('Waiting for SESSION_CLOSE...')

          const closeFrame = await waitFrame(
            (f) => f.cmd === 0x1c,
            15000, 'session close (cmd 0x1c)'
          )
          done = true
          await handleCompletion(closeFrame)
          break
        }

        if (frame.cmd === 0x1c) {
          done = true
          await handleCompletion(frame)
          break
        }

        currentAck = frame
      }
    }
  } finally {
    // Clean up auto-responder
    for (const c of conn.notifyChars) {
      c.removeEventListener('characteristicvaluechanged', autoResponder)
    }
  }
}
