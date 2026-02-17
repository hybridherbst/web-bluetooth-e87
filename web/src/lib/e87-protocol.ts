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
  batteryChar: BluetoothRemoteGATTCharacteristic | null
  isAuthenticated: boolean
  rcspSeq: number
  qixSeq: number
  notificationQueue: Uint8Array[]
  onNotification: (event: Event) => void
}

export interface E87BatteryReading {
  level: number | null
  updatedAt: string
}

export interface E87SmallFileEntry {
  type: number
  typeName: string
  id: number
  size: number
}

export interface E87SmallFileReadResult {
  entry: E87SmallFileEntry
  data: Uint8Array
  crc16: number | null
}

export interface E87FileBrowseEntry {
  name: string
  isFolder: boolean
  sizeBytes: number
  cluster: number
  rawHex: string
}

export interface E87TargetFeatureMapResult {
  mask: number
  raw: string
}

export interface E87TargetInfoResult {
  requestMask: number
  requestPlatform: number
  raw: string
  payload: string
  attrs: Array<{
    type: number
    name: string
    dataHex: string
    length: number
    decoded?: string
  }>
}

export interface E87SysInfoAttr {
  type: number
  name: string
  dataHex: string
  length: number
  decoded?: string
}

export interface E87SysInfoResult {
  function: number
  raw: string
  attrs: E87SysInfoAttr[]
}

const TARGET_INFO_ATTR_NAMES: Record<number, string> = {
  0: 'protocol_version',
  1: 'power_up_sys_info',
  2: 'edr_addr',
  3: 'platform',
  4: 'function_info',
  5: 'firmware_info',
  6: 'sdk_type',
  7: 'uboot_version',
  8: 'support_double_backup',
  9: 'mandatory_upgrade_flag',
  10: 'vid_pid',
  11: 'auth_key',
  12: 'project_code',
  13: 'protocol_mtu',
  14: 'allow_connect',
  16: 'name',
  17: 'connect_ble_only',
  18: 'peripherals_support',
  19: 'dev_support_func',
  20: 'recode_file_transfer',
  21: 'file_transfer',
  31: 'custom_ver',
}

const PUBLIC_SYSINFO_ATTR_NAMES: Record<number, string> = {
  0: 'battery',
  1: 'volume',
  2: 'music_dev_status',
  3: 'err',
  4: 'eq',
  5: 'file_type',
  6: 'cur_mode_type',
  7: 'light',
  8: 'fm_tx',
  9: 'emitter_mode',
  10: 'emitter_connect_status',
  11: 'high_bass',
  12: 'eq_preset_value',
  13: 'current_noise_mode',
  14: 'all_noise_mode',
  15: 'phone_status',
  16: 'fixed_len_data_fun',
  17: 'sound_card_eq_freq',
  18: 'sound_card_eq_gain',
  19: 'sound_card',
}

const SMALL_FILE_TYPES: Array<{ type: number; name: string }> = [
  { type: 1, name: 'contacts' },
  { type: 2, name: 'sports_record' },
  { type: 3, name: 'heart_rate' },
  { type: 4, name: 'blood_oxygen' },
  { type: 5, name: 'sleep' },
  { type: 6, name: 'message_sync' },
  { type: 7, name: 'weather' },
  { type: 8, name: 'call_log' },
  { type: 9, name: 'step' },
]

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
  let batteryChar: BluetoothRemoteGATTCharacteristic | null = null
  try {
    const batteryService = await server.getPrimaryService(0x180f)
    batteryChar = await batteryService.getCharacteristic(0x2a19)
    const value = await batteryChar.readValue()
    batteryLevel = value.getUint8(0)
    batteryUpdatedAt = new Date().toLocaleTimeString()
    log?.(`Battery: ${batteryLevel}%`)
  } catch {
    batteryLevel = null
    batteryUpdatedAt = ''
  }

  // Auto-ACK device-initiated RCSP commands to prevent queue pollution.
  // The device sends commands with flag=0xC0 (type=command, hasResponse=1);
  // we must respond with flag=0x00, same cmd, body=[0x00, deviceSeq].
  const autoAckDeviceCommand = (frame: E87Frame) => {
    // Only auto-ack commands FROM the device (flag bit 7 set = type=command,
    // bit 6 set = expects response).  Skip opcodes we handle explicitly.
    if ((frame.flag & 0xc0) !== 0xc0) return
    // Don't auto-ack opcodes the upload state machine handles (0x20, 0x1c, 0x1d)
    if (frame.cmd === 0x20 || frame.cmd === 0x1c || frame.cmd === 0x1d) return
    const deviceSeq = frame.body[0] ?? 0
    const resp = buildE87Frame(0x00, frame.cmd, Uint8Array.of(0x00, deviceSeq))
    log?.(`AUTO-ACK device cmd 0x${frame.cmd.toString(16)} seq=${deviceSeq}`)
    writeChunkTo(chars.write, resp).catch(() => {})
  }

  const onNotification = (event: Event) => {
    const target = event.target as BluetoothRemoteGATTCharacteristic
    const value = target.value
    if (!value) return
    const raw = new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength))
    // Log incoming data
    const frame = parseE87Frame(raw)
    if (frame) {
      log?.(`RX frame flag=0x${frame.flag.toString(16)} cmd=0x${frame.cmd.toString(16)} len=${frame.length}`)
      // Auto-respond to device-initiated commands so they don't clog the queue
      autoAckDeviceCommand(frame)
      // Only queue frames that are responses or data (not auto-acked commands)
      if ((frame.flag & 0xc0) === 0xc0 && frame.cmd !== 0x20 && frame.cmd !== 0x1c && frame.cmd !== 0x1d) {
        return // Already auto-acked, don't queue
      }
    } else {
      log?.(`RX notify (${raw.length} bytes): ${toHex(raw.slice(0, Math.min(24, raw.length)))}`)
    }
    notificationQueue.push(raw)
    if (notificationQueue.length > 200) notificationQueue.shift()
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
    batteryChar,
    isAuthenticated: false,
    rcspSeq: 1,
    qixSeq: 0,
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
  conn.isAuthenticated = false
  conn.rcspSeq = 1
  conn.qixSeq = 0
  log?.('Disconnected.')
}

