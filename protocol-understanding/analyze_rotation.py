#!/usr/bin/env python3
"""Analyze the data transformation: original app rotates JPEG so header is at end."""

# The captured file in sequential frame order starts with "44 45 46 47..."
# and has the JFIF header (FF D8 FF E0) at offset 15157.
# The valid JPEG is obtained by rotating: data[15157:] + data[:15157]
# That's a rotation by 490 bytes (one chunk) — moving chunk 0 to the front.
# 
# Actually: 15647 - 15157 = 490 exactly! So the file is rotated by 490 bytes.
# Original JPEG: [CHUNK_0 (490B)] [CHUNK_1 (490B)] ... [CHUNK_31 (457B)]
# Transmitted:   [CHUNK_1] [CHUNK_2] ... [CHUNK_31] [CHUNK_0]
# = The file is rotated LEFT by 490 bytes (one chunk size)

import struct

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
data_payloads = []
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
                            data_payloads.append(bytes(body[5:]))
                    break
        current = None

# Reconstruct transmitted file (sequential order)
transmitted = b''.join(data_payloads)
print(f"Transmitted file: {len(transmitted)} bytes")

# Find JPEG SOI marker
soi_pos = transmitted.find(b'\xff\xd8\xff\xe0')
print(f"JFIF header (FF D8 FF E0) at offset: {soi_pos}")
print(f"File length - SOI position = {len(transmitted) - soi_pos}")
print(f"Chunk size = 490")
print(f"Rotation amount = {soi_pos} bytes = {soi_pos / 490:.1f} chunks")

# Reconstruct valid JPEG by rotation
jpeg = transmitted[soi_pos:] + transmitted[:soi_pos]
print(f"\nRotated JPEG: {len(jpeg)} bytes")
print(f"  First 8: {jpeg[:8].hex()}")
print(f"  Has JFIF: {jpeg[:4] == b'\\xff\\xd8\\xff\\xe0'}")

# Find EOI
eoi = jpeg.rfind(b'\xff\xd9')
print(f"  EOI at: {eoi} (file end: {len(jpeg)-1})")
print(f"  Bytes after EOI: {len(jpeg) - eoi - 2}")

# Save both versions
with open('/Users/herbst/git/bluetooth-tag/captured_transmitted.bin', 'wb') as f:
    f.write(transmitted)
print(f"\nSaved transmitted (as-sent) to captured_transmitted.bin")

with open('/Users/herbst/git/bluetooth-tag/captured_image.jpg', 'wb') as f:
    f.write(jpeg)
print(f"Saved rotated JPEG to captured_image.jpg")

# Check: is the rotation exactly E87_DATA_CHUNK_SIZE?
if soi_pos == 490:
    print(f"\n✓ Rotation is EXACTLY 490 bytes (one chunk)")
    print("  The original app rotates the JPEG left by one chunk before sending.")
    print("  OUR code should do the same: rotate left by 490 bytes before sending.")
elif soi_pos % 490 == 0:
    print(f"\n✓ Rotation is {soi_pos // 490} chunks ({soi_pos} bytes)")
else:
    print(f"\n✗ Rotation is NOT aligned to chunk boundary: {soi_pos} bytes")
    print(f"  {soi_pos} mod 490 = {soi_pos % 490}")
