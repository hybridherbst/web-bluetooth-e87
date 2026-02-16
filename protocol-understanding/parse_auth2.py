#!/usr/bin/env python3
"""Extract auth exchange from pklg capture with proper record parsing."""
import struct

with open('cap.pklg', 'rb') as f:
    data = f.read()

# Parse ALL records properly
records = []
pos = 0
while pos + 4 < len(data):
    rec_len = struct.unpack('>I', data[pos:pos+4])[0]
    if rec_len < 9 or rec_len > 5000 or pos + 4 + rec_len > len(data):
        break
    rec_data = data[pos+4:pos+4+rec_len]
    ts = struct.unpack('>Q', rec_data[:8])[0]
    pkt_type = rec_data[8]
    payload = rec_data[9:]
    records.append((pos, rec_len, ts, pkt_type, payload))
    pos += 4 + rec_len

print(f"Parsed {len(records)} records")

# pkt_type in Apple PacketLogger:
# 0x00 = HCI Command (host->controller)
# 0x01 = HCI Event (controller->host)
# 0x02 = Sent ACL Data (host->controller)
# 0x03 = Received ACL Data (controller->host)

# For ACL data (types 0x02 and 0x03):
# Payload = HCI ACL header(4) + L2CAP header(4) + ATT data
# HCI ACL: handle(2LE) + length(2LE)
# L2CAP: length(2LE) + CID(2LE)
# ATT: opcode(1) + handle(2LE) + value(N)

print("\n=== All ATT Write/Notify records (pkt_type 0x02 or 0x03) ===")
auth_exchanges = []

for i, (offset, length, ts, pkt_type, payload) in enumerate(records):
    if pkt_type not in (0x02, 0x03):
        continue
    if len(payload) < 9:
        continue
    
    # Parse HCI ACL header
    acl_handle = struct.unpack('<H', payload[0:2])[0] & 0x0FFF
    acl_len = struct.unpack('<H', payload[2:4])[0]
    
    # Parse L2CAP header
    l2cap_len = struct.unpack('<H', payload[4:6])[0]
    l2cap_cid = struct.unpack('<H', payload[6:8])[0]
    
    if l2cap_cid != 0x0004:  # Not ATT
        continue
    
    att_data = payload[8:]
    if len(att_data) < 1:
        continue
    
    att_opcode = att_data[0]
    direction = "APP->DEV" if pkt_type == 0x02 else "DEV->APP"
    
    if att_opcode == 0x52 and len(att_data) >= 3:  # Write Command
        att_handle = struct.unpack('<H', att_data[1:3])[0]
        att_value = att_data[3:]
        hex_val = ' '.join(f'{b:02x}' for b in att_value)
        op = "WriteCmd"
        # Print ALL writes to handles in range 0x0003-0x000F
        if att_handle <= 0x0020:
            print(f"  [{i:4d}] {direction} {op} h=0x{att_handle:04x} ({len(att_value):3d}B): {hex_val[:80]}{'...' if len(hex_val) > 80 else ''}")
            if len(att_value) in (5, 17):
                auth_exchanges.append((i, direction, att_handle, list(att_value)))
    
    elif att_opcode == 0x12 and len(att_data) >= 3:  # Write Request
        att_handle = struct.unpack('<H', att_data[1:3])[0]
        att_value = att_data[3:]
        hex_val = ' '.join(f'{b:02x}' for b in att_value)
        op = "WriteReq"
        if att_handle <= 0x0020:
            print(f"  [{i:4d}] {direction} {op} h=0x{att_handle:04x} ({len(att_value):3d}B): {hex_val[:80]}{'...' if len(hex_val) > 80 else ''}")
            if len(att_value) in (5, 17):
                auth_exchanges.append((i, direction, att_handle, list(att_value)))
    
    elif att_opcode == 0x1B and len(att_data) >= 3:  # Notification
        att_handle = struct.unpack('<H', att_data[1:3])[0]
        att_value = att_data[3:]
        hex_val = ' '.join(f'{b:02x}' for b in att_value)
        op = "Notify"
        if att_handle <= 0x0020:
            print(f"  [{i:4d}] {direction} {op}   h=0x{att_handle:04x} ({len(att_value):3d}B): {hex_val[:80]}{'...' if len(hex_val) > 80 else ''}")
            if len(att_value) in (5, 17):
                auth_exchanges.append((i, direction, att_handle, list(att_value)))

print(f"\n=== Auth-sized packets (5 or 17 bytes): {len(auth_exchanges)} ===")
for idx, direction, handle, val in auth_exchanges:
    hex_val = ' '.join(f'{b:02x}' for b in val)
    if len(val) == 5:
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in val[1:])
        print(f"  [{idx}] {direction} h=0x{handle:04x}: {hex_val}  ascii='{ascii_str}'")
    else:
        type_str = {0: "RANDOM", 1: "ENCRYPTED"}.get(val[0], f"type={val[0]}")
        print(f"  [{idx}] {direction} h=0x{handle:04x}: {hex_val}  ({type_str})")
