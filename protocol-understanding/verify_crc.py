#!/usr/bin/env python3
"""Verify our CRC-16 XMODEM implementation against capture data."""
import struct

# Load the captured image
img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()
print(f"Image size: {len(img)} bytes")

# CRC-16 XMODEM
def crc16_xmodem(data):
    crc = 0x0000
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xffff
            else:
                crc = (crc << 1) & 0xffff
    return crc

# Rotation: tail = img[490:], head = img[0:490]
tail = img[490:]
head = img[:490]
rotated = tail + head
print(f"Rotated: tail({len(tail)}) + head({len(head)}) = {len(rotated)} bytes")

# Calculate CRC for each chunk and compare with capture
# From capture, the CRC values for each chunk:
capture_crcs = [
    0xc0b8, 0x3968, 0x723a, 0x6d88, 0x7098, 0x3197, 0x0fa2, 0xc4b6,  # slots 0-7, window 1
    0xa330, 0xe9eb, 0x5542, 0x377e, 0xf1d6, 0xe0bf, 0x9527, 0x56a8,  # slots 0-7, window 2
    0xf81e, 0xdc0a, 0x507c, 0x0874, 0x2ac6, 0x440b, 0x3bb9, 0xeb0b,  # slots 0-7, window 3
    0x1fce, 0x7a14, 0xedee, 0x7074, 0xc39f, 0x22ea, 0xdb1f,          # slots 0-6, window 4
    0xb03e,                                                            # commit chunk
]

chunk_size = 490
total_chunks = (len(rotated) + chunk_size - 1) // chunk_size
print(f"Total chunks: {total_chunks}")
print(f"Capture CRCs: {len(capture_crcs)}")

all_match = True
for i in range(total_chunks):
    offset = i * chunk_size
    payload = rotated[offset:min(offset + chunk_size, len(rotated))]
    crc = crc16_xmodem(payload)
    cap_crc = capture_crcs[i] if i < len(capture_crcs) else None
    match = "✓" if cap_crc == crc else "✗ MISMATCH"
    if cap_crc != crc:
        all_match = False
    print(f"  Chunk {i:2d}: offset={offset:5d} len={len(payload):3d} crc=0x{crc:04x} capture=0x{cap_crc:04x} {match}")

print(f"\nAll CRCs match: {all_match}")

# Verify the commit chunk (last one) starts with FFD8
print(f"\nCommit chunk starts with: {head[:4].hex()}")
print(f"Is JFIF header: {head[0]==0xff and head[1]==0xd8}")
