#!/usr/bin/env python3
"""Analyze window ack bodies to understand the re-send protocol."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw):
        break

# Reconstruct L2CAP and extract FE frames (same as probe_sequence.py)
assembled = []
current = None
for rec in records:
    if rec['type'] not in (2, 3): continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'dir': 'TX' if rec['type'] == 2 else 'RX', 'data': bytearray(p[8:]), 'expected': l2cap_len, 'rec': rec['idx']}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        if len(data) >= 3:
            op = data[0]
            if op in (0x52, 0x1B) and len(data) > 5:
                val = data[3:]
                for idx in range(len(val)):
                    if idx+7 < len(val) and val[idx]==0xFE and val[idx+1]==0xDC and val[idx+2]==0xBA:
                        flag = val[idx+3]; cmd = val[idx+4]
                        blen = (val[idx+5]<<8)|val[idx+6]
                        end = idx+7+blen
                        if end < len(val) and val[end] == 0xEF:
                            assembled.append({'dir': current['dir'], 'flag': flag, 'cmd': cmd, 
                                            'body': bytes(val[idx+7:end]), 'rec': current['rec']})
                        break
        current = None

# Track data frames and window acks
data_count = 0
data_bytes = 0

print("WINDOW ACK ANALYSIS:")
print("="*100)
for i, f in enumerate(assembled):
    if f['flag'] == 0x80 and f['cmd'] == 0x01:
        body = f['body']
        data_len = len(body) - 5  # minus header
        data_count += 1
        data_bytes += data_len
    
    if f['flag'] == 0x80 and f['cmd'] == 0x1d:
        body = f['body']
        ack_seq = body[0]
        b1 = body[1]
        win_size_be = (body[2] << 8) | body[3]
        
        # body[4:8] - let's try different interpretations
        b4567_be32 = (body[4]<<24)|(body[5]<<16)|(body[6]<<8)|body[7]
        b45_be = (body[4]<<8)|body[5]
        b67_be = (body[6]<<8)|body[7]
        
        print(f"\nACK #{ack_seq} (after {data_count} data frames sent, {data_bytes} file bytes)")
        print(f"  body: {' '.join(f'{b:02x}' for b in body)}")
        print(f"  [0] ack_seq = {ack_seq}")
        print(f"  [1] = 0x{b1:02x}")
        print(f"  [2:4] window_size = {win_size_be} = {win_size_be//490} × 490 + {win_size_be%490}")
        print(f"  [4:6] = {b45_be} (0x{b45_be:04x})")
        print(f"  [6:8] = {b67_be} (0x{b67_be:04x})")
        print(f"  [4:8] as BE32 = {b4567_be32}")
        
        # Check interpretations
        if win_size_be > 0:
            chunks_requested = win_size_be // 490
            print(f"  → Device wants {chunks_requested} chunk(s) of 490 bytes")
        if b4567_be32 % 490 == 0 and b4567_be32 > 0:
            print(f"  → [4:8] = {b4567_be32//490} × 490 (offset in file?)")
        elif b4567_be32 == 0:
            print(f"  → [4:8] = 0 (start of file / no offset)")
            
    if f['cmd'] == 0x20:
        print(f"\nCMD 0x20 (flag=0x{f['flag']:02x}): body={' '.join(f'{b:02x}' for b in f['body'])}")
    if f['cmd'] == 0x1c:
        print(f"CMD 0x1C (flag=0x{f['flag']:02x}): body={' '.join(f'{b:02x}' for b in f['body'])}")