function nextRcspSeq(conn: E87Connection): number {
  const out = conn.rcspSeq & 0xff
  conn.rcspSeq = (conn.rcspSeq + 1) & 0xff
  if (conn.rcspSeq === 0) conn.rcspSeq = 1
  return out
}

function nextQixSeq(conn: E87Connection): number {
  const out = conn.qixSeq & 0x0f
  conn.qixSeq = (conn.qixSeq + 1) & 0x0f
  return out
}

/**
 * Build a Qix 0x9E-framed command.
 *
 * Frame layout:
 *   [0x9E] [checksum] [flag] [cmd] [lenLo] [lenHi] [payload...]
 *
 * Flag byte bits:
 *   7: isRequest  6-3: serialNumber  2: isLong  1: needResponse  0: isResponse
 */
function buildQixFrame(cmd: number, payload: Uint8Array, flag: number): Uint8Array {
  const lenLo = payload.length & 0xff
  const lenHi = (payload.length >> 8) & 0xff
  const inner = new Uint8Array(4 + payload.length)
  inner[0] = flag & 0xff
  inner[1] = cmd & 0xff
  inner[2] = lenLo
  inner[3] = lenHi
  inner.set(payload, 4)
  let chk = 0
  for (const b of inner) chk = (chk + b) & 0xff
  const frame = new Uint8Array(2 + inner.length)
  frame[0] = 0x9e
  frame[1] = chk
  frame.set(inner, 2)
  return frame
}

function parseQixFrame(raw: Uint8Array): { cmd: number; flag: number; payload: Uint8Array } | null {
  if (raw.length < 6 || raw[0] !== 0x9e) return null
  const flag = raw[2]
  const cmd = raw[3]
  const plen = raw[4] | (raw[5] << 8)
  if (raw.length < 6 + plen) return null
  return { cmd, flag, payload: raw.slice(6, 6 + plen) }
}

/** Send a Qix 0x9E command on FD02 and wait for a matching response on FD01/FD03 */
async function sendQixCommandAndWait(
  conn: E87Connection,
  cmd: number,
  payload: Uint8Array,
  responseCmdFilter: number,
  log: (msg: string) => void,
  timeoutMs = 6000,
): Promise<{ cmd: number; flag: number; payload: Uint8Array }> {
  const seq = nextQixSeq(conn)
  // flag: isRequest=0, serialNumber=seq (bits 6-3), isLong=0, needResponse=1, isResponse=0
  const flag = ((seq & 0x0f) << 3) | 0x02
  const frame = buildQixFrame(cmd, payload, flag)
  log(`TX Qix cmd=0x${cmd.toString(16)} seq=${seq} payload=${toHex(payload)} frame=${toHex(frame)}`)
  await writeChunkTo(conn.controlChar, frame)

  const raw = await waitForRawNotification(
    conn.notificationQueue,
    (r) => {
      const q = parseQixFrame(r)
      return q !== null && q.cmd === responseCmdFilter
    },
    timeoutMs,
    `qix response cmd 0x${responseCmdFilter.toString(16)}`,
    log,
  )
  return parseQixFrame(raw)!
}

/**
 * Read battery level via Qix 0x9E protocol.
 * Sends COMMAND_REQ_DATA (0x29) with payload [0x80] on FD02,
 * waits for COMMAND_RET_BATTERY_DATA (0x27) response with [status, level].
 */
