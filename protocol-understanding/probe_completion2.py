#!/usr/bin/env python3
"""Extract the exact completion handshake from cap.pklg after all data frames."""
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

print(f"Total records: {len(records)}")

def find_fe_frames(payload):
    """Find all FE DC BA ... EF frames in a payload."""
    frames = []
    for idx in range(len(payload)):
        if idx + 7 < len(payload) and payload[idx] == 0xFE and payload[idx+1] == 0xDC and payload[idx+2] == 0xBA:
            # Find EF terminator
            for end in range(idx + 7, len(payload)):
                if payload[end] == 0xEF:
                    flag = payload[idx+3]
                    cmd = payload[idx+4]
                    body_len = (payload[idx+5] << 8) | payload[idx+6]
                    body = payload[idx+7:end]
                    frames.append({
                        'flag': flag, 'cmd': cmd, 'body_len': body_len,
                        'body': body, 'raw': payload[idx:end+1]
                    })
                    break
    return frames

# Collect all FE-framed records with their record index and direction
all_fe = []
for rec in records:
    direction = {0: 'CMD', 1: 'EVT', 2: 'TX', 3: 'RX'}.get(rec['type'], f'?{rec["type"]}')
    frames = find_fe_frames(rec['payload'])
    for f in frames:
        all_fe.append({'rec_idx': rec['idx'], 'dir': direction, 'ptype': rec['type'], **f})

print(f"Total FE frames: {len(all_fe)}")

# Find last data frame (flag=0x80, cmd=0x01)
last_data_idx = -1
for i, fe in enumerate(all_fe):
    if fe['flag'] == 0x80 and fe['cmd'] == 0x01:
        last_data_idx = i

print(f"Last data frame at FE index {last_data_idx}")

# Print everything from 5 before last data to end
print("\n" + "="*120)
print("COMPLETION SEQUENCE (from last few data frames to end)")
print("="*120)

start = max(0, last_data_idx - 3)
for i in range(start, len(all_fe)):
    fe = all_fe[i]
    body_hex = ' '.join(f'{b:02x}' for b in fe['body'])
    raw_hex = ' '.join(f'{b:02x}' for b in fe['raw'])
    
    marker = ""
    if fe['flag'] == 0x80 and fe['cmd'] == 0x01:
        marker = " [DATA]"
    elif fe['flag'] == 0x80 and fe['cmd'] == 0x1d:
        marker = " [WINDOW ACK]"
    elif fe['cmd'] == 0x20:
        marker = " [CMD 0x20 - FILE COMPLETE]"
    elif fe['cmd'] == 0x1c:
        marker = " [CMD 0x1C - SESSION CLOSE]"
    
    print(f"\n[FE {i:3d}] rec={fe['rec_idx']:4d} {fe['dir']:3s}  flag=0x{fe['flag']:02x} cmd=0x{fe['cmd']:02x} body_len={fe['body_len']}{marker}")
    print(f"  body ({len(fe['body'])} bytes): {body_hex}")
    print(f"  raw: {raw_hex}")

# Also print ALL raw records after the last data frame's record
print("\n" + "="*120)
print("RAW RECORDS (non-FE) after last data frame")
print("="*120)

if last_data_idx >= 0:
    last_data_rec = all_fe[last_data_idx]['rec_idx']
    for rec in records[last_data_rec:]:
        direction = {0: 'CMD', 1: 'EVT', 2: 'TX', 3: 'RX'}.get(rec['type'], f'?{rec["type"]}')
        p = rec['payload']
        has_fe = any(p[i] == 0xFE and p[i+1] == 0xDC and p[i+2] == 0xBA 
                     for i in range(len(p)-2) if i+2 < len(p))
        
        # ATT info
        att_info = ""
        if rec['type'] in (2, 3) and len(p) > 10:
            opcode = p[8] if len(p) > 8 else 0
            opcodes = {0x52: 'WriteWoR', 0x12: 'WriteReq', 0x13: 'WriteRsp', 0x1B: 'Notify', 0x1D: 'Indicate'}
            opname = opcodes.get(opcode, f'op=0x{opcode:02x}')
            if opcode in (0x52, 0x12, 0x1B, 0x1D) and len(p) > 10:
                att_handle = struct.unpack_from('<H', p, 9)[0]
                att_info = f" ATT:{opname} h=0x{att_handle:04x}"

        data_hex = ' '.join(f'{b:02x}' for b in p[:60])
        if len(p) > 60:
            data_hex += ' ...'
        fe_tag = " [has FE frame]" if has_fe else ""
        print(f"  [{rec['idx']:4d}] {direction:3s}{att_info}{fe_tag} len={len(p):3d} | {data_hex}")
