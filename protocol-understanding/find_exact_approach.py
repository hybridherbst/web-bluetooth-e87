#!/usr/bin/env python3
"""
Find the EXACT correct way to produce the capture's data frames.
The capture data = jpeg[490:] + jpeg[0:490], but the chunking must
produce: 30 x 490-byte + 1 x 457-byte + 1 x 490-byte frames.
"""
import struct

CHUNK = 490

def crc16xmodem(data):
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

jpeg = open('/Users/herbst/git/bluetooth-tag/captured_image.jpg', 'rb').read()

# Parse capture data frames
raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw): break

current = None
cap_data_frames = []
for rec in records:
    if rec['type'] != 2: continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'data': bytearray(p[8:]), 'expected': l2cap_len}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    else: continue
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        current = None
        if len(data) < 3: continue
        att_val = data[3:]
        for idx in range(len(att_val)):
            if (idx + 7 < len(att_val) and att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                flag = att_val[idx+3]
                cmd = att_val[idx+4]
                blen = (att_val[idx+5] << 8) | att_val[idx+6]
                end = idx + 7 + blen
                if end < len(att_val) and att_val[end] == 0xEF:
                    body = bytes(att_val[idx+7:end])
                    if flag == 0x80 and cmd == 0x01:
                        cap_data_frames.append(body[5:])  # just the file data
                break

print(f"Capture data frames: {len(cap_data_frames)}")
for i, d in enumerate(cap_data_frames):
    print(f"  frame {i:2d}: {len(d)} bytes, crc=0x{crc16xmodem(d):04x}")

print()

# The capture has:
# frames 0-29: 490 bytes each (from jpeg[490:15190])
# frame 30: 457 bytes (from jpeg[15190:15647])
# frame 31: 490 bytes (from jpeg[0:490])

# APPROACH: Two-part send
# Part A: send jpeg[490:] as sequential chunks → produces 31 chunks (30x490 + 1x457)
# Part B: send jpeg[0:490] as final chunk → produces 1 chunk (490)
# Total: 32 chunks, matching capture exactly

print("=== APPROACH: Two-part send (jpeg[490:] then jpeg[0:490]) ===")
tail = jpeg[490:]  # 15157 bytes
head = jpeg[0:490]  # 490 bytes

chunks = []
# Part A: chunk the tail
for off in range(0, len(tail), CHUNK):
    chunks.append(tail[off:off+CHUNK])
# Part B: the head
chunks.append(head)

print(f"Total chunks: {len(chunks)}")
all_match = True
for i, chunk in enumerate(chunks):
    cap = cap_data_frames[i]
    crc_ours = crc16xmodem(chunk)
    crc_cap = crc16xmodem(cap)
    match = (chunk == cap)
    if not match:
        all_match = False
    status = "✓" if match else "✗"
    print(f"  {status} chunk {i:2d}: len={len(chunk):3d}/{len(cap):3d}  crc=0x{crc_ours:04x}/0x{crc_cap:04x}")

print()
if all_match:
    print("✓✓✓ TWO-PART APPROACH: PERFECT MATCH!")
else:
    print("✗ Mismatch detected")

# Now verify slot numbering
print()
print("=== SLOT NUMBERING CHECK ===")
slot = 0
for i in range(len(chunks)):
    print(f"  chunk {i:2d}: slot={slot}")
    slot = (slot + 1) & 0x07
print(f"Frame 31 slot = {(31) % 8} → cap shows slot=0 → {31 % 8 == 0}")
# 32 chunks: slots 0,1,2,3,4,5,6,7, 0,1,2,3,4,5,6,7, 0,1,2,3,4,5,6,7, 0,1,2,3,4,5,6,7
# Frame 31 = slot (31 % 8) = 7... but capture shows slot=0!
# Wait... slot starts at 0, and increments. For 32 frames: 0..7, 0..7, 0..7, 0..7
# Frame 31 would be slot = 31 % 8 = 7. But capture shows slot=0.
# So there must be something different...

# Let me re-check the capture
raw2 = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off2 = 0
records2 = []
while off2 + 13 <= len(raw2):
    rec_len = struct.unpack_from('<I', raw2, off2)[0]
    ptype = raw2[off2 + 12]
    payload = raw2[off2 + 13:off2 + 13 + rec_len - 9]
    records2.append({'type': ptype, 'payload': payload})
    off2 += 4 + rec_len
    if off2 > len(raw2): break

current2 = None
cap_full = []
for rec in records2:
    if rec['type'] != 2: continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current2 = {'data': bytearray(p[8:]), 'expected': l2cap_len}
    elif flags == 0x01 and current2:
        current2['data'].extend(p[4:])
    else: continue
    if current2 and len(current2['data']) >= current2['expected']:
        data = bytes(current2['data'][:current2['expected']])
        current2 = None
        if len(data) < 3: continue
        att_val = data[3:]
        for idx in range(len(att_val)):
            if (idx + 7 < len(att_val) and att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                flag = att_val[idx+3]
                cmd = att_val[idx+4]
                blen = (att_val[idx+5] << 8) | att_val[idx+6]
                end = idx + 7 + blen
                if end < len(att_val) and att_val[end] == 0xEF:
                    body = bytes(att_val[idx+7:end])
                    if flag == 0x80 and cmd == 0x01 and len(body) >= 5:
                        cap_full.append({
                            'seq': body[0],
                            'xm': body[1],
                            'slot': body[2],
                            'crc': (body[3]<<8)|body[4],
                            'data': body[5:]
                        })
                break

print()
print("=== CAPTURE SLOT PATTERN (actual) ===")
for i, f in enumerate(cap_full):
    expected_slot = i % 8
    match = "✓" if f['slot'] == expected_slot else "✗"
    print(f"  {match} frame {i:2d}: seq=0x{f['seq']:02x} slot={f['slot']} expected_slot={expected_slot}")
