#!/usr/bin/env python3
"""Figure out the EXACT chunking scheme from the capture.
The capture has 32 data frames, each with a CRC over their payload.
We know the image, so let's figure out which bytes each chunk contains."""
import struct

img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()
print(f"Image size: {len(img)} bytes")

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

# CRCs from capture, along with first_data bytes and payload sizes
capture_data = [
    # (crc, first_4_bytes_hex, payload_size_in_capture)
    (0xc0b8, "44454647", 232),  # chunk 0, slot 0
    (0x3968, "0d92c063", 232),
    (0x723a, "53771d8e", 232),
    (0x6d88, "5350e2cd", 232),
    (0x7098, "c0c56522", 232),
    (0x3197, "a905ef28", 232),
    (0x0fa2, "0d02b119", 232),
    (0xc4b6, "2c38a771", 232),
    (0xa330, "7380290d", 232),
    (0xe9eb, "54bb9424", 232),
    (0x5542, "086604d0", 232),
    (0x377e, "d1195cb1", 232),
    (0xf1d6, "e0a8a5db", 232),
    (0xe0bf, "3e12c3e9", 232),
    (0x9527, "8d38e3c6", 232),
    (0x56a8, "352c2003", 232),
    (0xf81e, "9392c7b7", 232),
    (0xdc0a, "94d02b15", 232),
    (0x507c, "62b36688", 232),
    (0x0874, "b2477a2c", 232),
    (0x2ac6, "1a6e0503", 232),
    (0x440b, "156427b5", 232),
    (0x3bb9, "889f6a40", 232),
    (0xeb0b, "e34b10fb", 232),
    (0x1fce, "56855a4c", 232),
    (0x7a14, "23135ba4", 232),
    (0xedee, "062cb2b4", 232),
    (0x7074, "e9e8f634", 232),
    (0xc39f, "e6a9c12b", 232),
    (0x22ea, "340acc69", 232),
    (0xdb1f, "af142467", 232),
    (0xb03e, "ffd8ffe0", 232),  # commit chunk (slot 0), starts with JFIF header
]

print(f"\nCapture has {len(capture_data)} chunks")

# The first 4 bytes of each chunk's payload are visible in the capture
# Let's find where each occurs in the image

# Theory 1: Simple rotation img[490:] + img[:490], chunked at 490 bytes
# We showed this doesn't match for the last 2 chunks.

# Theory 2: The chunks use a DIFFERENT rotation or chunking
# Look at the commit chunk: it starts with FFD8FFE0 which is img[0:4]
# Its CRC is 0xb03e
# If the commit chunk is img[0:490], crc should be:
commit_crc = crc16_xmodem(img[0:490])
print(f"\nCRC of img[0:490] (full JFIF header): 0x{commit_crc:04x}")
print(f"Capture commit CRC: 0x{capture_data[-1][0]:04x}")
print(f"Match: {commit_crc == capture_data[-1][0]}")

# Theory 3: Tail chunks are img[490:] chunked, but each chunk is exactly 490 bytes,
# AND the commit chunk is separately img[0:490]
# So it's NOT a flat rotation — it's TWO separate sends:
# Part 1: img[490:] in 490-byte chunks (31 chunks)
# Part 2: img[0:490] as a single chunk (1 chunk)
tail = img[490:]
print(f"\nTail length: {len(tail)}")
print(f"Tail chunks at 490: {len(tail) / 490} (need to check last chunk)")

# Check tail chunking
print("\n=== Tail chunking (img[490:]) at 490-byte intervals ===")
all_match = True
for i in range(31):
    offset = i * 490
    end = min(offset + 490, len(tail))
    payload = tail[offset:end]
    crc = crc16_xmodem(payload)
    cap = capture_data[i][0]
    match = "✓" if crc == cap else "✗"
    if crc != cap:
        all_match = False
        print(f"  Chunk {i:2d}: tail[{offset}:{end}] len={len(payload)} crc=0x{crc:04x} cap=0x{cap:04x} {match}")
    if i < 3 or i > 28 or crc != cap:
        print(f"  Chunk {i:2d}: tail[{offset}:{end}] len={len(payload)} crc=0x{crc:04x} cap=0x{cap:04x} {match}")

# Last tail chunk
last_tail_chunk = tail[30*490:]
print(f"\n  Last tail chunk: tail[{30*490}:{len(tail)}] = {len(last_tail_chunk)} bytes")
print(f"  CRC: 0x{crc16_xmodem(last_tail_chunk):04x}")
print(f"  Capture chunk 30 CRC: 0x{capture_data[30][0]:04x}")

# So if we have 31 tail chunks + 1 head chunk = 32, but last tail chunk is only 
# 15157 - 30*490 = 15157 - 14700 = 457 bytes

# What if the last tail chunk is PADDED to 490 bytes?
padded = last_tail_chunk + b'\x00' * (490 - len(last_tail_chunk))
print(f"\n  Padded last tail chunk CRC: 0x{crc16_xmodem(padded):04x}")
print(f"  Capture: 0x{capture_data[30][0]:04x}")

# What if the last tail chunk INCLUDES the first bytes of the head?
mixed = tail[30*490:] + img[0:490 - len(last_tail_chunk)]
print(f"\n  Mixed chunk (tail end + head start): {len(mixed)} bytes")
print(f"  CRC: 0x{crc16_xmodem(mixed):04x}")
print(f"  Capture: 0x{capture_data[30][0]:04x}")
print(f"  First 4 bytes: {mixed[:4].hex()}")
print(f"  Capture first 4: {capture_data[30][1]}")

# AHA! Let's check if "af142467" appears in the tail
target = bytes.fromhex("af142467")
for pos in range(len(img)):
    if img[pos:pos+4] == target:
        print(f"\n  Found 'af142467' at img offset {pos}")
        print(f"  Relative to tail start (490): {pos - 490}")
        
for pos in range(len(tail)):
    if tail[pos:pos+4] == target:
        print(f"  Found 'af142467' at tail offset {pos}")
        expected_chunk = pos // 490
        expected_offset_in_chunk = pos % 490
        print(f"  Expected in chunk {expected_chunk}, offset {expected_offset_in_chunk}")
