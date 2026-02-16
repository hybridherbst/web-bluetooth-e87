#!/usr/bin/env python3
"""Compare the EXACT bytes of the commit chunk frame we'd build vs what the capture has."""
import struct

img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()

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

# Build what our code would send for the commit chunk
# sendChunksAt(offset=0, winSize=490)
# payload = jpegBytes[0:490]
payload = img[0:490]
seq = 0x25  # seq=37 in capture (6+31=37=0x25)
slot = 0
crc = crc16_xmodem(payload)

body = bytes([seq, 0x1d, slot, (crc >> 8) & 0xff, crc & 0xff]) + payload
print(f"Commit chunk body: {len(body)} bytes")
print(f"  body[0] (seq)  = 0x{body[0]:02x}")
print(f"  body[1] (sub)  = 0x{body[1]:02x}")
print(f"  body[2] (slot) = 0x{body[2]:02x}")
print(f"  body[3:5] (crc)= 0x{(body[3]<<8)|body[4]:04x}")
print(f"  body[5:9]      = {body[5:9].hex()} (should be ffd8ffe0)")

# Build the FE frame
frame = bytes([0xFE, 0xDC, 0xBA, 0x80, 0x01]) + bytes([(len(body) >> 8) & 0xff, len(body) & 0xff]) + body + bytes([0xEF])
print(f"\nFull FE frame: {len(frame)} bytes")
print(f"  header: {frame[0:7].hex()}")
print(f"  body[0:5]: {frame[7:12].hex()}")
print(f"  payload[0:4]: {frame[12:16].hex()}")

# Now compare with capture
raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ptype = raw[off + 12]
    payload_r = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload_r})
    off += 4 + rec_len
    if off > len(raw):
        break

# Find the commit chunk (last TX data frame)
last_data = None
for r in records:
    if r['type'] != 2:
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd == 0x01 and flag == 0x80:
                cap_body = p[idx+7:idx+7+blen]
                last_data = (p[idx:idx+7], cap_body)
            break

if last_data:
    cap_header, cap_body = last_data
    print(f"\nCapture commit chunk:")
    print(f"  header: {cap_header.hex()}")
    print(f"  body[0] (seq)  = 0x{cap_body[0]:02x}")
    print(f"  body[1] (sub)  = 0x{cap_body[1]:02x}")
    print(f"  body[2] (slot) = 0x{cap_body[2]:02x}")
    print(f"  body[3:5] (crc)= 0x{(cap_body[3]<<8)|cap_body[4]:04x}")
    print(f"  body[5:9]      = {cap_body[5:9].hex()}")
    
    # Compare first 20 bytes
    our_first20 = body[:20]
    cap_first20 = cap_body[:min(20, len(cap_body))]
    print(f"\nOur body[0:20]: {our_first20.hex()}")
    print(f"Cap body[0:20]: {cap_first20.hex()}")
    print(f"Match: {our_first20 == cap_first20}")
    
    # CRC comparison
    print(f"\nOur CRC: 0x{crc:04x}")
    cap_crc = (cap_body[3] << 8) | cap_body[4]
    print(f"Cap CRC: 0x{cap_crc:04x}")
    print(f"CRC match: {crc == cap_crc}")

# Now check: in the capture, what's the FE frame for cmd 0x20 response?
print("\n\n=== CMD 0x20 RESPONSE ANALYSIS ===")
for r in records:
    if r['type'] != 2:
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd == 0x20 and flag == 0x00:
                body = p[idx+7:idx+7+blen]
                print(f"TX cmd 0x20 response:")
                print(f"  flag=0x{flag:02x} cmd=0x{cmd:02x} bodyLen={blen}")
                print(f"  body hex: {body.hex()}")
                print(f"  body[0] (status) = 0x{body[0]:02x}")
                print(f"  body[1] (seq echo) = 0x{body[1]:02x}")
                if len(body) > 2:
                    path_bytes = body[2:]
                    try:
                        path_str = path_bytes.decode('utf-16-le').rstrip('\x00')
                        print(f"  path: '{path_str}'")
                        print(f"  path first char code: U+{ord(path_str[0]):04X}")
                    except:
                        print(f"  path bytes: {path_bytes.hex()}")
                    # Check: does the path start with 0x5C or 0x555C?
                    print(f"  path[0:2] hex: {path_bytes[0:2].hex()}")
                    print(f"  path[0:4] hex: {path_bytes[0:4].hex()}")
            break

# Also check the cmd 0x1c exchange
print("\n=== CMD 0x1c ANALYSIS ===")
for r in records:
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd == 0x1c:
                body = p[idx+7:idx+7+blen]
                direction = 'TX' if r['type'] == 2 else 'RX'
                print(f"{direction} cmd 0x1c: flag=0x{flag:02x} body={body.hex()}")
            break
