#!/usr/bin/env python3
"""Extract the full auth exchange from the pklg capture."""
import struct

def parse_pklg_records(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    # The format appears to be Apple PacketLogger (pklg)
    # Each record: uint32_be(len), uint64_be(timestamp), uint8(type), payload
    # But len includes everything after the 4-byte length field
    
    # Let's look at the structure around the auth area
    # 'pass' is at 0xdde7, so auth exchange should be before that
    
    # Try parsing from beginning
    records = []
    pos = 0
    while pos + 4 < len(data):
        rec_len = struct.unpack('>I', data[pos:pos+4])[0]
        if rec_len < 9 or rec_len > 5000 or pos + 4 + rec_len > len(data):
            # Try finding next valid record
            pos += 1
            continue
        
        rec_data = data[pos+4:pos+4+rec_len]
        ts = struct.unpack('>Q', rec_data[:8])[0]
        pkt_type = rec_data[8]
        payload = rec_data[9:]
        records.append((pos, rec_len, ts, pkt_type, payload))
        pos += 4 + rec_len
    
    print(f"Total records: {len(records)}")
    
    # Find records near the auth exchange (look for handle 0x0006 and 0x0008)
    # ATT Write = 0x52 (write command) or 0x12 (write request)
    # ATT Notification = 0x1B
    # The "pass" context showed: 52 06 00 02 70 61 73 73 (Write to handle 0x0006)
    # and: 1b 08 00 02 70 61 73 73 (Notify from handle 0x0008)
    
    # So AE01 write handle = 0x0006, AE02 notify handle = 0x0008
    
    print("\n=== Records with ATT writes to handle 0x0006 or notifications from 0x0008 ===")
    for i, (offset, length, ts, pkt_type, payload) in enumerate(records):
        if len(payload) < 4:
            continue
        
        # Look for L2CAP ATT channel (CID 0x0004)
        # HCI ACL format in pklg: handle(2) + acl_len(2) + l2cap_len(2) + l2cap_cid(2) + att_data
        # But pkt_type tells us direction: 0x00=cmd sent, 0x01=event recv, 0x02=sent ACL, 0x03=recv ACL
        
        # Find ATT opcode + handle patterns in payload
        for j in range(len(payload) - 3):
            # Write Command to handle 0x0006
            if payload[j] == 0x52 and payload[j+1] == 0x06 and payload[j+2] == 0x00:
                att_value = payload[j+3:]
                hex_val = ' '.join(f'{b:02x}' for b in att_value[:20])
                direction = "APP->DEV"
                print(f"  [{i:4d}] offset=0x{offset:05x} {direction} WriteCmd h=0x0006 ({len(att_value)}B): {hex_val}")
                break
            
            # Write Request to handle 0x0006
            if payload[j] == 0x12 and payload[j+1] == 0x06 and payload[j+2] == 0x00:
                att_value = payload[j+3:]
                hex_val = ' '.join(f'{b:02x}' for b in att_value[:20])
                direction = "APP->DEV"
                print(f"  [{i:4d}] offset=0x{offset:05x} {direction} WriteReq h=0x0006 ({len(att_value)}B): {hex_val}")
                break
            
            # Notification from handle 0x0008
            if payload[j] == 0x1B and payload[j+1] == 0x08 and payload[j+2] == 0x00:
                att_value = payload[j+3:]
                hex_val = ' '.join(f'{b:02x}' for b in att_value[:20])
                direction = "DEV->APP"
                print(f"  [{i:4d}] offset=0x{offset:05x} {direction} Notify  h=0x0008 ({len(att_value)}B): {hex_val}")
                break
            
            # Also check handles 0x0005, 0x0007, 0x0009 etc
            if payload[j] in (0x52, 0x12) and payload[j+2] == 0x00 and payload[j+1] in range(3, 0x20):
                att_handle = payload[j+1]
                att_value = payload[j+3:]
                if len(att_value) in (5, 17):
                    hex_val = ' '.join(f'{b:02x}' for b in att_value)
                    direction = "APP->DEV"
                    op = "WriteCmd" if payload[j] == 0x52 else "WriteReq"
                    print(f"  [{i:4d}] offset=0x{offset:05x} {direction} {op} h=0x{att_handle:04x} ({len(att_value)}B): {hex_val}")
                    break
            
            if payload[j] == 0x1B and payload[j+2] == 0x00 and payload[j+1] in range(3, 0x20):
                att_handle = payload[j+1]
                att_value = payload[j+3:]
                if len(att_value) in (5, 17):
                    hex_val = ' '.join(f'{b:02x}' for b in att_value)
                    direction = "DEV->APP"
                    print(f"  [{i:4d}] offset=0x{offset:05x} {direction} Notify  h=0x{att_handle:04x} ({len(att_value)}B): {hex_val}")
                    break

parse_pklg_records('cap.pklg')
