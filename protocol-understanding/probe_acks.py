#!/usr/bin/env python3
"""Extract ALL window acks and analyze their body content."""
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

def find_fe_frames(payload):
    frames = []
    for idx in range(len(payload)):
        if idx + 7 < len(payload) and payload[idx] == 0xFE and payload[idx+1] == 0xDC and payload[idx+2] == 0xBA:
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

# Collect all FE-framed records
all_fe = []
for rec in records:
    direction = {0: 'CMD', 1: 'EVT', 2: 'TX', 3: 'RX'}.get(rec['type'], f'?{rec["type"]}')
    frames = find_fe_frames(rec['payload'])
    for f in frames:
        all_fe.append({'rec_idx': rec['idx'], 'dir': direction, 'ptype': rec['type'], **f})

print("ALL WINDOW ACKS (flag=0x80, cmd=0x1d):")
print("="*80)
data_count = 0
for i, fe in enumerate(all_fe):
    if fe['flag'] == 0x80 and fe['cmd'] == 0x01:
        data_count += 1
    if fe['flag'] == 0x80 and fe['cmd'] == 0x1d:
        body = fe['body']
        body_hex = ' '.join(f'{b:02x}' for b in body)
        
        # Parse the ack body
        # body[0:2] might be cumulative offset or sequence info
        # Let's try both BE and LE interpretations
        if len(body) >= 8:
            b0 = body[0]
            b1 = body[1]
            be16_01 = (body[0] << 8) | body[1]
            le16_01 = body[0] | (body[1] << 8)
            be16_23 = (body[2] << 8) | body[3]
            le16_23 = body[2] | (body[3] << 8)
            be16_45 = (body[4] << 8) | body[5]
            le16_45 = body[4] | (body[5] << 8)
            be16_67 = (body[6] << 8) | body[7]
            le16_67 = body[6] | (body[7] << 8)
            
            be32_04 = (body[0] << 24) | (body[1] << 16) | (body[2] << 8) | body[3]
            le32_04 = body[0] | (body[1] << 8) | (body[2] << 16) | (body[3] << 24)
            be32_48 = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
            le32_48 = body[4] | (body[5] << 8) | (body[6] << 16) | (body[7] << 24)
            
            print(f"\n[FE {i:3d}] {fe['dir']:3s} rec={fe['rec_idx']:4d}  (after {data_count} data frames)")
            print(f"  body: {body_hex}")
            print(f"  body[0]={b0:02x} body[1]={b1:02x}")
            print(f"  [0:2] BE={be16_01} LE={le16_01}")
            print(f"  [2:4] BE={be16_23} LE={le16_23}")
            print(f"  [4:6] BE={be16_45} LE={le16_45}")
            print(f"  [6:8] BE={be16_67} LE={le16_67}")
            print(f"  [0:4] BE32={be32_04} LE32={le32_04}")
            print(f"  [4:8] BE32={be32_48} LE32={le32_48}")
            
            # Check if any field equals data_count * 490 or data_count * 495
            for label, val in [("[0:4] BE32", be32_04), ("[0:4] LE32", le32_04),
                               ("[4:8] BE32", be32_48), ("[4:8] LE32", le32_48),
                               ("[0:2] BE", be16_01), ("[2:4] BE", be16_23)]:
                if val > 0:
                    if val % 490 == 0:
                        print(f"  ** {label}={val} = {val//490} * 490")
                    if val % 495 == 0:
                        print(f"  ** {label}={val} = {val//495} * 495")

# Also print data frames before each ack to show the pattern
print("\n\nDATA FRAME SEQUENCE (seq, slot, body_len):")
print("="*80)
for i, fe in enumerate(all_fe):
    if fe['flag'] == 0x80 and fe['cmd'] == 0x01:
        body = fe['body']
        if len(body) >= 3:
            seq = body[0]
            marker = body[1]
            slot = body[2]
            print(f"  [FE {i:3d}] DATA seq=0x{seq:02x} marker=0x{marker:02x} slot={slot} body_len={len(body)}")
    elif fe['flag'] == 0x80 and fe['cmd'] == 0x1d:
        body_hex = ' '.join(f'{b:02x}' for b in fe['body'])
        print(f"  [FE {i:3d}] WINDOW ACK body={body_hex}")
    elif fe['cmd'] in (0x20, 0x1c):
        body_hex = ' '.join(f'{b:02x}' for b in fe['body'])
        print(f"  [FE {i:3d}] CMD 0x{fe['cmd']:02x} flag=0x{fe['flag']:02x} body={body_hex}")
