#!/usr/bin/env python3
"""Find the exact rotation point that matches the capture."""

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

jpeg = open('/Users/herbst/git/bluetooth-tag/captured_image.jpg', 'rb').read()
CHUNK = 490
total = len(jpeg)  # 15647

# Parse capture frames 
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

# The transmitted data as a flat stream (in capture frame order)
transmitted = b''.join(fd for _, _, _, fd in capture_frames)
print(f"Transmitted total: {len(transmitted)} bytes")
print(f"JPEG total:        {len(jpeg)} bytes")

# The capture's last two frames:
print(f"\nFrame 30 (seq=0x{capture_frames[30][0]:02x}): {len(capture_frames[30][3])} bytes, crc=0x{capture_frames[30][2]:04x}")
print(f"Frame 31 (seq=0x{capture_frames[31][0]:02x}): {len(capture_frames[31][3])} bytes, crc=0x{capture_frames[31][2]:04x}")
print(f"Frame 31 starts with: {capture_frames[31][3][:8].hex()}")

# So the stream is:
# Frames 0-29: 30 * 490 = 14700 bytes (from jpeg at some offset)
# Frame 30: 457 bytes (the remainder)  
# Frame 31: 490 bytes (the JPEG header)
# Total: 14700 + 457 + 490 = 15647 ✓

# The stream order matches: jpeg[490:] + jpeg[0:490]
# BUT jpeg[490:] is 15647-490 = 15157 bytes
# 15157 / 490 = 30.93... → 30 full chunks of 490 = 14700, plus 1 chunk of 457
# Then the last chunk is jpeg[0:490] = 490 bytes
# So the rotation IS jpeg[490:] + jpeg[0:490], the chunking just naturally
# makes frame 30 = 457 bytes and frame 31 = 490 bytes

# The problem is our code chunks the rotated data as:
#   chunk 0 = rotated[0:490]     = jpeg[490:980]     ← 490 bytes ✓
#   ...
#   chunk 30 = rotated[14700:15190] = jpeg[15190:15647] + jpeg[0:33]  ← 490 bytes ✗ should be 457!!
#   chunk 31 = rotated[15190:15647] = jpeg[33:490]  ← 457 bytes ✗ should be 490!!

# Wait no. rotated = jpeg[490:] + jpeg[0:490] = 15157 + 490 = 15647 bytes
# chunk 0 = rotated[0:490]     OK
# chunk 30 = rotated[14700:15190]  OK (490 bytes since 15190 < 15647)
# chunk 31 = rotated[15190:15647]  = 457 bytes
# BUT capture has frame 30 = 457 bytes and frame 31 = 490 bytes!

# So the rotation is DIFFERENT. Let me find the actual rotation point.
# The capture's frame 31 (490 bytes) contains jpeg[0:490] (the JFIF header).
# The capture's frame 30 (457 bytes) must be the tail end of jpeg.
# Frame 30's data should be jpeg[15190:15647] = last 457 bytes

print(f"\nCapture frame 30 data starts: {capture_frames[30][3][:8].hex()}")
print(f"JPEG[15190:15198]:             {jpeg[15190:15198].hex()}")
print(f"Match: {capture_frames[30][3] == jpeg[15190:15647]}")

print(f"\nCapture frame 31 data starts: {capture_frames[31][3][:8].hex()}")
print(f"JPEG[0:8]:                     {jpeg[0:8].hex()}")
print(f"Match: {capture_frames[31][3] == jpeg[0:490]}")

# So the actual split is:
# Frames 0-29: jpeg[490 : 490+30*490] = jpeg[490 : 15190]  (14700 bytes)
# Frame 30: jpeg[15190 : 15647]  (457 bytes)
# Frame 31: jpeg[0 : 490]  (490 bytes)
# Total sent: 14700 + 457 + 490 = 15647 ✓

# This means the chunking treats the tail part (jpeg[490:]) differently
# from what a simple sequential chunking of the rotated array would do.
# The chunks are:
#   - jpeg[490:] → chunk 0-30, using CHUNK_SIZE=490, last one is 457
#   - jpeg[0:490] → chunk 31, always full 490

# So rather than rotating the data and sequentially chunking,
# the correct approach is:
#   1. Send jpeg[490:] as chunks (30 full + 1 short = 31 chunks)
#   2. Send jpeg[0:490] as the final chunk

# OR equivalently: DON'T rotate the byte array. Instead, iterate chunks 
# starting from chunk 1 through end, then chunk 0 last.
# This way the size of each chunk matches the capture.

# Actually wait - let me reconsider. What if we DON'T rotate,
# and instead just reorder chunk sends?

# Original JPEG chunks:
# chunk_0 = jpeg[0:490]     → 490 bytes (JFIF header)
# chunk_1 = jpeg[490:980]   → 490 bytes  
# ...
# chunk_31 = jpeg[15190:15647] → 457 bytes (last/short chunk)

# Capture send order:
# send chunk_1, chunk_2, ..., chunk_31, chunk_0
# = 30 full chunks + 1 short chunk + 1 full chunk = 32 frames
# And IMPORTANTLY: the CRC and data for each frame match the original chunk

print("\n--- Verify chunk reordering approach ---")
chunks = []
off = 0
while off < total:
    end = min(off + CHUNK, total)
    chunks.append(jpeg[off:end])
    off = end

print(f"Total chunks: {len(chunks)}")
print(f"Chunk 0: {len(chunks[0])} bytes, starts with {chunks[0][:4].hex()}")
print(f"Chunk 31: {len(chunks[31])} bytes")

# Send order: chunks[1], chunks[2], ..., chunks[31], chunks[0]
send_order = list(range(1, len(chunks))) + [0]
print(f"Send order: {send_order}")

all_match = True
for frame_idx, chunk_idx in enumerate(send_order):
    chunk = chunks[chunk_idx]
    cap_seq, cap_slot, cap_crc, cap_data = capture_frames[frame_idx]
    our_crc = crc16xmodem(chunk)
    
    match_crc = our_crc == cap_crc
    match_data = chunk == cap_data
    match_len = len(chunk) == len(cap_data)
    
    if not (match_crc and match_data and match_len):
        all_match = False
        print(f"  ✗ frame {frame_idx:2d}: chunk[{chunk_idx:2d}] len={len(chunk)}/{len(cap_data)} "
              f"crc=0x{our_crc:04x}/0x{cap_crc:04x} data_match={match_data}")
    else:
        print(f"  ✓ frame {frame_idx:2d}: chunk[{chunk_idx:2d}] len={len(chunk)} crc=0x{our_crc:04x}")

print()
if all_match:
    print("✓✓✓ CHUNK REORDERING APPROACH: ALL 32 FRAMES MATCH!")
else:
    print("✗ Some frames don't match")
