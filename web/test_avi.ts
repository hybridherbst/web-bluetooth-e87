/**
 * Tests the AVI header timing fields written by buildMjpgAvi for whole and fractional frame rates.
 *
 * Run: npx tsx test_avi.ts
 */
import { aviRate, buildMjpgAvi } from './src/avi-builder'

const jpeg = Uint8Array.of(0xff, 0xd8, 0xff, 0xd9) // minimal stand-in frame
const tag = (buf: Uint8Array, name: string) => {
  const t = Array.from(name).map((c) => c.charCodeAt(0))
  for (let i = 0; i + 4 <= buf.length; i++) if (t.every((b, j) => buf[i + j] === b)) return i
  throw new Error(`chunk ${name} not found`)
}
const u32 = (buf: Uint8Array, o: number) => new DataView(buf.buffer, buf.byteOffset).getUint32(o, true)

function header(fps: number) {
  const avi = buildMjpgAvi([jpeg, jpeg], { fps })
  const avih = tag(avi, 'avih') + 8
  const strh = tag(avi, 'strh') + 8
  const vprp = tag(avi, 'vprp') + 8
  return {
    usecPerFrame: u32(avi, avih),
    scale: u32(avi, strh + 20),
    rate: u32(avi, strh + 24),
    refresh: u32(avi, vprp + 8),
  }
}

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  ${detail}`}`)
  if (!ok) failed++
}

// Whole rates keep the historical encoding (dwScale 1, dwRate = fps).
let h = header(12)
check('12 fps: usec', h.usecPerFrame === 83333, JSON.stringify(h))
check('12 fps: scale 1, rate 12', h.scale === 1 && h.rate === 12, JSON.stringify(h))
check('12 fps: refresh 12', h.refresh === 12)
h = header(1)
check('1 fps: 1,000,000 usec, scale 1, rate 1', h.usecPerFrame === 1_000_000 && h.scale === 1 && h.rate === 1, JSON.stringify(h))

// Fractional rates are encoded exactly, never truncated to zero.
h = header(0.25)
check('0.25 fps (4 s): usec 4,000,000', h.usecPerFrame === 4_000_000, JSON.stringify(h))
check('0.25 fps: rate/scale = 250/1000', h.scale === 1000 && h.rate === 250, JSON.stringify(h))
check('0.25 fps: rate is not zero', h.rate !== 0)
h = header(0.2)
check('0.2 fps (5 s): usec 5,000,000 and 200/1000', h.usecPerFrame === 5_000_000 && h.scale === 1000 && h.rate === 200, JSON.stringify(h))
h = header(1 / 3)
check('1/3 fps (3 s): 333/1000, usec 3,000,000', h.usecPerFrame === 3_000_000 && h.scale === 1000 && h.rate === 333, JSON.stringify(h))
check('refresh rate never 0', header(0.1).refresh === 1)

// Bad input is rejected.
for (const bad of [0, -1, NaN, Infinity]) {
  let threw = false
  try { aviRate(bad) } catch { threw = true }
  check(`aviRate(${bad}) throws`, threw)
}

if (failed > 0) process.exit(1)
console.log('All tests passed.')
