#!/usr/bin/env python3
"""Check RX FE frames in the capture — especially cmd 0x1d, 0x20, 0x1c from device."""
import struct
from collections import Counter

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw):
        break

tc = Counter(r['type'] for r in records)
print('Record types:', dict(tc))

# Look for FE DC BA in ALL records, regardless of L2CAP parsing
fe_by_type = Counter()
for r in records:
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            fe_by_type[r['type']] += 1
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd in (0x1d, 0x20, 0x1c, 0x1b, 0x21, 0x27, 0x03, 0x06, 0x07):
                body_start = p[idx+7:min(idx+7+blen, idx+25)]
                print(f'  rectype={r["type"]} flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen} body={body_start.hex()}')
            break

print()
print('FE frames by record type:', dict(fe_by_type))

# Also look for NON-FE-framed RX values during/after transfer
# The device window acks (cmd 0x1d) are FE-framed
# Let's check all record type=3 (RX) for any FE frames near the data transfer
print()
print('=== ALL RX FE FRAMES ===')
for r in records:
    if r['type'] != 3:
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            body = p[idx+7:idx+7+blen]
            print(f'  RX flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen} body={body[:20].hex()}')
            break

# What about the completion? Does the device send 0x20 or 0x1c?
# Or does the APP send them proactively?
print()
print('=== ALL cmd 0x20 and 0x1c frames (both directions) ===')
for r in records:
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd in (0x20, 0x1c):
                body = p[idx+7:idx+7+blen]
                direction = 'TX' if r['type'] == 2 else 'RX'
                print(f'  {direction} flag=0x{flag:02x} cmd=0x{cmd:02x} body={body.hex()}')
            break
