#!/usr/bin/env python3
"""Analyze window acks with both fragmented and single-record FE frames."""
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

def find_fe_in_bytes(data):
    """Find FE DC BA ... EF frames in raw bytes."""
    frames = []
    for idx in range(len(data) - 7):
        if data[idx] == 0xFE and data[idx+1] == 0xDC and data[idx+2] == 0xBA:
            flag = data[idx+3]
            cmd = data[idx+4]
            blen = (data[idx+5] << 8) | data[idx+6]
            end = idx + 7 + blen
            if end < len(data) and data[end] == 0xEF:
                frames.append({
                    'flag': flag, 'cmd': cmd,
                    'body': data[idx+7:end], 'blen': blen
                })
    return frames

# Collect ALL FE frames from all records (simple scan, no L2CAP reassembly)
all_fe = []
for rec in records:
    p = rec['payload']
    direction = 'TX' if rec['type'] == 2 else ('RX' if rec['type'] == 3 else 'OTHER')
    frames = find_fe_in_bytes(p)
    for f in frames:
        all_fe.append({**f, 'dir': direction, 'rec': rec['idx']})

# Now analyze data frames and acks in order
data_count = 0
data_bytes = 0

print("COMPLETE PROTOCOL FLOW (data frames + acks + completion):")
print("="*100)

for i, f in enumerate(all_fe):
    if f['flag'] == 0x80 and f['cmd'] == 0x01:
        body = f['body']
        if len(body) >= 5:
            seq = body[0]
            slot = body[2]
            data_len = len(body) - 5
            data_count += 1
            data_bytes += data_len
            
            # Only print for last few data frames
            if data_count >= 29 or slot == 0:
                preview = ' '.join(f'{b:02x}' for b in body[5:5+8])
                print(f"  DATA #{data_count:2d} seq=0x{seq:02x} slot={slot} data={data_len}B "
                      f"(total={data_bytes}) preview={preview}")
        continue
    
    if f['flag'] == 0x80 and f['cmd'] == 0x1d:
        body = f['body']
        body_hex = ' '.join(f'{b:02x}' for b in body)
        if len(body) >= 8:
            ack_seq = body[0]
            win_be = (body[2] << 8) | body[3]
            off_be32 = (body[4]<<24)|(body[5]<<16)|(body[6]<<8)|body[7]
            
            print(f"\n  === WINDOW ACK #{ack_seq} === {f['dir']} (after {data_count} data, {data_bytes} bytes)")
            print(f"      body: {body_hex}")
            print(f"      window_size = {win_be} ({win_be//490} chunks)")
            print(f"      offset(?) = {off_be32} ({off_be32//490 if off_be32%490==0 else off_be32} chunks)")
            print()
        continue
    
    if f['cmd'] in (0x20, 0x1c, 0x1b, 0x21, 0x27):
        body_hex = ' '.join(f'{b:02x}' for b in f['body'][:40])
        cmd_names = {0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE', 0x1b: 'METADATA',
                     0x21: 'BEGIN_UPLOAD', 0x27: 'XFER_PARAMS'}
        name = cmd_names.get(f['cmd'], f'0x{f["cmd"]:02x}')
        print(f"  CMD {name} flag=0x{f['flag']:02x} {f['dir']} body={body_hex}")
