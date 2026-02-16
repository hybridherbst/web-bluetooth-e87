#!/usr/bin/env python3
"""Extract auth exchange from pklg capture - LE format."""
import struct

with open('cap.pklg', 'rb') as f:
    data = f.read()

# Apple PacketLogger (.pklg) format with LITTLE-ENDIAN fields:
# Each record:
#   uint32_le length (payload bytes that follow)
#   uint32_le timestamp_secs  
#   uint32_le timestamp_usecs (or combined as 8 bytes?)
#   uint8 type
#   payload[length - 9] (since length includes ts+type)
#
# Actually let me try: length field is the total size after the 4-byte length

records = []
pos = 0
while pos + 4 < len(data):
    rec_len = struct.unpack('<I', data[pos:pos+4])[0]
    if rec_len < 5 or rec_len > 50000 or pos + 4 + rec_len > len(data):
        print(f"Bad record at 0x{pos:x}, len={rec_len}")
        break
    rec_data = data[pos+4:pos+4+rec_len]
    # Parse: ts_secs(4LE), ts_usecs(4LE), type(1), payload
    if len(rec_data) >= 9:
        ts_s = struct.unpack('<I', rec_data[0:4])[0]
        ts_us = struct.unpack('<I', rec_data[4:8])[0]
        pkt_type = rec_data[8]
        payload = rec_data[9:]
        records.append((pos, rec_len, ts_s, ts_us, pkt_type, payload))
    pos += 4 + rec_len

print(f"Parsed {len(records)} records")

# Print first few records to understand types
for i, (offset, length, ts_s, ts_us, pkt_type, payload) in enumerate(records[:5]):
    hex_pay = ' '.join(f'{b:02x}' for b in payload[:20])
    print(f"  [{i}] off=0x{offset:x} type=0x{pkt_type:02x} len={len(payload)} ts={ts_s}.{ts_us}: {hex_pay}...")

# pkt_type: 0x00=HCI Cmd, 0x01=HCI Event, 0x02=Sent ACL, 0x03=Recv ACL
print(f"\n=== ATT operations on all handles (types 0x02/0x03) ===")
auth_exchanges = []

for i, (offset, length, ts_s, ts_us, pkt_type, payload) in enumerate(records):
    if pkt_type not in (0x02, 0x03):
        continue
    if len(payload) < 9:
        continue
    
    # HCI ACL: handle(2LE) + length(2LE)
    acl_handle = struct.unpack('<H', payload[0:2])[0] & 0x0FFF
    acl_len = struct.unpack('<H', payload[2:4])[0]
    
    # L2CAP: length(2LE) + CID(2LE)
    if len(payload) < 8:
        continue
    l2cap_len = struct.unpack('<H', payload[4:6])[0]
    l2cap_cid = struct.unpack('<H', payload[6:8])[0]
    
    if l2cap_cid != 0x0004:  # Not ATT
        continue
    
    att_data = payload[8:]
    if len(att_data) < 1:
        continue
    
    att_opcode = att_data[0]
    direction = "APP->DEV" if pkt_type == 0x02 else "DEV->APP"
    
    att_value = b''
    att_handle = 0
    op = ""
    
    if att_opcode == 0x52 and len(att_data) >= 3:  # Write Command
        att_handle = struct.unpack('<H', att_data[1:3])[0]
        att_value = att_data[3:]
        op = "WriteCmd"
    elif att_opcode == 0x12 and len(att_data) >= 3:  # Write Request
        att_handle = struct.unpack('<H', att_data[1:3])[0]
        att_value = att_data[3:]
        op = "WriteReq"
    elif att_opcode == 0x1B and len(att_data) >= 3:  # Notification
        att_handle = struct.unpack('<H', att_data[1:3])[0]
        att_value = att_data[3:]
        op = "Notify"
    elif att_opcode == 0x13:  # Write Response (no payload)
        continue
    else:
        continue
    
    vlen = len(att_value)
    hex_val = ' '.join(f'{b:02x}' for b in att_value[:30])
    
    # Print packets that could be auth (17 bytes or 5 bytes) or FE DC BA frames
    is_auth = vlen in (5, 17)
    is_fe = vlen >= 5 and att_value[0] == 0xFE and att_value[1] == 0xDC and att_value[2] == 0xBA
    
    if is_auth or is_fe:
        print(f"  [{i:4d}] {direction} {op:8s} h=0x{att_handle:04x} ({vlen:4d}B): {hex_val}{'...' if vlen > 30 else ''}")
        if is_auth:
            auth_exchanges.append((i, direction, op, att_handle, list(att_value)))

print(f"\n=== Auth-specific packets ({len(auth_exchanges)}) ===")
for idx, direction, op, handle, val in auth_exchanges:
    hex_val = ' '.join(f'{b:02x}' for b in val)
    if len(val) == 5:
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in val[1:])
        print(f"  [{idx:4d}] {direction} {op:8s} h=0x{handle:04x}: {hex_val}  (ascii='{ascii_str}')")
    else:
        type_str = {0: "RANDOM", 1: "ENCRYPTED"}.get(val[0], f"type=0x{val[0]:02x}")
        print(f"  [{idx:4d}] {direction} {op:8s} h=0x{handle:04x}: {hex_val}  ({type_str})")
