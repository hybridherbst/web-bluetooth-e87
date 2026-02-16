#!/usr/bin/env python3
"""Analyze timing of data transfer using correct pklg timestamp format:
   [unix_seconds_LE32][microseconds_LE32]"""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    secs = struct.unpack_from('<I', raw, off + 4)[0]
    usecs = struct.unpack_from('<I', raw, off + 8)[0]
    ts_us = secs * 1_000_000 + usecs  # total microseconds
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'type': ptype, 'payload': payload, 'ts': ts_us})
    off += 4 + rec_len
    if off > len(raw):
        break

# Reconstruct L2CAP & FE frames
current = None
fe_frames = []

for rec in records:
    if rec['type'] not in (2, 3): continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'dir': rec['type'], 'data': bytearray(p[8:]), 'expected': l2cap_len, 'ts': rec['ts']}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    else:
        continue
    
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        direction = 'TX' if current['dir'] == 2 else 'RX'
        
        if len(data) >= 3:
            att_val = data[3:] if len(data) > 3 else b''
            for idx in range(len(att_val)):
                if (idx + 7 < len(att_val) and 
                    att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                    flag = att_val[idx+3]
                    cmd = att_val[idx+4]
                    blen = (att_val[idx+5] << 8) | att_val[idx+6]
                    end = idx + 7 + blen
                    if end < len(att_val) and att_val[end] == 0xEF:
                        body = att_val[idx+7:end]
                        fe_frames.append({
                            'ts': current['ts'], 'dir': direction,
                            'flag': flag, 'cmd': cmd, 'body': body,
                        })
                    break
        current = None

# Filter transfer events
transfer = []
for f in fe_frames:
    if f['flag'] == 0x80 and f['cmd'] == 0x01 and f['dir'] == 'TX':
        transfer.append(('DATA', f))
    elif f['flag'] == 0x80 and f['cmd'] == 0x1d:
        transfer.append(('WACK', f))
    elif f['cmd'] in (0x20, 0x1c):
        transfer.append((f'CMD_0x{f["cmd"]:02x}', f))

t0 = transfer[0][1]['ts']
prev_ts = t0

print("=== FULL TRANSFER TIMELINE ===\n")
window_num = 0
for label, f in transfer:
    rel_ms = (f['ts'] - t0) / 1000
    dt_ms = (f['ts'] - prev_ts) / 1000
    
    extra = ""
    if label == 'DATA':
        seq = f['body'][0]
        slot = f['body'][2] if len(f['body']) > 2 else -1
        data_len = len(f['body']) - 5
        extra = f"seq=0x{seq:02x} slot={slot} len={data_len}"
    elif label == 'WACK':
        if len(f['body']) >= 8:
            ack_seq = f['body'][0]
            win = (f['body'][2] << 8) | f['body'][3]
            foff = (f['body'][4] << 24) | (f['body'][5] << 16) | (f['body'][6] << 8) | f['body'][7]
            extra = f"ackseq={ack_seq} win={win} off={foff} ({f['dir']})"
    else:
        extra = f"({f['dir']})"
    
    marker = "  >>>" if label == 'WACK' else "     "
    print(f"{marker} {rel_ms:8.1f}ms  +{dt_ms:6.1f}ms  {label:8s} {extra}")
    prev_ts = f['ts']

# Stats
data_frames = [(l, f) for l, f in transfer if l == 'DATA']
print(f"\n=== SUMMARY ===")
total_ms = (transfer[-1][1]['ts'] - t0) / 1000
print(f"Total transfer: {total_ms:.1f} ms ({total_ms/1000:.2f} s)")
print(f"Data frames: {len(data_frames)}")

# Within-window delays
in_window = []
cross_window = []
for i in range(1, len(data_frames)):
    dt = (data_frames[i][1]['ts'] - data_frames[i-1][1]['ts']) / 1000
    slot = data_frames[i][1]['body'][2]
    if slot == 0:
        cross_window.append(dt)
    else:
        in_window.append(dt)

print(f"\nWithin-window delays ({len(in_window)} gaps):")
if in_window:
    print(f"  Min:  {min(in_window):.1f} ms")
    print(f"  Max:  {max(in_window):.1f} ms")
    print(f"  Mean: {sum(in_window)/len(in_window):.1f} ms")

print(f"\nCross-window delays ({len(cross_window)} gaps):")
if cross_window:
    print(f"  Min:  {min(cross_window):.1f} ms")
    print(f"  Max:  {max(cross_window):.1f} ms")
    print(f"  Mean: {sum(cross_window)/len(cross_window):.1f} ms")