export async function refreshBatteryQixE87(
  conn: E87Connection,
  log: (msg: string) => void,
): Promise<E87BatteryReading> {
  if (!conn.server?.connected) throw new Error('Device is disconnected.')
  const resp = await sendQixCommandAndWait(
    conn, 0x29, Uint8Array.of(0x80), 0x27, log, 5000,
  )
  if (resp.payload.length >= 2) {
    const chargingStatus = resp.payload[0]
    const level = resp.payload[1]
    const updatedAt = new Date().toLocaleTimeString()
    conn.batteryLevel = level
    conn.batteryUpdatedAt = updatedAt
    log(`Battery via Qix: ${level}% (charging status=${chargingStatus})`)
    return { level, updatedAt }
  }
  log(`Unexpected Qix battery response: ${toHex(resp.payload)}`)
  return { level: null, updatedAt: '' }
}

async function sendRcspCommandAndWait(
  conn: E87Connection,
  cmd: number,
  paramData: Uint8Array,
  log: (msg: string) => void,
  timeoutMs = 8000,
): Promise<E87Frame> {
  const seq = nextRcspSeq(conn)
  const body = new Uint8Array(1 + paramData.length)
  body[0] = seq
  body.set(paramData, 1)

  const frame = buildE87Frame(0xc0, cmd, body)
  log(`TX RCSP cmd=0x${cmd.toString(16)} seq=${seq} len=${body.length}`)
  await writeChunkTo(conn.writeChar, frame)

  const ack = await waitForNotificationFrame(
    conn.notificationQueue,
    (f) => {
      if (f.cmd !== cmd) return false
      // Response frames have flag bit 7 cleared (type=response)
      // Accept if seq matches OR if body is long enough (relaxed for devices that don't echo seq)
      if (f.body.length >= 2 && f.body[1] === seq) return true
      // Relaxed: accept any response for this cmd if flag indicates response
      if ((f.flag & 0x80) === 0 && f.body.length >= 1) return true
      return false
    },
    timeoutMs,
    `rcsp ack cmd 0x${cmd.toString(16)} seq ${seq}`,
    log,
  )

  const status = ack.body[0] ?? 0xff
  if (status !== 0x00) {
    log(`RCSP cmd 0x${cmd.toString(16)} response: status=0x${status.toString(16)} body=${toHex(ack.body)}`)
    throw new Error(`RCSP cmd 0x${cmd.toString(16)} failed with status 0x${status.toString(16)}`)
  }
  return ack
}

/** Remove stale device-command frames from the notification queue */
function drainStaleFrames(queue: Uint8Array[], log?: (msg: string) => void): void {
  let drained = 0
  for (let i = queue.length - 1; i >= 0; i--) {
    const f = parseE87Frame(queue[i])
    if (f && (f.flag & 0xc0) === 0xc0 && f.cmd !== 0x20 && f.cmd !== 0x1c && f.cmd !== 0x1d) {
      queue.splice(i, 1)
      drained++
    }
  }
  if (drained > 0) log?.(`Drained ${drained} stale device-command frame(s) from queue.`)
}

function parseSysInfoAttrs(payload: Uint8Array): E87SysInfoAttr[] {
  const out: E87SysInfoAttr[] = []
  let i = 0
  while (i < payload.length) {
    const attrLen = payload[i] ?? 0
    if (attrLen < 1) break
    const typeIdx = i + 1
    const dataStart = i + 2
    const dataLen = attrLen - 1
    const dataEnd = dataStart + dataLen
    if (dataEnd > payload.length) break
    const type = payload[typeIdx] ?? 0
    const data = payload.slice(dataStart, dataEnd)
    const decoded = decodeAttrValue(type, data)
    out.push({
      type,
      name: PUBLIC_SYSINFO_ATTR_NAMES[type] ?? `attr_${type}`,
      dataHex: toHex(data),
      length: data.length,
      decoded,
    })
    i = dataEnd
  }
  return out
}

function parseTargetInfoAttrs(payload: Uint8Array): Array<{
  type: number
  name: string
  dataHex: string
  length: number
  decoded?: string
}> {
  const out: Array<{ type: number; name: string; dataHex: string; length: number; decoded?: string }> = []
  let i = 0
  while (i < payload.length) {
    const attrLen = payload[i] ?? 0
    if (attrLen < 1) break
    const typeIdx = i + 1
    const dataStart = i + 2
    const dataLen = attrLen - 1
    const dataEnd = dataStart + dataLen
    if (dataEnd > payload.length) break
    const type = payload[typeIdx] ?? 0
    const data = payload.slice(dataStart, dataEnd)
    out.push({
      type,
      name: TARGET_INFO_ATTR_NAMES[type] ?? `attr_${type}`,
      dataHex: toHex(data),
      length: data.length,
      decoded: decodeTargetInfoAttr(type, data),
    })
    i = dataEnd
  }
  return out
}

function decodeAttrValue(type: number, data: Uint8Array): string | undefined {
  if (!data.length) return undefined
  if (type === 0 && data.length === 1) return `${data[0]}%`
  const asAscii = tryAscii(data)
  if (asAscii) return asAscii
  if (data.length === 1) return `${data[0]}`
  if (data.length === 2) return `${((data[0] << 8) | data[1]) >>> 0}`
  if (data.length === 4) return `${((data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]) >>> 0}`
  return undefined
}

