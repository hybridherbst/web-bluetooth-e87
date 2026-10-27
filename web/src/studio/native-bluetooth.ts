// The shared E87 protocol keeps its Web Bluetooth interface. Only Studio uses
// this small adapter; all radio access is handled by the native Rust backend.
type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>
type Properties = { read: boolean; write: boolean; writeWithoutResponse: boolean; notify: boolean; indicate: boolean }
type ServiceInfo = { uuid: string; characteristics: { uuid: string; properties: Properties }[] }
type DeviceInfo = { deviceId: string; deviceName: string; advertisedMac?: string; rssi?: number }
type Scan = { requestId: number; devices: DeviceInfo[]; error?: string }
const canonical = (uuid: string | number) => typeof uuid === 'number' ? `0000${uuid.toString(16).padStart(4, '0')}-0000-1000-8000-00805f9b34fb` : uuid.length === 4 ? `0000${uuid.toLowerCase()}-0000-1000-8000-00805f9b34fb` : uuid.toLowerCase()

export class NativeBluetooth {
  invoke: Invoke
  private counter = 0
  private pending?: { id: number; resolve: (device: NativeDevice) => void; reject: (error: Error) => void }
  private device?: NativeDevice
  private scan?: Scan
  private scanHandlers = new Set<(scan: Scan | null) => void>()
  constructor(invoke: Invoke) {
    this.invoke = async (command, args) => {
      try { return await invoke(command, args) }
      catch (error) { throw error instanceof Error ? error : new Error(String(error)) }
    }
  }
  private update(scan: Scan | null) { this.scan = scan || undefined; for (const h of this.scanHandlers) h(scan) }
  onDevices(handler: (scan: Scan | null) => void) {
    this.scanHandlers.add(handler); handler(this.scan || null)
    return () => { this.scanHandlers.delete(handler) }
  }
  receiveScan(scan: Scan) {
    if (scan.requestId !== this.pending?.id) return
    if (scan.error) { this.pending.reject(new Error(scan.error)); this.pending = undefined; this.update(null) }
    else this.update(scan)
  }
  requestDevice(): Promise<NativeDevice> {
    if (this.pending) return Promise.reject(new Error('Поиск уже идёт.'))
    const id = ++this.counter
    return new Promise((resolve, reject) => {
      this.pending = { id, resolve, reject }
      this.update({ requestId: id, devices: [] })
      void this.invoke('ble_scan', { requestId: id }).catch(error => {
        if (this.pending?.id !== id) return
        this.pending = undefined; this.update(null); reject(new Error(String(error)))
      })
    })
  }
  async select(requestId: number, deviceId: string) {
    const pending = this.pending
    if (!pending || pending.id !== requestId) return false
    try {
      const info = await this.invoke<DeviceInfo | null>('ble_select', { requestId, deviceId })
      if (this.pending !== pending) return false
      this.pending = undefined; this.update(null)
      if (info) {
        this.device = new NativeDevice(this.invoke, requestId, info)
        pending.resolve(this.device)
      } else pending.reject(new DOMException('Поиск отменён.', 'NotFoundError'))
      return true
    } catch { return false }
  }
  receiveNotification(event: { sessionId: number; uuid: string; value: number[] }) {
    if (this.device?.sessionId === event.sessionId) this.device.gatt.notification(event.uuid, event.value)
  }
  receiveDisconnect(sessionId: number) {
    if (this.device?.sessionId === sessionId) this.device.gatt.didDisconnect()
  }
}

class NativeDevice extends EventTarget {
  id: string
  name: string
  sessionId: number
  gatt: NativeServer
  constructor(invoke: Invoke, sessionId: number, info: DeviceInfo) {
    super(); this.id = info.deviceId; this.name = info.deviceName; this.sessionId = sessionId
    this.gatt = new NativeServer(invoke, this)
  }
}
class NativeServer {
  connected = false
  private services: NativeService[] = []
  private disconnecting: Promise<unknown> = Promise.resolve()
  invoke: Invoke
  device: NativeDevice
  constructor(invoke: Invoke, device: NativeDevice) { this.invoke = invoke; this.device = device }
  async connect() {
    await this.disconnecting
    const services = await this.invoke<ServiceInfo[]>('ble_connect', { sessionId: this.device.sessionId })
    this.services = services.map(info => new NativeService(this, info)); this.connected = true
    return this
  }
  disconnect() {
    this.didDisconnect()
    this.disconnecting = this.invoke('ble_disconnect', { sessionId: this.device.sessionId }).catch(() => {})
  }
  didDisconnect() {
    const wasConnected = this.connected
    this.connected = false; this.services = []
    if (wasConnected) this.device.dispatchEvent(new Event('gattserverdisconnected'))
  }
  async getPrimaryServices() { this.ensureConnected(); return this.services }
  async getPrimaryService(uuid: string | number) {
    this.ensureConnected()
    const service = this.services.find(s => s.uuid === canonical(uuid))
    if (!service) throw new Error(`Service ${uuid} not found`)
    return service
  }
  ensureConnected() { if (!this.connected) throw new Error('Значок отключён.') }
  notification(uuid: string, bytes: number[]) {
    if (!this.connected) return
    for (const service of this.services) for (const c of service.characteristics) if (c.uuid === uuid) c.notification(bytes)
  }
}
class NativeService {
  uuid: string
  characteristics: NativeCharacteristic[]
  server: NativeServer
  constructor(server: NativeServer, info: ServiceInfo) {
    this.server = server; this.uuid = info.uuid
    this.characteristics = info.characteristics.map(c => new NativeCharacteristic(this, c.uuid, c.properties))
  }
  async getIncludedServices() { return [] }
  async getCharacteristics() { this.server.ensureConnected(); return this.characteristics }
  async getCharacteristic(uuid: string | number) {
    this.server.ensureConnected()
    const c = this.characteristics.find(c => c.uuid === canonical(uuid))
    if (!c) throw new Error(`Characteristic ${uuid} not found`)
    return c
  }
}
class NativeCharacteristic extends EventTarget {
  uuid: string
  properties: Properties
  service: NativeService
  value?: DataView
  private subscribed = false
  constructor(service: NativeService, uuid: string, properties: Properties) { super(); this.service = service; this.uuid = uuid; this.properties = properties }
  private call<T>(command: string, args: Record<string, unknown> = {}) {
    this.service.server.ensureConnected()
    return this.service.server.invoke<T>(command, { sessionId: this.service.server.device.sessionId, service: this.service.uuid, uuid: this.uuid, ...args })
  }
  async readValue() { this.value = new DataView(Uint8Array.from(await this.call<number[]>('ble_read')).buffer); return this.value }
  private async write(value: BufferSource, withoutResponse: boolean) {
    const bytes = ArrayBuffer.isView(value) ? new Uint8Array(value.buffer, value.byteOffset, value.byteLength) : new Uint8Array(value)
    await this.call('ble_write', { bytes: Array.from(bytes), withoutResponse })
  }
  writeValue(value: BufferSource) { return this.write(value, false) }
  writeValueWithoutResponse(value: BufferSource) { return this.write(value, true) }
  async startNotifications() {
    // A notification may arrive before the native subscribe promise resolves.
    this.subscribed = true
    try { await this.call('ble_notify', { enabled: true }) } catch (e) { this.subscribed = false; throw e }
    return this
  }
  async stopNotifications() { this.subscribed = false; await this.call('ble_notify', { enabled: false }); return this }
  notification(bytes: number[]) {
    if (!this.subscribed) return
    this.value = new DataView(Uint8Array.from(bytes).buffer)
    this.dispatchEvent(new Event('characteristicvaluechanged'))
  }
}
