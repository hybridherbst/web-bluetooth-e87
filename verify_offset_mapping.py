#!/usr/bin/env python3
"""Map the windowed flow: which chunks go in which window, what offsets."""

# WIN_ACKs from capture:
# seq=1 winSize=3920 nextOff=490
# seq=2 winSize=3920 nextOff=4410
# seq=3 winSize=3920 nextOff=8330
# seq=4 winSize=3920 nextOff=12250
# seq=5 winSize=490 nextOff=0

# Data frames from capture (seq 6-37, 32 chunks):
# Chunk 0-7: seq 6-13, slots 0-7  (window 1: offset 490, size 3920 => 8 chunks of 490)
# Chunk 8-15: seq 14-21, slots 0-7 (window 2: offset 4410, size 3920 => 8 chunks)
# Chunk 16-23: seq 22-29, slots 0-7 (window 3: offset 8330, size 3920)
# Chunk 24-30: seq 30-36, slots 0-6 (window 4: offset 12250, size 3920)
#   But 12250+3920=16170 > 15647, so only ceil((15647-12250)/490) = ceil(3397/490) = 7 chunks
#   Actually: 15647 - 490 (head) = 15157 tail bytes.
#   Offset 12250 in the TAIL: 12250 - 490 = 11760... NO.
#   
#   Wait: the offsets in WIN_ACK -- what are they relative to?
#   WIN_ACK 1: nextOff=490. This means "send from offset 490".
#   But the data starts with tail = img[490:]. So offset 490 = img[490:] which = tail[0:]
#   
#   WIN_ACK 2: nextOff=4410. img[4410:] = tail[3920:]
#   4410 = 490 + 3920 ✓
#   
#   WIN_ACK 3: nextOff=8330. img[8330:] = tail[7840:]
#   8330 = 490 + 7840 ✓
#   
#   WIN_ACK 4: nextOff=12250. img[12250:] = tail[11760:]
#   12250 = 490 + 11760 ✓
#   12250 + 3920 = 16170 > 15647 => only 15647 - 490 - 11760 = 3397 bytes of tail remain
#   ceil(3397 / 490) = 7 chunks (6 full + 1 partial of 457)
#   This matches: chunks 24-30 = 7 chunks
#   
#   WIN_ACK 5: nextOff=0. The COMMIT chunk. img[0:490] = head.
#   winSize=490, so exactly 1 chunk of 490 bytes.

# So the offsets are RELATIVE TO THE ORIGINAL IMAGE, not the rotated data!
# offset=490 means img[490:]
# offset=0 means img[0:]

# Our code does: rotatedData = tail + head, then chunks rotatedData[nextOffset:nextOffset+winSize]
# But when WIN_ACK says nextOffset=490, we should be sending img[490:] which is tail[0:]
# And when WIN_ACK says nextOffset=0, we should be sending img[0:] which is head!

# Wait, but our code's rotatedData is tail+head. So:
# rotatedData[0:] = tail = img[490:]  -- but WIN_ACK says nextOff=490 for this!
# rotatedData[15157:] = head = img[0:490] -- but WIN_ACK says nextOff=0 for this!

# So our code uses WIN_ACK nextOffset to index into rotatedData, but the device
# uses nextOffset relative to the ORIGINAL image!

# This means:
# WIN_ACK nextOff=490 → our code sends rotatedData[490:] = tail[490:] = img[980:]  ← WRONG!
#                        should send img[490:] = tail[0:] = rotatedData[0:]

# AH WAIT. Let me re-read the code more carefully...

# Let me check: what does our code ACTUALLY do with nextOffset?
# In sendChunksAt(offset, winSize):
#   for c in range(chunksInWindow):
#     chunkOffset = offset + c * E87_DATA_CHUNK_SIZE
#     payload = rotatedData.slice(chunkOffset, ...)
#
# So if WIN_ACK says nextOff=490, we do rotatedData[490:490+490] = tail[490:980]
# But the capture says at offset 490, chunk 0 starts with bytes "44454647"
# Let's check: what's at tail[0:4] vs tail[490:4]?