function decodeTargetInfoAttr(type: number, data: Uint8Array): string | undefined {
  if (!data.length) return undefined
  if (type === 2 && data.length === 6) {
    return [...data].map((b) => b.toString(16).padStart(2, '0')).join(':')
  }
  if (type === 10 && data.length >= 4) {
    const vid = ((data[0] << 8) | data[1]) >>> 0
    const pid = ((data[2] << 8) | data[3]) >>> 0
    return `vid=0x${vid.toString(16)}, pid=0x${pid.toString(16)}`
  }
  if (type === 13 && data.length >= 2) {
    const mtu = ((data[0] << 8) | data[1]) >>> 0
    return `mtu=${mtu}`
  }
  if ((type === 11 || type === 12 || type === 16 || type === 31) && tryAscii(data)) {
    return tryAscii(data)
  }
  return decodeAttrValue(type, data)
}

function tryAscii(data: Uint8Array): string | undefined {
  if (!data.length) return undefined
  let printable = true
  for (const b of data) {
    if (b < 0x20 || b > 0x7e) {
      printable = false
      break
    }
  }
  if (!printable) return undefined
  return new TextDecoder().decode(data)
}

const RCSP_STATUS_NAMES: Record<number, string> = {
  0x00: 'SUCCESS', 0x01: 'UNKNOWN_ERROR', 0x02: 'NOT_SUPPORTED',
  0x03: 'DATA_ERROR', 0x04: 'TIMEOUT', 0x05: 'REJECTED',
}

export async function getTargetFeatureMapE87(conn: E87Connection, log: (msg: string) => void): Promise<E87TargetFeatureMapResult> {
  await ensureE87Auth(conn, log)
  drainStaleFrames(conn.notificationQueue, log)
  log('GetTargetFeatureMap: sending opcode 0x02 (no params)...')

  // Use manual send + wait to handle non-zero status gracefully
  const seq = nextRcspSeq(conn)
  const frame = buildE87Frame(0xc0, 0x02, Uint8Array.of(seq))
  log(`TX RCSP cmd=0x2 seq=${seq} len=1`)
  await writeChunkTo(conn.writeChar, frame)

  const ack = await waitForNotificationFrame(
    conn.notificationQueue,
    (f) => f.cmd === 0x02 && (f.flag & 0x80) === 0,
    8000,
    'rcsp ack cmd 0x2',
    log,
  )
  const status = ack.body[0] ?? 0xff
  const statusName = RCSP_STATUS_NAMES[status] ?? `0x${status.toString(16)}`
  log(`GetTargetFeatureMap: status=${statusName} body(${ack.body.length})=${toHex(ack.body)}`)

  if (status !== 0x00) {
    log(`GetTargetFeatureMap: device returned ${statusName} — feature map not available on this device.`)
    return { mask: 0, raw: toHex(ack.body) }
  }

  const payload = ack.body.slice(2)
  let mask = 0
  if (payload.length >= 4) {
    mask = ((payload[0] << 24) | (payload[1] << 16) | (payload[2] << 8) | payload[3]) >>> 0
  }
  log(`GetTargetFeatureMap: mask=0x${mask.toString(16).padStart(8, '0')} (${payload.length} payload bytes)`)
  return { mask, raw: toHex(ack.body) }
}

export async function getTargetInfoE87(
  conn: E87Connection,
  log: (msg: string) => void,
  options?: { mask?: number; platform?: number },
): Promise<E87TargetInfoResult> {
  await ensureE87Auth(conn, log)
  const requestMask = (options?.mask ?? 0xffffffff) >>> 0
  const requestPlatform = (options?.platform ?? 0) & 0xff
  const param = Uint8Array.of(
    (requestMask >>> 24) & 0xff,
    (requestMask >>> 16) & 0xff,
    (requestMask >>> 8) & 0xff,
    requestMask & 0xff,
    requestPlatform,
  )
  const ack = await sendRcspCommandAndWait(conn, 0x03, param, log, 10000)
  const payload = ack.body.slice(2)
  log(`GetTargetInfo: payload ${payload.length} bytes`)
  return {
    requestMask,
    requestPlatform,
    raw: toHex(ack.body),
    payload: toHex(payload),
    attrs: parseTargetInfoAttrs(payload),
  }
}

export async function getSysInfoE87(
  conn: E87Connection,
  log: (msg: string) => void,
  options?: { function?: number; mask?: number },
): Promise<E87SysInfoResult> {
  await ensureE87Auth(conn, log)
  const fn = (options?.function ?? 0xff) & 0xff
  const mask = (options?.mask ?? 0xffffffff) >>> 0
  const param = Uint8Array.of(
    fn,
    (mask >>> 24) & 0xff,
    (mask >>> 16) & 0xff,
    (mask >>> 8) & 0xff,
    mask & 0xff,
  )
  const ack = await sendRcspCommandAndWait(conn, 0x07, param, log, 10000)
  const payload = ack.body.slice(2)
  const functionId = payload.length ? payload[0] : fn
  const attrsRaw = payload.slice(Math.min(1, payload.length))
  const attrs = parseSysInfoAttrs(attrsRaw)
  log(`GetSysInfo: function=0x${functionId.toString(16)} attrs=${attrs.length}`)
  return {
    function: functionId,
    raw: toHex(payload),
    attrs,
  }
}

