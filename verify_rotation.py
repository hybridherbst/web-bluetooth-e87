#!/usr/bin/env python3
"""Verify rotation matches capture: simulate what our JS code does."""

# Our JS code does:
#   rotatedBytes = jpeg[490:] + jpeg[0:490]
# Then sends rotatedBytes sequentially as chunks 0, 1, 2, ...
# 
# We need to verify this produces the same CRCs as the capture.

import struct

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

# Load the reconstructed JPEG (the valid one)
jpeg = open('/Users/herbst/git/bluetooth-tag/captured_image.jpg', 'rb').read()
print(f"Valid JPEG: {len(jpeg)} bytes, starts with {jpeg[:4].hex()}")

# Apply the same rotation our JS code does
rotated = bytes(jpeg[490:]) + bytes(jpeg[:490])
print(f"Rotated:    {len(rotated)} bytes, starts with {rotated[:8].hex()}")
print(f"Rotated ends with: {rotated[-8:].hex()}")
print()

# Now extract CRCs from capture frames
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
capture_frames = []
for rec in records:
    if rec['type'] not in (2, 3): continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'dir': rec['type'], 'data': bytearray(p[8:]), 'expected': l2cap_len}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    else: continue
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        if len(data) >= 3 and current['dir'] == 2:
            att_val = data[3:]
            for idx in range(len(att_val)):
                if (idx + 7 < len(att_val) and att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                    flag = att_val[idx+3]
                    cmd = att_val[idx+4]
                    blen = (att_val[idx+5] << 8) | att_val[idx+6]
                    end = idx + 7 + blen
                    if end < len(att_val) and att_val[end] == 0xEF:
                        body = att_val[idx+7:end]
                        if flag == 0x80 and cmd == 0x01 and len(body) >= 5:
                            seq = body[0]
                            slot = body[2]
                            crc_cap = (body[3] << 8) | body[4]
                            file_data = bytes(body[5:])
                            capture_frames.append((seq, slot, crc_cap, file_data))
                    break
        current = None

print(f"Capture frames: {len(capture_frames)}")
print()

# Compare: chunk our rotated data and check CRCs match capture
CHUNK = 490
all_match = True
for i, (seq, slot, crc_cap, cap_data) in enumerate(capture_frames):
    offset = i * CHUNK
    our_data = rotated[offset:offset + CHUNK]
    our_crc = crc16xmodem(our_data)
    
    match_crc = our_crc == crc_cap
    match_data = our_data == cap_data
    
    status = "✓" if (match_crc and match_data) else "✗"
    if not (match_crc and match_data):
        all_match = False
    
    print(f"  {status} chunk {i:2d} (seq=0x{seq:02x} slot={slot}): "
          f"cap_crc=0x{crc_cap:04x} our_crc=0x{our_crc:04x} "
          f"data_match={match_data} len={len(cap_data)}/{len(our_data)}")

print()
if all_match:
    print("✓✓✓ ALL CHUNKS MATCH — rotation is correct!")
else:
    print("✗✗✗ Some chunks don't match — rotation may be wrong")
