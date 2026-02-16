/**
 * Test for jl-auth crypto module against captured BLE auth exchange.
 *
 * Run: npx tsx test_crypto.ts
 */
import { functionE1test, STATIC_KEY, MAGIC } from './src/jl-auth'

// Captured challenge from device (bytes after 0x00 prefix)
const challenge = [
  0xb6, 0xe0, 0x80, 0xec, 0xaf, 0xf3, 0x22, 0x91,
  0x6d, 0x88, 0xfa, 0xd5, 0xaa, 0x34, 0xc2, 0xac,
]

// Expected encrypted response (bytes after 0x01 prefix)
const expected = [
  0x1d, 0x88, 0x97, 0xac, 0x46, 0x04, 0xd3, 0x32,
  0xe8, 0x17, 0x5e, 0x81, 0xbb, 0x29, 0x25, 0x24,
]

const result = functionE1test(MAGIC, challenge, STATIC_KEY)

const hex = (arr: number[]) => arr.map(b => b.toString(16).padStart(2, '0')).join(' ')

console.log('Result:  ', hex(result))
console.log('Expected:', hex(expected))

const match = result.every((b, i) => b === expected[i])
console.log('Match:', match)

if (!match) {
  process.exit(1)
}
