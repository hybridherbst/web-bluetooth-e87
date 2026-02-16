#!/usr/bin/env python3
"""Check the BLE MTU from the capture. The iOS app negotiated a specific MTU."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload, 'rec_len': rec_len})
    off += 4 + rec_len
    if off > len(raw):
        break

# Find MTU Exchange request/response (ATT opcode 0x02/0x03)
print("=== MTU EXCHANGE ===")
for r in records:
    p = r['payload']
    if len(p) > 8:
        # HCI ACL header: handle(2), len(2), L2CAP: len(2), cid(2), ATT data
        att_start = 8
        if att_start < len(p):
            att_op = p[att_start]
            if att_op == 0x02:  # MTU Request
                mtu = p[att_start+1] | (p[att_start+2] << 8)
                print(f"  MTU Request: {mtu}")
            elif att_op == 0x03:  # MTU Response
                mtu = p[att_start+1] | (p[att_start+2] << 8)
                print(f"  MTU Response: {mtu}")

# Find the largest ATT Write Without Response (opcode 0x52)
print("\n=== LARGEST ATT WRITES ===")
max_att_len = 0
for r in records:
    p = r['payload']
    if len(p) > 8 and r['type'] == 2:
        att_start = 8
        if att_start < len(p) and p[att_start] == 0x52:  # Write Without Response
            # L2CAP length tells us the real ATT payload size
            l2cap_len = p[4] | (p[5] << 8)
            att_value_len = l2cap_len - 3  # subtract opcode(1) + handle(2)
            if att_value_len > max_att_len:
                max_att_len = att_value_len
                att_handle = p[att_start+1] | (p[att_start+2] << 8)
                print(f"  Max so far: {att_value_len} bytes to handle 0x{att_handle:04x} (L2CAP len={l2cap_len})")

print(f"\n  Largest ATT Write value: {max_att_len} bytes")
print(f"  FE frame for 490B payload: 503 bytes")
print(f"  Minimum MTU needed: 503 + 3 = 506 bytes (ATT value + ATT header)")
print(f"  With HCI overhead: write opcode(1) + handle(2) + value(503) = 506 ATT PDU")
