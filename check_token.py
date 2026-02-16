#!/usr/bin/env python3
"""Check what the 4-byte 'token' field really is."""

def crc16x(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc

img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()
whole_crc = crc16x(img)
print(f"Whole-file CRC-16 XMODEM = 0x{whole_crc:04x}")
print(f"As bytes (BE): 0x{(whole_crc >> 8) & 0xff:02x} 0x{whole_crc & 0xff:02x}")
print()

# Capture token field: 66 ab 66 66
token = bytes.fromhex('66ab6666')
print(f"Capture token: {token.hex()}")
print(f"  token[0:2] = 0x{(token[0] << 8) | token[1]:04x} = file CRC? {'YES!' if (token[0] << 8) | token[1] == whole_crc else 'no'}")
print(f"  token[2:4] = 0x{(token[2] << 8) | token[3]:04x}")
print()

# The format is likely:
# body[5:7] = CRC-16 XMODEM of entire file (big-endian)
# body[7:9] = random 2 bytes (or another field)
print("Conclusion: body[5:7] = whole-file CRC-16 XMODEM (BE)")
print("            body[7:9] = random padding (0x6666 in capture)")
