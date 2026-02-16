#!/usr/bin/env python3
"""Dump AVI header details from session2.avi (simplest: 4 images, no audio)"""
import struct

data = open('/Users/herbst/git/bluetooth-tag/session2.avi', 'rb').read()

print(f"Total size: {len(data)} bytes")
print(f"RIFF: {data[:4]}")
riff_size = struct.unpack_from('<I', data, 4)[0]
print(f"RIFF size: {riff_size}")
print(f"AVI : {data[8:12]}")

# Dump first 5742 bytes as hex for template reference
hdr = data[:5742]

# Parse avih (at offset 24+8 = 32)
off = 24
print(f"\navih tag: {data[off:off+4]} size: {struct.unpack_from('<I', data, off+4)[0]}")
avih = data[off+8:off+8+56]
fields = struct.unpack_from('<14I', avih, 0)
names = ['usec_per_frame', 'max_bytes_per_sec', 'padding_granularity', 'flags',
         'total_frames', 'initial_frames', 'streams', 'suggested_buf',
         'width', 'height', 'reserved0', 'reserved1', 'reserved2', 'reserved3']
for n, v in zip(names, fields):
    print(f"  {n}={v} (0x{v:08x})")
print(f"avih raw: {avih.hex()}")

# Parse strl LIST
off = 88  # from earlier analysis
print(f"\nstrl LIST at {off}: {data[off:off+4]} size={struct.unpack_from('<I', data, off+4)[0]}")
print(f"  type: {data[off+8:off+12]}")

# strh at offset 100
off = 100
print(f"\nstrh at {off}: {data[off:off+4]} size={struct.unpack_from('<I', data, off+4)[0]}")
strh = data[off+8:off+8+56]
print(f"  fccType: {strh[0:4]}")
print(f"  fccHandler: {strh[4:8]}")
print(f"  flags: {struct.unpack_from('<I', strh, 8)[0]}")
print(f"  priority: {struct.unpack_from('<H', strh, 12)[0]}")
print(f"  language: {struct.unpack_from('<H', strh, 14)[0]}")
print(f"  initial_frames: {struct.unpack_from('<I', strh, 16)[0]}")
print(f"  scale: {struct.unpack_from('<I', strh, 20)[0]}")
print(f"  rate: {struct.unpack_from('<I', strh, 24)[0]}")
print(f"  start: {struct.unpack_from('<I', strh, 28)[0]}")
print(f"  length: {struct.unpack_from('<I', strh, 32)[0]}")
print(f"  suggested_buf: {struct.unpack_from('<I', strh, 36)[0]}")
print(f"  quality: {struct.unpack_from('<I', strh, 40)[0]}")
print(f"  sample_size: {struct.unpack_from('<I', strh, 44)[0]}")
print(f"  frame_left: {struct.unpack_from('<H', strh, 48)[0]}")
print(f"  frame_top: {struct.unpack_from('<H', strh, 50)[0]}")
print(f"  frame_right: {struct.unpack_from('<H', strh, 52)[0]}")
print(f"  frame_bottom: {struct.unpack_from('<H', strh, 54)[0]}")
print(f"strh raw: {strh.hex()}")

# strf at offset 164
off = 164
print(f"\nstrf at {off}: {data[off:off+4]} size={struct.unpack_from('<I', data, off+4)[0]}")
strf = data[off+8:off+8+40]
bi_size = struct.unpack_from('<I', strf, 0)[0]
bi_w = struct.unpack_from('<I', strf, 4)[0]
bi_h = struct.unpack_from('<I', strf, 8)[0]
bi_planes = struct.unpack_from('<H', strf, 12)[0]
bi_bits = struct.unpack_from('<H', strf, 14)[0]
bi_comp = strf[16:20]
bi_img_size = struct.unpack_from('<I', strf, 20)[0]
print(f"  bi_size={bi_size} w={bi_w} h={bi_h} planes={bi_planes} bits={bi_bits}")
print(f"  compression={bi_comp} image_size={bi_img_size}")
print(f"strf raw: {strf.hex()}")

# JUNK at 212
off = 212
junk_size = struct.unpack_from('<I', data, off+4)[0]
print(f"\nJUNK at {off}: size={junk_size}")
print(f"  content: all zeros? {all(b == 0 for b in data[off+8:off+8+junk_size])}")

# vprp at 4340
off = 4340
print(f"\nvprp at {off}: {data[off:off+4]} size={struct.unpack_from('<I', data, off+4)[0]}")
vprp = data[off+8:off+8+68]
print(f"vprp raw: {vprp.hex()}")

# JUNK at 4416
off = 4416
junk_size2 = struct.unpack_from('<I', data, off+4)[0]
print(f"\nJUNK at {off}: size={junk_size2}")

# LIST INFO at 4684
off = 4684
print(f"\nLIST INFO at {off}: size={struct.unpack_from('<I', data, off+4)[0]}")
print(f"  type: {data[off+8:off+12]}")

# ISFT at 4696
off = 4696
isft_size = struct.unpack_from('<I', data, off+4)[0]
isft = data[off+8:off+8+isft_size]
print(f"\nISFT at {off}: size={isft_size}")
print(f"  value: {isft}")

# JUNK at 4718
off = 4718
junk_size3 = struct.unpack_from('<I', data, off+4)[0]
print(f"\nJUNK at {off}: size={junk_size3}")

# movi LIST at 5742
off = 5742
print(f"\nmovi LIST at {off}: size={struct.unpack_from('<I', data, off+4)[0]}")

# idx1
# Find idx1
idx1_off = data.find(b'idx1')
if idx1_off >= 0:
    idx1_size = struct.unpack_from('<I', data, idx1_off+4)[0]
    print(f"\nidx1 at {idx1_off}: size={idx1_size}")
    # Each index entry: 4+4+4+4 = 16 bytes
    n_entries = idx1_size // 16
    print(f"  entries: {n_entries}")
    for i in range(min(n_entries, 6)):
        e_off = idx1_off + 8 + i * 16
        chunk_id = data[e_off:e_off+4]
        flags = struct.unpack_from('<I', data, e_off+4)[0]
        offset = struct.unpack_from('<I', data, e_off+8)[0]
        size = struct.unpack_from('<I', data, e_off+12)[0]
        print(f"  [{i}] id={chunk_id} flags=0x{flags:08x} offset={offset} size={size}")

# Key: the header is 5742 bytes, everything before movi
# We need to replicate this structure for our AVI builder
print(f"\n\nTotal header size (before movi data): {5742 + 12} bytes")
print(f"Header bytes (RIFF to movi start): {5754}")
