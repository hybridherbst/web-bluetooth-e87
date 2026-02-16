#!/usr/bin/env python3
"""Verify chunk ordering in capture: chunk 0 is sent last."""

data = open('/Users/herbst/git/bluetooth-tag/captured_image.jpg', 'rb').read()
print(f'File size: {len(data)} bytes')
print(f'First 16 bytes (offset 0): {data[:16].hex()}')
print(f'Bytes at offset 490:       {data[490:506].hex()}')
print()
print(f'Offset 0 = FF D8 (JPEG SOI)? {data[:2] == bytes([0xff, 0xd8])}')
print(f'Offset 490 starts with 44 45? {data[490:492].hex()}')
print()

# Capture frame order analysis:
# seq 0x06 (first data frame sent): data = 44 45 46 47... = file offset 490
# seq 0x24 (last normal frame):     data = file end
# seq 0x25 (sent last):             data = FF D8 FF E0... = file offset 0
#
# Conclusion: original app sends chunks 1..N first, then chunk 0 last
# Chunk 0 (the JPEG header) acts as a "commit" signal

# Count chunks
total_chunks = -(-len(data) // 490)  # ceil division
print(f'Total chunks: {total_chunks}')
print(f'  Chunk 0: offset 0, size 490 (JPEG header)')
print(f'  Chunk 1: offset 490, size 490')
print(f'  ...')
last_offset = (total_chunks - 1) * 490
last_size = len(data) - last_offset
print(f'  Chunk {total_chunks-1}: offset {last_offset}, size {last_size}')
print()
print('Capture send order:')
print(f'  First: chunk 1 (offset 490) through chunk {total_chunks-1} (offset {last_offset})')
print(f'  Last:  chunk 0 (offset 0) — JPEG header as commit')
print()

# Verify CRC of the first chunk in capture
# From capture: seq=0x06, slot=0, CRC bytes = C0 B8
# CRC should be for the data at offset 490 (NOT offset 0!)
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

chunk0 = data[0:490]
chunk1 = data[490:980]
print(f'CRC of chunk 0 (offset 0):   0x{crc16xmodem(chunk0):04x}')
print(f'CRC of chunk 1 (offset 490): 0x{crc16xmodem(chunk1):04x}')
print(f'Capture CRC for first frame: 0xC0B8')
print()
if crc16xmodem(chunk1) == 0xC0B8:
    print('✓ CONFIRMED: First data frame has CRC of chunk 1 (offset 490)')
    print('  => Original app sends chunk 1 first, chunk 0 last!')
elif crc16xmodem(chunk0) == 0xC0B8:
    print('✓ First data frame has CRC of chunk 0 (offset 0)')
    print('  => Original app sends in normal order')
else:
    print('✗ Neither CRC matches — need more investigation')
    print(f'  Expected 0xC0B8, got chunk0=0x{crc16xmodem(chunk0):04x}, chunk1=0x{crc16xmodem(chunk1):04x}')
