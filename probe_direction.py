#!/usr/bin/env python3
"""Check actual payload size per data frame and direction via ACL handle."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'off': off + 13, 'len': rec_len - 9, 'type': ptype, 'payload': payload, 'ts': ts})
    off += 4 + rec_len
    if off > len(raw):
        break

# For type=0x02 records (ACL data), the first 4 bytes are ACL header:
# bytes 0-1: handle + flags (LE16), bytes 2-3: length (LE16)
# After that: L2CAP header (4 bytes): length(LE16) + CID(LE16)
# After that: ATT data

# Look at the first data frame record and the record before it
# to understand direction
rec_idx = 1614
print(f"Record {rec_idx} (first data frame start):")
p = records[rec_idx]['payload']
print(f"  type=0x{records[rec_idx]['type']:02x} len={len(p)}")
print(f"  first 30 bytes: {' '.join(f'{b:02x}' for b in p[:30])}")

# ACL header
acl_hdr = struct.unpack_from('<H', p, 0)[0]
acl_handle = acl_hdr & 0x0FFF
acl_flags = (acl_hdr >> 12) & 0x0F
acl_len = struct.unpack_from('<H', p, 2)[0]
print(f"  ACL: handle=0x{acl_handle:03x} flags=0x{acl_flags:x} len={acl_len}")

# Check what 'flags' means:
# 0x0 = first fragment, host to controller (OUTGOING)
# 0x1 = continuing fragment
# 0x2 = first fragment, controller to host (INCOMING)

if len(p) > 7:
    l2cap_len = struct.unpack_from('<H', p, 4)[0]
    l2cap_cid = struct.unpack_from('<H', p, 6)[0]
    print(f"  L2CAP: len={l2cap_len} CID=0x{l2cap_cid:04x}")
    
    if len(p) > 8:
        att_opcode = p[8]
        print(f"  ATT opcode: 0x{att_opcode:02x}")
        if att_opcode == 0x52:  # Write Without Response
            att_handle = struct.unpack_from('<H', p, 9)[0]
            print(f"  ATT Write Without Response, handle=0x{att_handle:04x}")
            print(f"  ATT data starts at p[11]: {' '.join(f'{b:02x}' for b in p[11:30])}")

# Now check a record that we know is INCOMING (a notification from device)
# Look for ATT Handle Value Notification (opcode 0x1B)
print(f"\nLooking for ATT notifications (opcode 0x1B) to determine incoming ACL handle...")
for i, rec in enumerate(records):
    if rec['type'] != 0x02:
        continue
    p = rec['payload']
    if len(p) > 8 and p[8] == 0x1B:
        acl_hdr = struct.unpack_from('<H', p, 0)[0]
        acl_handle = acl_hdr & 0x0FFF
        acl_flags = (acl_hdr >> 12) & 0x0F
        att_handle = struct.unpack_from('<H', p, 9)[0]
        data_preview = ' '.join(f'{b:02x}' for b in p[11:30])
        print(f"  rec[{i}] ACL handle=0x{acl_handle:03x} flags=0x{acl_flags:x} ATT notify handle=0x{att_handle:04x} data: {data_preview}")
        if i > 20:
            break

# How many 0x01 type records (outgoing)
print(f"\nLooking for type=0x01 (HCI ACL out) records with ATT Write Without Response...")
for i, rec in enumerate(records):
    if rec['type'] != 0x01:
        continue
    p = rec['payload']
    if len(p) > 8 and p[8] == 0x52:
        acl_hdr = struct.unpack_from('<H', p, 0)[0]
        acl_handle = acl_hdr & 0x0FFF
        att_handle = struct.unpack_from('<H', p, 9)[0]
        data_preview = ' '.join(f'{b:02x}' for b in p[11:min(30, len(p))])
        print(f"  rec[{i}] ACL handle=0x{acl_handle:03x} ATT WwoR handle=0x{att_handle:04x} data: {data_preview}")
        if i > 1700:
            break

# Actually in Apple PacketLogger:
# type 0x00 = HCI Command (outgoing)
# type 0x01 = HCI Event (incoming)  ← NOT outgoing ACL!
# type 0x02 = ACL Data (both directions)
# type 0x03 = SCO Data
# Wait, that might be wrong. Let me check the type distribution

from collections import Counter
type_counts = Counter(rec['type'] for rec in records)
print(f"\nRecord type distribution: {dict(type_counts)}")

# In Apple PacketLogger format:
# 0x00 = HCI Command (H→C)
# 0x01 = HCI Event (C→H)  
# 0x02 = Sent ACL Data (H→C)
# 0x03 = Received ACL Data (C→H)
# But some implementations use:
# 0x00 = Command Packet (Host to Controller)
# 0x01 = Event Packet (Controller to Host)
# 0x02 = ACL Data Packet (Sent)
# 0x03 = ACL Data Packet (Received)
# Apple uses 0x00=CMD, 0x01=EVENT, 0x02=ACL_TX, 0x03=ACL_RX
# BUT PacketLogger specifically may use different encoding

# Let me check by finding the first FE DC BA C0 frame (sent by phone) 
# and seeing what pklg type it has
print(f"\nFE DC BA C0 frames (flag=0xC0 = phone sends):")
for i, rec in enumerate(records):
    p = rec['payload']
    idx = p.find(b'\xFE\xDC\xBA\xC0')
    if idx >= 0 and idx + 7 < len(p):
        cmd = p[idx+4]
        body_len = (p[idx+5] << 8) | p[idx+6]
        body_hex = ' '.join(f'{b:02x}' for b in p[idx+7:idx+7+min(body_len, 20)])
        print(f"  rec[{i}] pklg_type=0x{rec['type']:02x} cmd=0x{cmd:02x} body_len={body_len} body: {body_hex}")
        if i > 100:
            break

print(f"\nFE DC BA 00 frames (flag=0x00 = device response):")
for i, rec in enumerate(records):
    p = rec['payload']
    # Need to search for FEDCBA00 but not confuse with FEDCBA0001
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA and p[idx+3] == 0x00:
            cmd = p[idx+4]
            body_len = (p[idx+5] << 8) | p[idx+6]
            if 0 < body_len < 200 and cmd != 0x01:  # exclude data frames
                body_hex = ' '.join(f'{b:02x}' for b in p[idx+7:idx+7+min(body_len, 20)])
                print(f"  rec[{i}] pklg_type=0x{rec['type']:02x} cmd=0x{cmd:02x} body_len={body_len} body: {body_hex}")
            break
