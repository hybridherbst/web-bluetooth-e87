#!/usr/bin/env python3
"""Verify exact total data transferred and figure out the real chunk size."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

# We know:
# - 32 data frames (cmd 0x01, flag 0x80)
# - 31 have body_len=495, 1 has body_len=462
# - body = [seq(1), 0x1D(1), slot(1), data...]
# - So payload sizes: 31 × 492 + 459 = 15711

# Window acks:
# WA0: seq=01 window=3920 offset=490    (after 0 data frames, before data starts)
# WA1: seq=02 window=3920 offset=4410   = 490 + 3920
# WA2: seq=03 window=3920 offset=8330   = 490 + 2×3920
# WA3: seq=04 window=3920 offset=12250  = 490 + 3×3920
# WA4: seq=05 window=490  offset=0      (final window)

# The offset field progresses by 3920 = 8 × 490
# Starting offset = 490

# 490 * 8 frames = 3920 per window
# 4 full windows + 1 partial: 4×3920 = 15680 + last window of 490 = 16170
# But that's not 7997 either

# WAIT. seq=01 for WA0 doesn't match any data frame seq. 
# The WA seq is a SEPARATE counter for window acks themselves!
# WA0 seq=1 (1st ack), WA1 seq=2 (2nd ack), etc.
# The data frame seqs go 0x06-0x25 (32 frames).

# Let me check: are some data frames sent AFTER the last window ack?
# WA4 is at record 1760, and seq=0x25 data is at record 1761
# So yes, 1 frame after WA4.

# Data distribution:
# WA0 (rec 1613): then 8 frames (seq 0x06-0x0d) → WA1 (rec 1655)
# WA1: then 8 frames (0x0e-0x15) → WA2 (rec 1693)
# WA2: then 8 frames (0x16-0x1d) → WA3 (rec 1730)
# WA3: then 7 frames (0x1e-0x24) → WA4 (rec 1760)
# WA4: then 1 frame (0x25) → cmd 0x20

# So: 8+8+8+7+1 = 32 frames

# The WA4 says window=490 which would be exactly 1 frame worth.
# If each frame carries 490 bytes of data:
#   31 × 490 + (462-5) = 15190 + 457 = 15647
# If each frame carries 492 bytes:
#   31 × 492 + (462-3) = 15252 + 459 = 15711

# Neither is 7997. So maybe the file is NOT 7997 bytes!
# Let me check: maybe 0x1F3D is not the file size.
# metadata body: 05 00 00 3D 1F 66 AB 66 66 62 39 33 38 65 31 2E 74 6D 70 00
# body[0] = seq = 5
# body[1] = 0x00
# body[2] = 0x00
# body[3:5] = 3D 1F → LE16 = 0x1F3D = 7997, BE16 = 0x3D1F = 15647!

# 15647 BE16!!! 
# 31×490+457 = 15647!!! IT MATCHES!

print("AHA! The file size is BIG ENDIAN in the metadata!")
print(f"body[3:5] = 0x3D 0x1F = BE16 = {0x3D1F} = 15647")
print(f"31 × 490 + 457 = {31*490 + 457}")
print(f"Match: {31*490 + 457 == 15647}")

# So:
# - File size in metadata is BIG ENDIAN 16-bit!
# - Data per frame = 490 bytes (5 bytes overhead: seq, 0x1D, slot, + 2 unknown)
# - Total: 15647 bytes

# But wait, we also need to check: is the short frame payload = 462-5=457 or 462-3=459?
# If 490 per full frame and body_len=495: overhead = 495-490 = 5
# The 5 overhead bytes are: seq(1), 0x1D(1), slot(1), ???(2)
# If short frame: 462-5 = 457 → 31*490+457 = 15647 ✓ PERFECT MATCH

# Now: what are the 2 mystery bytes?
# First data frame body bytes 3-4: 0xC0 0xB8
# These might be a CRC-16 of the payload, or a 2-byte file offset BE
# 0xC0B8 = 49336 → not a file offset
# Maybe it's a CRC of the 490 payload bytes?

# Let me check if it could be the frame offset in the file (BE)
# Frame 0: file offset 0 → 0x0000
# Frame 1: file offset 490 → 0x01EA
# That doesn't match 0xC0B8

# Maybe the mystery bytes are part of the JPEG data itself
# The JPEG data would be XORed or encrypted
# The last frame has: body[3:5] = B0 3E, then body[5:] = FF D8 FF E0...
# So body[3:5] = B0 3E before the JPEG header

# Actually wait: body[3]=0xB0 body[4]=0x3E then body[5]=FF body[6]=D8
# If we treat body[3:] as all data: 492 bytes per frame
# Then total = 31*492 + 459 = 15711
# That doesn't match the BE16 file size of 15647

# But if overhead is 5: 490 per frame
# 31*490 + 457 = 15647 ✓

# OR: overhead is 3 (just seq, 0x1D, slot) and the file size is actually 15711
# 15711 = 0x3D5F → body[3:5] should be 3D 5F (BE) or 5F 3D (LE)
# But body[3:5] = 3D 1F. NOT 3D 5F.

# Hmm. 0x3D1F = 15647 BE. Let me double check:
# 32 frames total. Last frame (seq 0x24) has body_len=462, all others have 495.
# If payload = body_len - 5:
#   31 * (495-5) + (462-5) = 31*490 + 457 = 15190+457 = 15647
# 0x3D1F = 15647 ✓✓✓

# But wait, there's also seq 0x25 with body_len=495 AFTER the short frame!
# That's frame 32. If we include it:
#   31*490 + 457 + 490 = 16137
# With all 32: 30*490 + 457 + 490 = 15647? No: 30*490=14700+457+490=15647. Yes!
# 30 full frames + 1 short + 1 full = 30*490 + 457 + 490 = 15647

# Hmm wait that's 32 frames: frame indices 0-31
# frame 0-30 (indices 0x06-0x24): 31 frames, one is short (0x24 with 462 body)
# frame 31 (index 0x25): 1 frame with 495 body
# 30 * 490 + 457 + 490 = 14700 + 457 + 490 = 15647 ✓

# So E87_DATA_CHUNK_SIZE should be 490, not 492!

print(f"\n{'='*60}")
print("CONCLUSIONS:")
print(f"{'='*60}")
print(f"E87_DATA_CHUNK_SIZE should be 490 (not 492)")
print(f"Body per frame = [seq(1), 0x1D(1), slot(1), unknown(2), filedata(490)] = 495")
print(f"The 2 unknown bytes at body[3:4] are unknown overhead")
print(f"File size in metadata is BE16 (not LE16!)")
print(f"Total 32 frames: 30×490 + 457 + 490 = 15647")
print(f"Short frame payload: 462-5 = 457")

# But WAIT: we need to figure out what body[3:4] actually is.
# If the device needs it, we need to send it correctly.
# Let me check multiple frames' body[3:4]:

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'payload': payload, 'type': ptype})
    off += 4 + rec_len
    if off > len(raw):
        break

print(f"\nBody[3:4] (mystery bytes) for each data frame:")
for i, rec in enumerate(records):
    p = rec['payload']
    idx = p.find(b'\xFE\xDC\xBA\x80\x01')
    if idx < 0:
        continue
    body_len = (p[idx+5] << 8) | p[idx+6]
    if body_len < 3 or body_len > 600:
        continue
    body_start = idx + 7
    if body_start + 5 > len(p):
        continue
    seq = p[body_start]
    subcmd = p[body_start+1]
    slot = p[body_start+2]
    b3 = p[body_start+3]
    b4 = p[body_start+4]
    if subcmd != 0x1D:
        continue
    # Check if these could be a running CRC or checksum
    mystery_be = (b3 << 8) | b4
    mystery_le = (b4 << 8) | b3
    print(f"  seq=0x{seq:02x} slot={slot} mystery=0x{b3:02x}{b4:02x} (BE={mystery_be} LE={mystery_le})")