async function sendE87CommandAndWait(
  conn: E87Connection,
  cmd: number,
  body: Uint8Array,
  log: (msg: string) => void,
  timeoutMs = 6000,
): Promise<E87Frame> {
  const frame = buildE87Frame(0xc0, cmd, body)
  log(`TX frame flag=0xc0 cmd=0x${cmd.toString(16)} len=${body.length}`)
  await writeChunkTo(conn.writeChar, frame)
  return waitForNotificationFrame(
    conn.notificationQueue,
    (f) => f.cmd === cmd,
    timeoutMs,
    `ack cmd 0x${cmd.toString(16)}`,
    log,
  )
}

export async function ensureE87Auth(conn: E87Connection, log: (msg: string) => void): Promise<void> {
  if (conn.isAuthenticated) return

  const writeChunk = (chunk: Uint8Array) => writeChunkTo(conn.writeChar, chunk)
  const waitRaw = (
    pred: (raw: Uint8Array) => boolean,
    timeout = 5000,
    label = 'matching raw notification',
  ) => waitForRawNotification(conn.notificationQueue, pred, timeout, label, log)

  log('Auth: Starting Jieli RCSP crypto handshake...')
  const randomAuthData = getRandomAuthData()
  log(`Auth TX: [0x00, rand*16] = ${toHex(randomAuthData)}`)
  await writeChunk(randomAuthData)

  const deviceResponse = await waitRaw(
    (raw) => raw.length === 17 && raw[0] === 0x01,
    5000,
    'auth device response [0x01, encrypted*16]',
  )
  log(`Auth RX: ${toHex(deviceResponse)}`)

  log('Auth TX: [0x02, pass]')
  await writeChunk(Uint8Array.of(0x02, 0x70, 0x61, 0x73, 0x73))

  const deviceChallenge = await waitRaw(
    (raw) => raw.length === 17 && raw[0] === 0x00,
    5000,
    'auth device challenge [0x00, challenge*16]',
  )
  log(`Auth RX challenge: ${toHex(deviceChallenge)}`)

  const encryptedResponse = getEncryptedAuthData(deviceChallenge)
  log(`Auth TX encrypted: ${toHex(encryptedResponse)}`)
  await writeChunk(encryptedResponse)

  const authConfirm = await waitRaw(
    (raw) => raw.length >= 5 && raw[0] === 0x02 && raw[1] === 0x70 && raw[2] === 0x61 && raw[3] === 0x73 && raw[4] === 0x73,
    5000,
    'auth pass confirmation',
  )
  log(`Auth SUCCESS: ${toHex(authConfirm)}`)
  conn.isAuthenticated = true
}

export async function refreshBatteryE87(conn: E87Connection, log: (msg: string) => void): Promise<E87BatteryReading> {
  if (!conn.server?.connected) throw new Error('Device is disconnected.')

  // Try Qix 9E protocol first (works on most Jieli devices)
  try {
    const qixResult = await refreshBatteryQixE87(conn, log)
    if (qixResult.level !== null && qixResult.level > 0) return qixResult
    log('Qix battery returned 0%, trying BLE battery service...')
  } catch (err) {
    log(`Qix battery failed: ${(err as Error).message}, trying BLE service...`)
  }

  // Fall back to standard BLE Battery Service (0x180F)
  let batteryChar = conn.batteryChar
  if (!batteryChar) {
    try {
      const batteryService = await conn.server.getPrimaryService(0x180f)
      batteryChar = await batteryService.getCharacteristic(0x2a19)
      conn.batteryChar = batteryChar
    } catch {
      log('BLE battery service also unavailable.')
      // Last resort: try SysInfo battery attr
      try {
        const sysInfo = await getSysInfoE87(conn, log, { function: 0, mask: 1 })
        const battAttr = sysInfo.attrs.find((a) => a.type === 0)
        if (battAttr && battAttr.decoded?.endsWith('%')) {
          const n = Number.parseInt(battAttr.decoded, 10)
          if (Number.isFinite(n) && n > 0) {
            conn.batteryLevel = n
            conn.batteryUpdatedAt = new Date().toLocaleTimeString()
            log(`Battery from SysInfo: ${n}%`)
            return { level: n, updatedAt: conn.batteryUpdatedAt }
          }
        }
      } catch { /* ignore */ }
      return { level: null, updatedAt: '' }
    }
  }

  const value = await batteryChar.readValue()
  const level = value.getUint8(0)
  const updatedAt = new Date().toLocaleTimeString()
  conn.batteryLevel = level
  conn.batteryUpdatedAt = updatedAt
  log(`Battery from BLE service: ${level}%`)
  return { level, updatedAt }
}

