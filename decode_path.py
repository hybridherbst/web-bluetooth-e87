#!/usr/bin/env python3
"""Decode the cmd 0x20 response path from the capture."""

# This is the body of the cmd 0x20 response (FE 32, TX)
body = bytes([
    0x00, 0x06,   # status=0x00, seq=0x06
    0x5c, 0x55, 0x32, 0x00,   # path starts here
    0x30, 0x00, 0x32, 0x00, 0x36, 0x00,
    0x30, 0x00, 0x32, 0x00, 0x31, 0x00,
    0x35, 0x00, 0x30, 0x00, 0x30, 0x00,
    0x34, 0x00, 0x35, 0x00, 0x33, 0x00,
    0x30, 0x00, 0x2e, 0x00, 0x6a, 0x00,
    0x70, 0x00, 0x67, 0x00, 0x00, 0x00
])

path_data = body[2:]

print(f"Path data length: {len(path_data)} bytes")
print(f"Path data hex: {' '.join(f'{b:02x}' for b in path_data)}")
print()

# Interpretation 1: Full UTF-16LE
try:
    as_utf16 = path_data.decode('utf-16-le')
    print(f"As UTF-16LE: {repr(as_utf16)}")
    print(f"  Characters: {[hex(ord(c)) for c in as_utf16]}")
except:
    print("UTF-16LE decode failed")

print()

# Interpretation 2: Mixed - first 2 bytes are ASCII \U, rest is UTF-16LE  
first_two_ascii = chr(path_data[0]) + chr(path_data[1])  # \U
rest_utf16 = path_data[2:].decode('utf-16-le')
print(f"As mixed (2 ASCII + UTF-16LE): '{first_two_ascii}{rest_utf16}'")
print(f"  => '{first_two_ascii}' + '{rest_utf16}'")

print()

# The capture path decoded: \U20260215004530.jpg
# Our code generates: \U32\0YYYYMMDDHHMMSS.jpg
# Wait - let me look more carefully at the capture path

# In the capture: 5c 55 32 00 30 00 32 00 36 00 ...
# If UTF-16LE: 0x555c (啜) 0x0032 (2) 0x0030 (0) 0x0032 (2) 0x0036 (6) ...
# The device path would be: 啜20260215004530.jpg
# That seems wrong.

# BUT: What if it's actually: 
# byte 0x5c = '\' (ASCII)
# Then UTF-16LE starting from offset 1:
# 55 32 = char 0x3255 (㉕) 
# That's also wrong.

# Alternative: The path is \U32\020260215004530.jpg with \0 as null terminators
# And the encoding is NOT UTF-16LE but rather a mix?

# Actually let me look at it as bytes representing the path \U32\020260215004530.jpg
# \  = 5c
# U  = 55
# 3  = 33
# 2  = 32
# But the capture has 5c 55 32 00 - which has a 0x00 after the '2'
# This matches UTF-16LE for '\U2' where \ and U are merged into a single 16-bit char

# I think the Android app uses a path like "\U2" + "0260215004530" + ".jpg"
# Where the full path is: \U20260215004530.jpg  
# That's \U + 20260215004530.jpg = \U + YYYYMMDDHHMMSS where YY=2026, MM=02, etc.

# And encoding is UTF-16LE where \U are two ASCII bytes that form one UTF-16 code point
# No wait... let me think again.

# Actually the simplest reading:
# The first TWO bytes (5c 55) form a single UTF-16LE character U+555C
# Then bytes 32 00 form '2', 30 00 form '0', etc.
# So the path as UTF-16LE has 20 chars = 40 bytes
# First char is U+555C, then "20260215004530.jpg" + null

# But the INTENDED path is clearly "\U" followed by a timestamp
# The Android app probably builds it as: "\\U" + datestr + ".jpg" and encodes UTF-16LE
# But "\" is U+005C and "U" is U+0055
# In UTF-16LE: 5c 00 55 00 - but capture shows 5c 55
# So either the capture is wrong or the Android app encodes differently

# WAIT - maybe the capture path does NOT start with \U at all
# Maybe the path bytes are just: first char 0x555C (an actual CJK char)
# Jieli firmware is Chinese, so \U might just be a CJK path marker

# Let me check: what does our code produce?
# devicePath = `\\U32\\0${dateStr}.jpg`
# For date "20260215125341":
# \\U32\\020260215125341.jpg
# In UTF-16LE that would be:
# 5c 00 55 00 33 00 32 00 5c 00 30 00 32 00 ...
# That's DIFFERENT from the capture which has: 5c 55 32 00 30 00 32 00 ...

# So the issue is clear: 
# Capture path starts with bytes: 5c 55 = one UTF-16LE char (U+555C)
# Our code produces: 5c 00 55 00 = TWO UTF-16LE chars (\, U)

# CONCLUSION: The device path in capture is NOT "\\U32\\0..." 
# It's a single character U+555C followed by "20260215004530.jpg"
# The path format from capture is: [U+555C]20260215004530.jpg
# That's 1 char prefix + 14 digit timestamp + .jpg + null = 20 chars = 40 bytes ✓

print("="*60)
print("CONCLUSION:")
print(f"  Path format: one char prefix (U+555C) + YYYYMMDDHHMMSS + .jpg + null")
print(f"  Capture path: {repr(path_data.decode('utf-16-le'))}")
print(f"  Body total: 2 (status+seq) + 40 (path UTF-16LE) = 42 bytes")
print()

# NOW: what does our code produce?
# `\\U32\\0${dateStr}.jpg` = \U32\020260215125341.jpg 
# UTF-16LE: 5c 00 55 00 33 00 32 00 5c 00 30 00 ...  (much longer!)
# That's 24 chars * 2 + 2 null = 50 bytes for path alone

# Fix: The path should be chr(0x555c) + dateStr + ".jpg"
# Where dateStr is JUST the 14-digit timestamp (no separators)
