/**
 * Tests for the free-space check, using values measured on an E87 badge.
 *
 * Run: npx tsx test_storage.ts
 */
import { checkFreeSpace, clustersNeeded } from './src/lib/storage'

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  ${detail}`}`)
  if (!ok) failed++
}

// A 131,090-byte AVI (33 clusters of data) lowered the badge's free space from 2252 KB to 2116 KB = 34 clusters.
check('131,090 bytes needs 34 clusters', clustersNeeded(131_090) === 34, String(clustersNeeded(131_090)))

// The same file against the card as it was when uploads failed (72 KB free) and when they worked (2252 KB free).
let r = checkFreeSpace(72, 131_090)
check('does not fit in 72 KB', !r.fits && r.neededKb === 136 && r.freeKb === 72, JSON.stringify(r))
r = checkFreeSpace(2252, 131_090)
check('fits in 2252 KB', r.fits, JSON.stringify(r))

// Boundary: 34 clusters needed + 1 spare = 35 clusters = 140 KB free.
check('does not fit in 136 KB (no spare cluster left)', !checkFreeSpace(136, 131_090).fits)
check('fits in 140 KB', checkFreeSpace(140, 131_090).fits)

// Exact cluster multiples and tiny files.
check('4096 bytes needs 2 clusters', clustersNeeded(4096) === 2)
check('4097 bytes needs 3 clusters', clustersNeeded(4097) === 3)
check('0 bytes needs 1 cluster', clustersNeeded(0) === 1)

// A completely full card (0 KB) fits nothing.
check('0 KB free fits nothing', !checkFreeSpace(0, 1).fits)

if (failed > 0) process.exit(1)
console.log('All tests passed.')