function parseSmallFileQueryBody(type: number, typeName: string, body: Uint8Array): E87SmallFileEntry[] {
  // Seen in SDK: [version][id_hi][id_lo][size_hi][size_lo]...
  // Some devices prepend a status byte, so try a few possible starts.
  const starts = [1, 2, 0]
  for (const start of starts) {
    const rest = body.length - start
    if (rest <= 0 || rest % 4 !== 0) continue
    const out: E87SmallFileEntry[] = []
    for (let i = start; i + 3 < body.length; i += 4) {
      const id = (body[i] << 8) | body[i + 1]
      const size = (body[i + 2] << 8) | body[i + 3]
      if (id === 0 && size === 0) continue
      out.push({ type, typeName, id, size })
    }
    if (out.length > 0 || rest === 0) return out
  }
  return []
}

export async function listSmallFilesE87(conn: E87Connection, log: (msg: string) => void): Promise<E87SmallFileEntry[]> {
  await ensureE87Auth(conn, log)
  drainStaleFrames(conn.notificationQueue, log)

  const all: E87SmallFileEntry[] = []
  for (const t of SMALL_FILE_TYPES) {
    try {
      const queryBody = Uint8Array.of(0x00, t.type)
      const ack = await sendE87CommandAndWait(conn, 0x28, queryBody, log, 7000)
      const parsed = parseSmallFileQueryBody(t.type, t.name, ack.body)
      if (parsed.length > 0) {
        log(`Small-file type ${t.name}: ${parsed.length} item(s)`)
        all.push(...parsed)
      }
    } catch (err) {
      log(`Small-file type ${t.name}: no response (${(err as Error).message})`)
    }
  }

  return all.sort((a, b) => a.type - b.type || a.id - b.id)
}

export async function readSmallFileE87(
  conn: E87Connection,
  entry: E87SmallFileEntry,
  log: (msg: string) => void,
): Promise<E87SmallFileReadResult> {
  await ensureE87Auth(conn, log)

  // op=1, type, id(2), offset(2), len(2), flag(1)
  const maxLen = Math.min(0xffff, Math.max(entry.size, 256))
  const body = Uint8Array.of(
    0x01,
    entry.type & 0xff,
    (entry.id >> 8) & 0xff,
    entry.id & 0xff,
    0x00,
    0x00,
    (maxLen >> 8) & 0xff,
    maxLen & 0xff,
    0x01,
  )

  const ack = await sendE87CommandAndWait(conn, 0x28, body, log, 9000)
  let dataStart = 3
  let crc16: number | null = null

  if (ack.body.length >= 3) {
    // Typical: [ret][crc_hi][crc_lo][data...]
    const ret = ack.body[0]
    if (ret === 0x00) {
      crc16 = (ack.body[1] << 8) | ack.body[2]
      dataStart = 3
    } else if (ack.body.length >= 4 && ack.body[1] === 0x00) {
      // Some stacks echo op before status: [op][ret][crc_hi][crc_lo][data...]
      crc16 = (ack.body[2] << 8) | ack.body[3]
      dataStart = 4
    }
  }

  const data = ack.body.slice(Math.min(dataStart, ack.body.length))
  log(`Read small file type=${entry.typeName} id=${entry.id} bytes=${data.length}`)
  return { entry, data, crc16 }
}

export async function deleteSmallFileE87(
  conn: E87Connection,
  entry: E87SmallFileEntry,
  log: (msg: string) => void,
): Promise<void> {
  await ensureE87Auth(conn, log)

  // op=4, type, id(2)
  const body = Uint8Array.of(
    0x04,
    entry.type & 0xff,
    (entry.id >> 8) & 0xff,
    entry.id & 0xff,
  )

  const ack = await sendE87CommandAndWait(conn, 0x28, body, log, 7000)
  const ret = ack.body.length ? ack.body[0] : 0
  if (ret !== 0x00) {
    throw new Error(`Delete failed for type=${entry.typeName} id=${entry.id}, ret=0x${ret.toString(16)}`)
  }
  log(`Deleted small file type=${entry.typeName} id=${entry.id}`)
}

/**
 * Browse device filesystem using RCSP StartFileBrowseCmd (opcode 0x0C).
 *
 * Parameter layout (from decompiled FileBrowseParam):
 *   [type:1] [readNum:1] [startIndex:2 BE] [devHandler:4 BE] [pathLen:2 LE] [path:N*4 BE]
 *
 * type: 0=folder, 1=file
 * devHandler: 0=USB, 1=SD0, 2=SD1, 3=Flash
 *
 * Response is parsed as file/folder entries.
 */
