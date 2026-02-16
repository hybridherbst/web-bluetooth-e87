#!/usr/bin/env python3
"""Verify that body[3:5] is CRC-16 of the 490-byte payload."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'payload': payload, 'type': ptype})
    off += 4 + rec_len
    if off > len(raw):
        break

# Reconstruct the FULL body of the first data frame (seq=0x06)
# It spans records 1614 (first fragment), 1615 (continuation), 1616 (continuation)
def reconstruct_att_data(start_rec_idx):
    """Reconstruct ATT data from fragmented L2CAP."""
    att_data = bytearray()
    rec = records[start_rec_idx]
    p = rec['payload']
    # First fragment: ACL(4) + L2CAP(4) + ATT_opcode(1) + ATT_handle(2) + data
    att_data.extend(p[11:])  # Skip ACL(4) + L2CAP(4) + ATT(3)
    
    for r_idx in range(start_rec_idx + 1, start_rec_idx + 10):
        if r_idx >= len(records):
            break
        rec = records[r_idx]
        if rec['type'] != 0x02:  # Only outgoing ACL
            continue
        p = rec['payload']
        if len(p) < 4:
            continue
        acl_flags = (struct.unpack_from('<H', p, 0)[0] >> 12) & 0xF
        if acl_flags == 0x1:  # continuation
            att_data.extend(p[4:])
        elif acl_flags == 0x0:  # new L2CAP PDU = next frame
            break
    
    return bytes(att_data)

# Get the full ATT data for first frame (rec 1614)
att_data = reconstruct_att_data(1614)
print(f"Reconstructed ATT data: {len(att_data)} bytes")
print(f"Expected: FE(7) + body(495) + EF(1) = 503")

# Parse the body
fe_header = att_data[:7]
body = att_data[7:-1]  # exclude EF
ef = att_data[-1]
print(f"FE header: {' '.join(f'{b:02x}' for b in fe_header)}")
print(f"Body length: {len(body)}")
print(f"EF terminator: 0x{ef:02x}")

# body[0] = seq, body[1] = 0x1D, body[2] = slot
# body[3:5] = mystery (CRC?)
# body[5:] = data (490 bytes)
seq_b = body[0]
subcmd = body[1]
slot = body[2]
mystery = body[3:5]
data_payload = body[5:]
print(f"seq=0x{seq_b:02x} subcmd=0x{subcmd:02x} slot={slot}")
print(f"mystery bytes: {mystery[0]:02x} {mystery[1]:02x}")
print(f"data payload: {len(data_payload)} bytes")
print(f"First 20 data bytes: {' '.join(f'{b:02x}' for b in data_payload[:20])}")

# Try various CRC-16 algorithms
def crc16_ccitt(data, init=0xFFFF):
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc

def crc16_ccitt_false(data):
    return crc16_ccitt(data, 0xFFFF)

def crc16_xmodem(data):
    return crc16_ccitt(data, 0x0000)

def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def crc16_ibm(data):
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def crc16_aug_ccitt(data):
    return crc16_ccitt(data, 0x1D0F)

mystery_be = (mystery[0] << 8) | mystery[1]
mystery_le = (mystery[1] << 8) | mystery[0]

# Try CRC on just the 490-byte data
print(f"\nCRC-16 of 490-byte payload (body[5:]):")
d = bytes(data_payload)
print(f"  CCITT-FALSE: 0x{crc16_ccitt_false(d):04x} (target BE=0x{mystery_be:04x} LE=0x{mystery_le:04x})")
print(f"  XMODEM:      0x{crc16_xmodem(d):04x}")
print(f"  Modbus:      0x{crc16_modbus(d):04x}")
print(f"  IBM:         0x{crc16_ibm(d):04x}")
print(f"  AUG-CCITT:   0x{crc16_aug_ccitt(d):04x}")

# Try CRC on body[5:] (data) with body[:3] included
combined = bytes(body[:3]) + bytes(data_payload)
print(f"\nCRC-16 of [seq,subcmd,slot]+data ({len(combined)} bytes):")
print(f"  CCITT-FALSE: 0x{crc16_ccitt_false(combined):04x}")
print(f"  XMODEM:      0x{crc16_xmodem(combined):04x}")
print(f"  Modbus:      0x{crc16_modbus(combined):04x}")

# Try CRC on full body minus mystery
rest = bytes(body[:3]) + bytes(body[5:])
print(f"\nCRC-16 of [header+data] minus mystery ({len(rest)} bytes):")
print(f"  CCITT-FALSE: 0x{crc16_ccitt_false(rest):04x}")
print(f"  XMODEM:      0x{crc16_xmodem(rest):04x}")

# Maybe the mystery bytes are NOT a CRC but just part of the file data
# In that case, payload per frame = 492 (body[3:495])
# Let me check: could body[3:] be ALL file data (492 bytes)?
# Then: 31*492 + (462-3) = 15711
# File size as BE16 = 0x3D1F = 15647 → 15711 ≠ 15647
# As LE16 = 0x1F3D = 7997 → 15711 ≠ 7997

# File size alternatives:
# Maybe it's 32-bit? body[3:7] = 3D 1F 66 AB
# LE32: 0xAB661F3D = 2875596605 (too big)
# BE32: 0x3D1F66AB = 1025468075 (too big)
# body[1:5] = 00 00 3D 1F
# LE32: 0x1F3D0000 (too big)
# BE32: 0x00003D1F = 15647 (same as BE16)

# So file size is definitely 15647 (BE16)
# 31 full frames × 490 + 1 short frame × 457 = 15647 ← matches
# This means overhead per frame is 5 bytes

# Maybe body[3:5] ISN'T a CRC. Maybe it's just data!
# Let me try: overhead = 3 bytes (seq, 0x1D, slot), data = 492
# Then we need: total data = sum of all frame payloads
# 31 * 492 + (462-3) = 15252 + 459 = 15711
# But file size = 15647, difference = 64
# Hmm, that's suspicious — maybe the LAST full frame (seq=0x25) has 492-64=428 payload?
# But body_len=495 for seq=0x25...

# OR: maybe the file size doesn't include the very first 2 bytes of each window (the mystery bytes)
# 32 windows × 2 = 64
# 15711 - 64 = 15647! YES!!!

print(f"\n\n{'='*60}")
print("EUREKA!")
print(f"{'='*60}")
print(f"15711 (total with 492/frame) - 64 (32 frames × 2 mystery bytes) = {15711-64}")
print(f"File size (BE16) = 15647")
print(f"Match: {15711-64 == 15647}")
print(f"")
print(f"This means: body[3:5] IS part of the overhead, NOT file data")
print(f"Each frame: body = [seq(1), 0x1D(1), slot(1), checksum(2), filedata(490)]")
print(f"E87_DATA_CHUNK_SIZE should be 490")
