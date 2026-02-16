#!/usr/bin/env python3
"""Parse btsnoop capture to find auth exchange data."""
import struct

def parse_btsnoop(path):
    with open(path, 'rb') as f:
        # Header: 'btsnoop\0' + version(4) + type(4)
        hdr = f.read(16)
        print(f"Header: {hdr[:8]}, version={struct.unpack('>I', hdr[8:12])[0]}, type={struct.unpack('>I', hdr[12:16])[0]}")
        
        records = []
        while True:
            rec_hdr = f.read(24)
            if len(rec_hdr) < 24:
                break
            orig_len, inc_len, flags, drops = struct.unpack('>IIII', rec_hdr[:16])
            ts = struct.unpack('>Q', rec_hdr[16:24])[0]
            data = f.read(inc_len)
            if len(data) < inc_len:
                break
            records.append((orig_len, inc_len, flags, drops, ts, data))
        
        print(f"Total records: {len(records)}")
        
        # Look for ATT writes/notifications
        # HCI ACL data starts with handle(2) + length(2) + L2CAP(4) + ATT opcode
        # ATT opcodes: 0x12 = Write Request, 0x52 = Write Command, 0x1B = Notification
        auth_packets = []
        for i, (orig_len, inc_len, flags, drops, ts, data) in enumerate(records):
            if len(data) < 9:
                continue
            # HCI packet indicator + ACL
            if data[0] == 0x02:  # HCI ACL
                acl_handle = struct.unpack('<H', data[1:3])[0] & 0x0FFF
                acl_len = struct.unpack('<H', data[3:5])[0]
                if len(data) < 5 + acl_len:
                    continue
                l2cap_len = struct.unpack('<H', data[5:7])[0]
                l2cap_cid = struct.unpack('<H', data[7:9])[0]
                if l2cap_cid == 0x0004:  # ATT
                    att_opcode = data[9]
                    att_payload = data[9:]
                    att_handle = 0
                    att_value = b''
                    if att_opcode in (0x12, 0x52) and len(att_payload) >= 4:  # Write Req/Cmd
                        att_handle = struct.unpack('<H', att_payload[1:3])[0]
                        att_value = att_payload[3:]
                    elif att_opcode == 0x1B and len(att_payload) >= 4:  # Notification
                        att_handle = struct.unpack('<H', att_payload[1:3])[0]
                        att_value = att_payload[3:]
                    
                    # Look for auth data: 17 bytes with first byte 0x00 or 0x01, or 5 bytes "pass"
                    vlen = len(att_value)
                    if vlen in (5, 17):
                        direction = "SEND" if (flags & 1) == 0 else "RECV"
                        op_name = {0x12: "WriteReq", 0x52: "WriteCmd", 0x1B: "Notify"}.get(att_opcode, f"0x{att_opcode:02x}")
                        hex_val = ' '.join(f'{b:02x}' for b in att_value)
                        print(f"  [{i:4d}] {direction} {op_name} handle=0x{att_handle:04x} ({vlen}B): {hex_val}")
                        if vlen == 17 and att_value[0] in (0, 1):
                            auth_packets.append((i, direction, op_name, att_handle, list(att_value)))
                        elif vlen == 5 and att_value[0] == 2:
                            auth_packets.append((i, direction, op_name, att_handle, list(att_value)))
        
        print(f"\n=== Auth packets found: {len(auth_packets)} ===")
        for idx, direction, op, handle, val in auth_packets:
            hex_val = ' '.join(f'{b:02x}' for b in val)
            if len(val) == 5:
                ascii_val = ''.join(chr(b) if 32 <= b < 127 else '.' for b in val[1:])
                print(f"  [{idx}] {direction} {op} h=0x{handle:04x}: {hex_val}  ('{ascii_val}')")
            else:
                type_name = {0: "random", 1: "encrypted"}.get(val[0], "?")
                print(f"  [{idx}] {direction} {op} h=0x{handle:04x}: {hex_val}  (type={type_name})")
        
        return auth_packets

if __name__ == '__main__':
    print("=== Parsing cap.btsnoop ===")
    pkts = parse_btsnoop('cap.btsnoop')
    
    # If we found challenge + response, we can verify crypto
    if len(pkts) >= 2:
        print("\n=== Crypto verification data ===")
        for p in pkts:
            print(f"  Record {p[0]}: {p[1]} type={p[4][0]} data={' '.join(f'{b:02x}' for b in p[4])}")
