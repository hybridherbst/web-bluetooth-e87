#!/usr/bin/env python3
"""
Quick analysis: what are the FD02 writes BETWEEN sessions?
Focus on 9ed30bc6 and 9ef40bdc patterns.
Also decode the FD03 notification 9e..c7 patterns (screen config?)
"""

# From capture analysis:
# cap.pklg (single image):
#   FD02 before upload: 9eb50b29010080, 9ed30bc6010001, 9ef40bdc01000c
#
# cap-extended.pklg:
#   Before session 1 (15s video):
#     9ed30bc6010001  → at 1771267411.395
#     9ef40bdc01000c  → at 1771267413.694
#   Before session 2 (4-image seq):
#     9ed30bc6010001  → at 1771267494.010
#     9ef40bdc01000c  → at 1771267494.269
#   Before session 3 (3s video):
#     9eb50b29010080  → at 1771267541.732
#     9ed30bc6010001  → at 1771267542.412
#     then:
#     9ed30bc6010001  → at 1771267550.079
#     9ef40bdc01000c  → at 1771267550.334

# These FD02 writes are IDENTICAL between image and video!
# 9ed30bc6010001 and 9ef40bdc01000c always appear before each session.
# The only difference is 9eb50b29010080 appears before some sessions (battery check?)

# Key finding: the PROTOCOL is the same for video and image!
# The only differences are:
# 1. FILE_META body[1:5] = 32-bit file size (not 16-bit)
# 2. The file content is an AVI container (RIFF/AVI with MJPG frames)
# 3. FILE_COMP response uses .avi extension instead of .jpg

# FILE_COMP response format from captures:
# Session 1: filename = "\u555C" + "bullet_screen_video.avi"
# Session 2: filename = "\u555C" + "20260215_005855.avi" 
# Session 3: filename = "\u555C" + "20260216_184542.avi"

# AVI structure:
# Session 1 (15s video): 180 frames, 12fps, 368x368 MJPG, ~1MB
# Session 2 (4-image seq): 4 frames, 1fps, 368x368 MJPG, ~38KB
# Session 3 (3s video with audio): 36 frames, 12fps + audio (auds), 368x368 MJPG, ~375KB

print("=== PROTOCOL DIFFERENCES SUMMARY ===")
print()
print("Single-image vs Video/ImageSequence — SAME protocol, different content:")
print()
print("1. FILE_META body format (cmd 0x1b TX):")
print("   CURRENT: [seq, 0x00, 0x00, size_hi, size_lo, crc_hi, crc_lo, rand, rand, name..., 0x00]")
print("   ACTUAL:  [seq, size_b3, size_b2, size_b1, size_b0, crc_hi, crc_lo, rand, rand, name..., 0x00]")
print("   → body[1:5] is a 32-bit big-endian file size (not 16-bit at [3:5])")
print("   → Single-image worked because size < 65536, so body[1:3] happened to be 0x0000")
print()
print("2. File content:")
print("   Single image: raw JPEG (FFD8...FFD9)")
print("   Video:        RIFF/AVI with MJPG codec, 12fps")
print("   Image seq:    RIFF/AVI with MJPG codec, 1fps")
print("   Video+audio:  RIFF/AVI with MJPG + PCM audio streams")
print()
print("3. FILE_COMP response filename:")
print("   Single image: \\u555C + timestamp + .jpg")
print("   Video/seq:    \\u555C + timestamp + .avi")
print()
print("4. AVI building:")
print("   Videos: 12fps, 368x368, MJPG codec")
print("   Image sequences: 1fps, 368x368, MJPG codec")
print("   The iOS app creates the AVI container from frames/video")
print()
print("5. NO other protocol changes - same commands, same FD02 writes")
print()
print("=== IMPLEMENTATION PLAN ===")
print("1. Fix FILE_META to use 32-bit file size: body[1:5]")
print("2. Add AVI builder (MJPG) for multi-image sequences")
print("3. Add video → AVI converter (extract frames, re-encode as MJPG AVI)")
print("4. Update FILE_COMP response: .avi extension for non-single-image")
print("5. Update UI: allow multiple image selection, video file input")
