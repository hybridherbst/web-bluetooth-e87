#!/usr/bin/env python3
"""Check which ATT handles are used for what in the capture."""
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

# Find characteristic discovery (Read By Type Response, ATT opcode 0x09)
# and service discovery to map handles to UUIDs
print("=== ATT HANDLE MAPPING ===")
handles_seen = {}
for r in records:
    p = r['payload']
    if len(p) <= 8:
        continue
    att_op = p[8] if len(p) > 8 else 0
    
    # Write Without Response (0x52) or Write Request (0x12) or Notification (0x1b)
    if att_op in (0x52, 0x12, 0x1b) and len(p) > 10:
        handle = p[9] | (p[10] << 8)
        direction = 'TX' if r['type'] == 2 else 'RX'
        op_name = {0x52: 'WriteNoResp', 0x12: 'WriteReq', 0x1b: 'Notification'}[att_op]
        if handle not in handles_seen:
            handles_seen[handle] = {'ops': set(), 'dirs': set(), 'count': 0}
        handles_seen[handle]['ops'].add(op_name)
        handles_seen[handle]['dirs'].add(direction)
        handles_seen[handle]['count'] += 1

for handle in sorted(handles_seen.keys()):
    info = handles_seen[handle]
    print(f"  Handle 0x{handle:04x}: {info['count']} operations, ops={info['ops']}, dirs={info['dirs']}")

# Find Read By Group Type responses (service discovery, ATT opcode 0x11)
# and Read By Type responses (characteristic discovery, ATT opcode 0x09)
print("\n=== GATT DISCOVERY ===")
for r in records:
    p = r['payload']
    if len(p) <= 8:
        continue
    att_op = p[8]
    
    if att_op == 0x11 and r['type'] == 3:  # Read By Group Type Response (RX)
        attr_len = p[9]
        data = p[10:]
        i = 0
        while i + attr_len <= len(data):
            start_handle = data[i] | (data[i+1] << 8)
            end_handle = data[i+2] | (data[i+3] << 8)
            uuid = data[i+4:i+attr_len]
            uuid_str = uuid[::-1].hex() if len(uuid) > 2 else f"0x{(uuid[0] | (uuid[1]<<8)):04x}"
            print(f"  Service: handles 0x{start_handle:04x}-0x{end_handle:04x} UUID={uuid_str}")
            i += attr_len
    
    if att_op == 0x09 and r['type'] == 3:  # Read By Type Response (RX)
        attr_len = p[9]
        data = p[10:]
        i = 0
        while i + attr_len <= len(data):
            handle = data[i] | (data[i+1] << 8)
            properties = data[i+2]
            value_handle = data[i+3] | (data[i+4] << 8)
            uuid = data[i+5:i+attr_len]
            uuid_str = uuid[::-1].hex() if len(uuid) > 2 else f"0x{(uuid[0] | (uuid[1]<<8)):04x}"
            prop_str = []
            if properties & 0x04: prop_str.append('WriteNoResp')
            if properties & 0x08: prop_str.append('Write')
            if properties & 0x10: prop_str.append('Notify')
            if properties & 0x20: prop_str.append('Indicate')
            print(f"  Char: handle=0x{handle:04x} value_handle=0x{value_handle:04x} props={','.join(prop_str)} UUID={uuid_str}")
            i += attr_len
