#!/usr/bin/env python3
"""Look at EVERY record between the last data frame and cmd 0x20 to see if 
we're missing any non-data FE frames or control messages."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'len': rec_len - 9, 'type': ptype, 'payload': payload, 'ts': ts})
    off += 4 + rec_len
    if off > len(raw):
        break

# Show records 1740-1775 in full detail
print("DETAILED RECORDS 1740-1775:")
print("="*100)
for rec in records[1740:1775]:
    p = rec['payload']
    direction = {0: 'CMD', 1: 'EVT', 2: 'ACL_TX', 3: 'ACL_RX'}.get(rec['type'], f'type={rec["type"]}')
    
    # Parse ACL header if present
    att_info = ""
    if rec['type'] in (2, 3) and len(p) > 10:
        acl_handle = struct.unpack_from('<H', p, 0)[0] & 0x0FFF
        acl_flags = (struct.unpack_from('<H', p, 0)[0] >> 12) & 0x0F
        acl_len = struct.unpack_from('<H', p, 2)[0]
        if len(p) > 8:
            opcode = p[8]
            opcodes = {0x52: 'WriteWoR', 0x12: 'WriteReq', 0x13: 'WriteRsp', 0x1B: 'Notify', 0x1D: 'Indicate'}
            opname = opcodes.get(opcode, f'op=0x{opcode:02x}')
            if opcode in (0x52, 0x12, 0x1B, 0x1D) and len(p) > 10:
                att_handle = struct.unpack_from('<H', p, 9)[0]
                att_info = f" ATT:{opname} h=0x{att_handle:04x}"
            else:
                att_info = f" ATT:{opname}"
    
    # Check for FE frames
    fe_info = ""
    for idx in range(len(p)):
        if idx + 7 < len(p) and p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            body_len = (p[idx+5] << 8) | p[idx+6]
            body_start = idx + 7
            body_preview = p[body_start:body_start+min(20, body_len)]
            body_hex = ' '.join(f'{b:02x}' for b in body_preview)
            fe_info = f" | FE: flag=0x{flag:02x} cmd=0x{cmd:02x} blen={body_len} body={body_hex}"
            break
    
    # Check for 9E control frames  
    ctrl_info = ""
    if len(p) > 10 and rec['type'] in (2, 3):
        # Look for 9E prefix in ATT value area
        for idx in range(8, min(len(p), 14)):
            if idx < len(p) and p[idx] == 0x9E:
                ctrl_hex = ' '.join(f'{b:02x}' for b in p[idx:idx+min(10, len(p)-idx)])
                ctrl_info = f" | CTRL: {ctrl_hex}"
                break
    
    data_hex = ' '.join(f'{b:02x}' for b in p[:30])
    if len(p) > 30:
        data_hex += '...'
    
    print(f"  [{rec['idx']:4d}] {direction:8s} len={len(p):3d}{att_info}{fe_info}{ctrl_info}")
    print(f"         {data_hex}")
