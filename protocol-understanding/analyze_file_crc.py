#!/usr/bin/env python3
"""
Analyze the FILE_META (cmd 0x1b) body from the capture to find
the whole-file CRC-16 XMODEM field.
"""
import struct

# CRC-16 XMODEM
def crc16_xmodem(data):
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

# Parse PKLG and find cmd 0x1b TX
raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_secs = struct.unpack_from('<I', raw, off+4)[0]
    ts_usecs = struct.unpack_from('<I', raw, off+8)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6})
    off += 4 + rec_len

for r in records:
    p = r['payload']
    direction = 'TX' if r['type'] == 2 else 'RX'
    for i in range(len(p) - 10):
        if p[i:i+3] == b'\xfe\xdc\xba':
            flag = p[i+3]
            cmd = p[i+4]
            blen = (p[i+5] << 8) | p[i+6]
            body = p[i+7:i+7+blen]
            
            if cmd == 0x1b:
                print(f"{direction} cmd=0x1b flag=0x{flag:02x} bodyLen={blen}")
                print(f"  full body hex: {body.hex()}")
                print(f"  body bytes: {[f'0x{b:02x}' for b in body]}")
                print()
                
                if direction == 'TX':
                    # Parse the body structure
                    seq = body[0]
                    print(f"  [0] seq = {seq}")
                    print(f"  [1] = 0x{body[1]:02x}")
                    print(f"  [2] = 0x{body[2]:02x}")
                    
                    # File size at bytes 3-4 (BE16)
                    fsize = (body[3] << 8) | body[4]
                    print(f"  [3:5] file_size = {fsize} (0x{fsize:04x})")
                    
                    # Token at bytes 5-8
                    token = body[5:9]
                    print(f"  [5:9] token = {token.hex()}")
                    
                    # Name starts at byte 9
                    name_end = body.index(0x00, 9) if 0x00 in body[9:] else len(body)
                    name = body[9:name_end]
                    print(f"  [9:] name = {name.decode('ascii', errors='replace')}")
                    print(f"  remaining after name: {body[name_end:].hex()}")
                    
                    # Now let's check if any field could be a CRC-16
                    # Compute CRC-16 XMODEM of the whole image file
                    img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()
                    whole_crc = crc16_xmodem(img)
                    print(f"\n  Whole-file CRC-16 XMODEM = 0x{whole_crc:04x} ({whole_crc})")
                    print(f"  File size = {len(img)} bytes")
                    
                    # Check if the CRC appears anywhere in the body
                    crc_hi = (whole_crc >> 8) & 0xff
                    crc_lo = whole_crc & 0xff
                    print(f"  CRC bytes: 0x{crc_hi:02x} 0x{crc_lo:02x}")
                    
                    for j in range(len(body)-1):
                        if body[j] == crc_hi and body[j+1] == crc_lo:
                            print(f"  *** CRC found at body offset {j}-{j+1} (BE) ***")
                        if body[j] == crc_lo and body[j+1] == crc_hi:
                            print(f"  *** CRC found at body offset {j}-{j+1} (LE) ***")
                    
                    # Also check token bytes for CRC
                    token_as_16 = (token[0] << 8) | token[1]
                    token_as_16_2 = (token[2] << 8) | token[3]
                    print(f"\n  token[0:2] as BE16 = 0x{token_as_16:04x}")
                    print(f"  token[2:4] as BE16 = 0x{token_as_16_2:04x}")
                    
                    # What about bytes 1-2?
                    b12 = (body[1] << 8) | body[2]
                    print(f"  body[1:3] as BE16 = 0x{b12:04x}")
                    
                    # Let's also try different CRC positions for a longer body format
                    # The Jieli SDK suggests: file_version(8) + file_size(4) + crc(2) = 14 bytes
                    # But our body is structured differently (seq + flags + size + token + name)
                    print(f"\n  Body length: {len(body)} bytes")
                    
            break

print("\n" + "=" * 60)
print("ALTERNATIVE BODY PARSING (Jieli SDK format):")
print("=" * 60)
print("SDK struct file_parameter_t:")
print("  file_version[8] (8 bytes)")
print("  file_size (4 bytes, LE)")
print("  crc (2 bytes, LE)")
print("Total: 14 bytes")
print()
print("But our capture body is 20 bytes with seq, flags, etc.")
print("Let's see if there's a sub-structure after the seq byte...")