async function sendFileBrowseRequest(
  conn: E87Connection,
  log: (msg: string) => void,
  type: number,
  readNum: number,
  startIndex: number,
  devHandler: number,
  clusters: number[],
): Promise<E87Frame> {
  // Build path data: each cluster is a big-endian 4-byte int
  const pathBytes = new Uint8Array(clusters.length * 4)
  for (let i = 0; i < clusters.length; i++) {
    const c = clusters[i]
    pathBytes[i * 4 + 0] = (c >> 24) & 0xff
    pathBytes[i * 4 + 1] = (c >> 16) & 0xff
    pathBytes[i * 4 + 2] = (c >> 8) & 0xff
    pathBytes[i * 4 + 3] = c & 0xff
  }
  const pathLen = pathBytes.length

  // Serialize: [type][readNum][startIndex:2 BE][devHandler:4 BE][pathLen:2 LE][pathBytes]
  const param = new Uint8Array(1 + 1 + 2 + 4 + 2 + pathLen)
  param[0] = type & 0xff
  param[1] = readNum & 0xff
  param[2] = (startIndex >> 8) & 0xff
  param[3] = startIndex & 0xff
  param[4] = (devHandler >> 24) & 0xff
  param[5] = (devHandler >> 16) & 0xff
  param[6] = (devHandler >> 8) & 0xff
  param[7] = devHandler & 0xff
  param[8] = pathLen & 0xff        // LE low byte
  param[9] = (pathLen >> 8) & 0xff // LE high byte
  param.set(pathBytes, 10)

  log(`FileBrowse: type=${type} readNum=${readNum} startIndex=${startIndex} devHandler=${devHandler} clusters=[${clusters}]`)

  // Use manual send+wait so we can handle non-zero status without throwing
  const seq = nextRcspSeq(conn)
  const body = new Uint8Array(1 + param.length)
  body[0] = seq
  body.set(param, 1)
  const frame = buildE87Frame(0xc0, 0x0c, body)
  log(`TX RCSP cmd=0xc seq=${seq} len=${body.length}`)
  await writeChunkTo(conn.writeChar, frame)

  return waitForNotificationFrame(
    conn.notificationQueue,
    (f) => f.cmd === 0x0c && (f.flag & 0x80) === 0,
    10000,
    'rcsp ack cmd 0xc (FileBrowse)',
    log,
  )
}

const DEV_HANDLER_NAMES: Record<number, string> = {
  0: 'USB', 1: 'SD0', 2: 'SD1', 3: 'Flash',
}

export async function browseFilesE87(
  conn: E87Connection,
  log: (msg: string) => void,
  options?: {
    type?: number       // 0=folder, 1=file (default: 1)
    readNum?: number    // items to read (default: 20)
    startIndex?: number // 1-based start (default: 1)
    devHandler?: number // 0=USB, 1=SD0, 2=SD1, 3=Flash (default: auto-try)
    clusters?: number[] // path clusters (default: [0] for root)
  },
): Promise<E87FileBrowseEntry[]> {
  await ensureE87Auth(conn, log)
  drainStaleFrames(conn.notificationQueue, log)

  const type = options?.type ?? 1
  const readNum = options?.readNum ?? 20
  const startIndex = options?.startIndex ?? 1
  const clusters = options?.clusters ?? [0]

  // If devHandler specified, try only that; otherwise try all (Flash first)
  const handlersToTry = options?.devHandler !== undefined
    ? [options.devHandler]
    : [3, 2, 1, 0]  // Flash, SD1, SD0, USB

  for (const devHandler of handlersToTry) {
    drainStaleFrames(conn.notificationQueue, log)
    try {
      const ack = await sendFileBrowseRequest(conn, log, type, readNum, startIndex, devHandler, clusters)
      const status = ack.body[0] ?? 0xff
      const statusName = RCSP_STATUS_NAMES[status] ?? `0x${status.toString(16)}`
      log(`FileBrowse[${DEV_HANDLER_NAMES[devHandler] ?? devHandler}]: status=${statusName} body(${ack.body.length})=${toHex(ack.body.slice(0, Math.min(80, ack.body.length)))}`)

      // Give device a moment, then drain any StopFileBrowse commands it sends
      await sleep(200)
      drainStaleFrames(conn.notificationQueue, log)

      if (status !== 0x00) {
        log(`FileBrowse[${DEV_HANDLER_NAMES[devHandler] ?? devHandler}]: ${statusName} — skipping.`)
        continue
      }

      const payload = ack.body.slice(2)
      if (payload.length === 0) {
        log(`FileBrowse[${DEV_HANDLER_NAMES[devHandler] ?? devHandler}]: success but empty payload.`)
        continue
      }

      const entries = parseFileBrowseResponse(payload, type, log)
      if (entries.length > 0) {
        log(`FileBrowse[${DEV_HANDLER_NAMES[devHandler] ?? devHandler}]: found ${entries.length} entries.`)
        return entries
      }
    } catch (err) {
      log(`FileBrowse[${DEV_HANDLER_NAMES[devHandler] ?? devHandler}]: ${(err as Error).message}`)
    }
  }

  log('FileBrowse: no entries found on any storage device.')
  drainStaleFrames(conn.notificationQueue, log)
  return []
}

