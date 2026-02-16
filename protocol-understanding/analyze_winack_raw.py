#!/usr/bin/env python3
"""Check if WIN_ACK frames arrive as standalone BLE notifications or concatenated with other data."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
rec_idx = 0
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_secs = struct.unpack_from('<I', raw, off+4)[0]
    ts_usecs = struct.unpack_from('<I', raw, off+8)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': rec_idx, 'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6})
    rec_idx += 1
    off += 4 + rec_len
    if off > len(raw): break

# Find the 0x1b TX, its ack, and the first WIN_ACK
# Show the RAW HCI/L2CAP/ATT payload for each
print("=== Looking for 0x1b ack and WIN_ACK in RX records ===")

# Find the 0x1b TX first
found_1b_tx = False
for r in records:
    if r['type'] not in (2, 3): continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            cmd = p[idx+4]
            if cmd == 0x1b and r['type'] == 2:
                found_1b_tx = True
                print(f"\nRec#{r['idx']} TX cmd=0x1b:")
                print(f"  Full payload ({len(p)} bytes): {p.hex()}")
            elif found_1b_tx and r['type'] == 3:
                flag = p[idx+3]
                blen = (p[idx+5] << 8) | p[idx+6]
                body = p[idx+7:idx+7+blen]
                print(f"\nRec#{r['idx']} RX flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen}:")
                print(f"  Full payload ({len(p)} bytes): {p.hex()}")
                print(f"  FE frame starts at offset {idx} in payload")
                print(f"  Body: {body.hex()}")
                
                # Check if there's more FE data after this frame
                frame_end = idx + 7 + blen + 1  # +1 for 0xEF trailer
                if frame_end < len(p):
                    remaining = p[frame_end:]
                    print(f"  *** REMAINING after frame ({len(remaining)} bytes): {remaining.hex()}")
                
                if cmd == 0x1c or cmd == 0x20:
                    break  # Stop after completion
            break

# Now show ALL RX records between 0x1b ack and first data TX
# to see if WIN_ACK comes as separate notification
print("\n\n=== ALL RX records (type=3) around the 0x1b area ===")
# Find record index of 0x1b TX
start_rec = None
for r in records:
    if r['type'] != 2: continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA and p[idx+4] == 0x1b:
            start_rec = r['idx']
            break
    if start_rec: break

if start_rec:
    for r in records[start_rec:start_rec+20]:
        direction = 'TX' if r['type'] == 2 else 'RX' if r['type'] == 3 else f"t{r['type']}"
        p = r['payload']
        # Check for FE frame
        fe_info = ''
        for idx in range(len(p) - 3):
            if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
                flag = p[idx+3]
                cmd = p[idx+4]
                blen = (p[idx+5] << 8) | p[idx+6]
                fe_info = f' FE: flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen}'
                break
        
        # Show HCI header info
        if len(p) >= 5:
            # HCI ACL: handle(2) + len(2), then L2CAP: len(2) + cid(2), then ATT
            hci_len = (p[3] << 8) | p[2] if len(p) >= 4 else 0
            l2cap_len = (p[5] << 8) | p[4] if len(p) >= 6 else 0
            l2cap_cid = (p[7] << 8) | p[6] if len(p) >= 8 else 0
            att_op = p[8] if len(p) >= 9 else 0
            att_handle = ((p[10] << 8) | p[9]) if len(p) >= 11 else 0
            print(f"  Rec#{r['idx']:4d} {direction} len={len(p):4d} HCI_len={hci_len} L2CAP_len={l2cap_len} CID=0x{l2cap_cid:04x} ATT_op=0x{att_op:02x} handle=0x{att_handle:04x}{fe_info}")
            if fe_info:
                # Show the ATT value data (after op+handle = 3 bytes of ATT header)
                att_value = p[11:] if len(p) > 11 else b''
                print(f"         ATT value ({len(att_value)} bytes): {att_value[:40].hex()}")
