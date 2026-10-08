/**
 * Tests for file-browse request building and response parsing, using bytes captured
 * from a real E87 badge (storage SD1, handle 2, folder "BAG").
 *
 * Run: npx tsx test_browse.ts
 */
import { buildBrowseParams, buildE87Frame, parseBrowseEntries, parseStorageAttr } from './src/lib/e87-protocol'

const fromHex = (h: string) => Uint8Array.from(h.match(/../g)!.map((b) => parseInt(b, 16)))
const toHex = (a: Uint8Array) => Array.from(a).map((b) => b.toString(16).padStart(2, '0')).join('')

let failed = 0
function check(name: string, ok: boolean, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  ${detail}`}`)
  if (!ok) failed++
}

// ── Request: list folder BAG (path = [root 0, BAG cluster 2]) on handle 2, as captured ──
const params = buildBrowseParams(0, 50, 1, 2, [0, 2])
const frame = buildE87Frame(0xc0, 0x0c, Uint8Array.of(0x06, ...params))
check('browse request frame', toHex(frame) === 'fedcbac00c001306003200010000000200080000000000000002ef', toHex(frame))

// ── Request: delete the file at cluster 3 on handle 2 (captured; response was status 0) ──
const del = new Uint8Array(11)
const dv = new DataView(del.buffer)
del[0] = 0x05; del[1] = 0x01; dv.setUint32(2, 2, false); del[6] = 0x01; dv.setUint32(7, 3, false)
check('delete request frame', toHex(buildE87Frame(0xc0, 0x1f, del)) === 'fedcbac01f000b0501000000020100000003ef')

// ── Root listing: one folder entry "BAG" (flags 0x0a = folder, GBK name, device index 2) ──
const root = parseBrowseEntries(fromHex('0a00000002000103424147'))
check('root: one entry', root.length === 1)
check('root: BAG is a folder', root[0]?.isFolder === true && root[0]?.name === 'BAG')
check('root: cluster/fileNum/devIndex', root[0]?.cluster === 2 && root[0]?.fileNum === 1 && root[0]?.devIndex === 2)
check('root: GBK name', root[0]?.unicode === false)

// ── Folder listing: two files (flags 0x09 = file, UTF-16LE name, device index 2) ──
const files = parseBrowseEntries(fromHex(
  '0900000003000124320030003200360030003300320039003000390031003500300038002e006a0070006700' +
  '0900000008000224320030003200360030003300320039003100360034003200340039002e00610076006900',
))
check('files: two entries', files.length === 2)
check('files: names', files[0]?.name === '20260329091508.jpg' && files[1]?.name === '20260329164249.avi', JSON.stringify(files.map((f) => f.name)))
check('files: not folders, UTF-16LE', files.every((f) => !f.isFolder && f.unicode))
check('files: clusters and numbers', files[0]?.cluster === 3 && files[0]?.fileNum === 1 && files[1]?.cluster === 8 && files[1]?.fileNum === 2)

// ── A truncated trailing record is ignored rather than mis-parsed ──
check('truncated record ignored', parseBrowseEntries(fromHex('0a0000000200010342414709000000')).length === 1)

// ── Storage attribute (GetSysInfo attr 2, legacy layout): only SD1 online, handle 2 ──
const storage = parseStorageAttr(fromHex('04000000000000000000000002000000000000000000000000'))
const online = storage.filter((d) => d.online)
check('storage: only SD1 online', online.length === 1 && online[0].index === 2 && online[0].name === 'SD1', JSON.stringify(online))
check('storage: handle is 2', online[0]?.handle === 2)

if (failed > 0) process.exit(1)
console.log('All tests passed.')
