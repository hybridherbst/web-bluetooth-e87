export function normalizeMAC(value: string): string {
  let raw = value.trim()
  if (/^https?:\/\//.test(raw)) {
    try { raw = new URL(raw).searchParams.get('mac') || '' } catch { return '' }
  }
  raw = raw.replaceAll('-', ':').toUpperCase()
  return /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(raw) ? raw : ''
}

export function systemMAC(id: string, platform: string): string {
  // Chromium on macOS hashes the CoreBluetooth UUID into a MAC-shaped ID.
  // It is never the peripheral's advertised hardware address.
  return platform === 'darwin' ? '' : normalizeMAC(id)
}