img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()
tail = img[490:]

print("=== OFFSET MAPPING ===")
print(f"img[490:494] = {img[490:494].hex()}")
print(f"tail[0:4]    = {tail[0:4].hex()}")
print(f"tail[490:494]= {tail[490:494].hex()}")
print(f"Capture chunk 0 first bytes: 44454647")
print()

# If capture chunk 0 first bytes are 44454647, and img[490:494] = that,
# then the device's nextOff=490 means "send from img[490:]"
# But if we index rotatedData[490:], we get tail[490:] = img[980:]
# Unless... the first WIN_ACK starts the transfer, and it says nextOff=490.
# Maybe our code is handling the FIRST window differently?

# Let me check: what does the initial code path look like?
# 1. File meta (0x1b) sent
# 2. Wait for first WIN_ACK
# 3. firstWinAck body: seq=1, status=0, winSize=3920, nextOff=490
# 4. Call sendChunksAt(490, 3920)
# 5. This sends rotatedData[490:490+3920] which is tail[490:4410] = img[980:4900]
#
# BUT the capture shows data chunks starting at img[490:] = tail[0:]!
# So we're off by 490 bytes!

# The issue: WIN_ACK nextOffset is in ORIGINAL IMAGE coordinates.
# Our rotatedData starts at tail (img[490:]), so offset 490 in image space
# corresponds to offset 0 in rotatedData space.
# We need: rotatedData_offset = nextOffset - 490 (for tail portion)
# And for nextOffset=0: that's the head, at rotatedData_offset = 15157

# OR: don't use rotatedData at all. Use the original image directly.
# When nextOffset=X, send img[X:X+winSize] (with wrapping at the end for head).

# Actually, simpler: just index the original image with nextOffset!
# The WIN_ACK tells us where in the ORIGINAL image to read from.
# For the commit (nextOff=0): send img[0:490] = JFIF header
# For nextOff=490: send img[490:490+3920] = first 3920 bytes of tail

print("=== VERIFICATION: WIN_ACK offsets as image coordinates ===")
win_acks = [
    (1, 3920, 490),    # window 1
    (2, 3920, 4410),   # window 2
    (3, 3920, 8330),   # window 3
    (4, 3920, 12250),  # window 4
    (5, 490, 0),       # commit
]

chunk_idx = 0
capture_crcs = [
    0xc0b8, 0x3968, 0x723a, 0x6d88, 0x7098, 0x3197, 0x0fa2, 0xc4b6,
    0xa330, 0xe9eb, 0x5542, 0x377e, 0xf1d6, 0xe0bf, 0x9527, 0x56a8,
    0xf81e, 0xdc0a, 0x507c, 0x0874, 0x2ac6, 0x440b, 0x3bb9, 0xeb0b,
    0x1fce, 0x7a14, 0xedee, 0x7074, 0xc39f, 0x22ea, 0xdb1f, 0xb03e,
]

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

all_match = True
for seq, winSize, nextOff in win_acks:
    chunks_in_win = 0
    remaining = winSize
    off = nextOff
    print(f"\nWindow {seq}: nextOff={nextOff}, winSize={winSize}")
    while remaining > 0 and off < len(img):
        chunk_len = min(490, remaining, len(img) - off)
        payload = img[off:off+chunk_len]
        crc = crc16_xmodem(payload)
        cap_crc = capture_crcs[chunk_idx]
        match = "✓" if crc == cap_crc else "✗"
        if crc != cap_crc:
            all_match = False
        print(f"  Chunk {chunk_idx}: img[{off}:{off+chunk_len}] len={chunk_len} crc=0x{crc:04x} cap=0x{cap_crc:04x} {match}")
        chunk_idx += 1
        off += chunk_len
        remaining -= chunk_len
        chunks_in_win += 1
    print(f"  ({chunks_in_win} chunks in this window)")

print(f"\n=== ALL CRCs MATCH: {all_match} ===")