function parseFileBrowseResponse(payload: Uint8Array, queryType: number, log: (msg: string) => void): E87FileBrowseEntry[] {
  const entries: E87FileBrowseEntry[] = []
  if (payload.length < 2) {
    log(`FileBrowse: empty response (${payload.length} bytes)`)
    return entries
  }

  // Try to parse as a sequence of entries
  // The response format varies by device, so try multiple parsing strategies
  log(`FileBrowse: parsing ${payload.length} bytes of response data`)
  log(`FileBrowse: raw hex: ${toHex(payload.slice(0, Math.min(120, payload.length)))}`)

  // Strategy 1: try to decode as UTF-16LE name entries
  // Each entry might be: [cluster:4 BE][size:4 BE][name_len:1][name:UTF16LE]
  let i = 0
  let entryCount = 0
  while (i < payload.length) {
    // Need at least 9 bytes for cluster + size + name_len
    if (i + 9 > payload.length) break
    const cluster = ((payload[i] << 24) | (payload[i+1] << 16) | (payload[i+2] << 8) | payload[i+3]) >>> 0
    const sizeBytes = ((payload[i+4] << 24) | (payload[i+5] << 16) | (payload[i+6] << 8) | payload[i+7]) >>> 0
    const nameLen = payload[i+8]
    if (nameLen === 0 || i + 9 + nameLen > payload.length) break
    // Try decoding name as UTF-16LE
    const nameRaw = payload.slice(i + 9, i + 9 + nameLen)
    let name: string
    try {
      // If nameLen is even, try UTF-16LE; otherwise treat as UTF-8
      if (nameLen >= 2 && nameLen % 2 === 0) {
        name = new TextDecoder('utf-16le').decode(nameRaw).replace(/\0+$/, '')
      } else {
        name = new TextDecoder().decode(nameRaw).replace(/\0+$/, '')
      }
    } catch {
      name = toHex(nameRaw)
    }
    entries.push({
      name,
      isFolder: queryType === 0,
      sizeBytes,
      cluster,
      rawHex: toHex(payload.slice(i, i + 9 + nameLen)),
    })
    entryCount++
    i += 9 + nameLen
    if (entryCount > 100) break
  }

  if (entries.length === 0) {
    // Strategy 2: Just log the raw data for now
    log(`FileBrowse: could not parse structured entries, raw payload logged above`)
  } else {
    for (const e of entries) {
      log(`FileBrowse: ${e.isFolder ? '[DIR]' : '[FILE]'} "${e.name}" size=${e.sizeBytes} cluster=${e.cluster}`)
    }
  }

  return entries
}

/**
 * Stop a file browse session using RCSP StopFileBrowseCmd (opcode 0x0D).
 */
export async function stopBrowseE87(conn: E87Connection, log: (msg: string) => void): Promise<void> {
  await ensureE87Auth(conn, log)
  drainStaleFrames(conn.notificationQueue, log)
  try {
    await sendRcspCommandAndWait(conn, 0x0d, Uint8Array.of(0x00), log, 3000)
  } catch { /* device may have already stopped */ }
  drainStaleFrames(conn.notificationQueue, log)
  log('FileBrowse: stopped.')
}

/**
 * Get device screen/display info via Qix COMMAND_RET_SCREEN_INFO (0xC7).
 * Sends COMMAND_REQ_SCREEN_INFO (0xC6) on FD02.
 */
export async function getScreenInfoE87(
  conn: E87Connection,
  log: (msg: string) => void,
): Promise<{ width: number; height: number; pictureWidth: number; pictureHeight: number; memory: number } | null> {
  try {
    const resp = await sendQixCommandAndWait(conn, 0xc6, Uint8Array.of(0x01), 0xc7, log, 5000)
    if (resp.payload.length >= 9 && resp.payload[0] === 0x01) {
      const width = resp.payload[1] | (resp.payload[2] << 8)
      const height = resp.payload[3] | (resp.payload[4] << 8)
      const pictureWidth = resp.payload[5] | (resp.payload[6] << 8)
      const pictureHeight = resp.payload[7] | (resp.payload[8] << 8)
      const memory = resp.payload.length >= 13
        ? (resp.payload[9] | (resp.payload[10] << 8) | (resp.payload[11] << 16) | (resp.payload[12] << 24)) >>> 0
        : 0
      log(`ScreenInfo: ${width}x${height} pic=${pictureWidth}x${pictureHeight} mem=${memory}`)
      return { width, height, pictureWidth, pictureHeight, memory }
    }
    log(`ScreenInfo: unexpected response payload ${toHex(resp.payload)}`)
    return null
  } catch (err) {
    log(`ScreenInfo: failed (${(err as Error).message})`)
    return null
  }
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
    await ensureE87Auth(conn, log)

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
