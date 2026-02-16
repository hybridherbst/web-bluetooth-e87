#!/usr/bin/env python3
"""Re-examine the chunk ordering claim. Was the CRC proof circular?"""

# The captured_image.jpg was constructed as: frame[0x25] data + frame[0x06..0x24] data
# So captured_image.jpg[0:490] = frame[0x25] data (JFIF header)
# And captured_image.jpg[490:980] = frame[0x06] data
#
# When I checked: CRC of captured_image.jpg[490:980] == 0xC0B8 == frame[0x06]'s CRC
# That's TRIVIALLY TRUE because I put frame[0x06] at offset 490!
# This was CIRCULAR REASONING — not proof of chunk ordering!

# The REAL question: what order does the device expect?
# Option A: Sequential (offset 0, 490, 980, ...)  — our original code, device showed progress
# Option B: Chunk 1 first, chunk 0 last — broke the device

# Let's check what the file looks like in PURE sequential order
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw): break

current = None
data_frames = []  # (seq, slot, file_data)
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
                            file_data = bytes(body[5:])
                            data_frames.append((seq, slot, file_data))
                    break
        current = None

print(f"Extracted {len(data_frames)} data frames")
print()

# Option 1: Pure sequential order (frame 0,1,2,...31)
seq_data = b''.join(d for _, _, d in data_frames)
print(f"Option A - Sequential order (frames as sent):")
print(f"  Size: {len(seq_data)} bytes")
print(f"  First 8: {seq_data[:8].hex()}")
print(f"  Last 8: {seq_data[-8:].hex()}")
if seq_data[:2] == b'\xff\xd8':
    print(f"  ✓ Valid JPEG start")
else:
    print(f"  ✗ NOT valid JPEG start")

# Option 2: Last frame first (the "alt" reconstruction)
alt_data = data_frames[-1][2] + b''.join(d for _, _, d in data_frames[:-1])
print(f"\nOption B - Last frame first (alt reconstruction):")
print(f"  Size: {len(alt_data)} bytes")
print(f"  First 8: {alt_data[:8].hex()}")
print(f"  Last 8: {alt_data[-8:].hex()}")
if alt_data[:2] == b'\xff\xd8':
    print(f"  ✓ Valid JPEG start")
else:
    print(f"  ✗ NOT valid JPEG start")

# Option 3: First 31 frames only (frame 0x25 is re-send of frame 0)
# If seq 0x25 is just a duplicate/re-send, the file is frames 0x06-0x24
only31 = b''.join(d for _, _, d in data_frames[:31])
print(f"\nOption C - First 31 frames only (skip re-sent):")
print(f"  Size: {len(only31)} bytes")
print(f"  First 8: {only31[:8].hex()}")
if only31[:2] == b'\xff\xd8':
    print(f"  ✓ Valid JPEG start")
else:
    print(f"  ✗ NOT valid JPEG start")

print()
print("=== CONCLUSION ===")
print("Only Option B produces a valid JPEG, but the CRC 'proof' was circular.")
print("The original app likely processes chunks in order 0-30, then re-sends chunk 0.")
print("The device uses seq/slot numbers to place data, not arrival order.")
print("Our code should send chunks in SEQUENTIAL ORDER (0, 1, 2, ...) like before.")
print()

# Verify: does the capture file size match the metadata?
print("Metadata file size from capture: 15647 (0x3D1F)")
print(f"Option A size: {len(seq_data)} (match: {len(seq_data)==15647})")
print(f"Option B size: {len(alt_data)} (match: {len(alt_data)==15647})")
print(f"Option C size: {len(only31)} (match: {len(only31)==15647})")
print()

# If Option A = 15647, the file IS frames in sequential order, 
# and the file on the device starts with "44 45 46 47"
# which might be a custom format, not raw JPEG
if len(seq_data) == 15647:
    print("Sequential order = 15647 bytes = matches metadata.")
    print("This means all 32 frames ARE the file in order.")
    print("The JPEG header at offset 15157 might be intentional (device-specific format).")
elif len(only31) == 15647:
    print("31 frames = 15647 bytes = matches metadata.")
    print("Frame 0x25 is an extra re-sent chunk, not part of the file.")
