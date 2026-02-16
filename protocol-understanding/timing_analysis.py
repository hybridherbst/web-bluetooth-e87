#!/usr/bin/env python3
"""Analyze timing between data frames in the pklg capture."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'type': ptype, 'ts': ts, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw):
        break

# Reconstruct L2CAP frames with timestamps
current = None
frames = []

for rec in records:
    if rec['type'] not in (2, 3): continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'dir': rec['type'], 'data': bytearray(p[8:]), 'expected': l2cap_len, 'ts': rec['ts'], 'idx': rec['idx']}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    else:
        continue
    
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        direction = 'TX' if current['dir'] == 2 else 'RX'
        
        # Parse ATT for FE frames
        if len(data) >= 3:
            att_op = data[0]
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
                        frames.append({
                            'ts': current['ts'],
                            'dir': direction,
                            'flag': flag,
                            'cmd': cmd,
                            'body_len': blen,
                            'body': body,
                            'rec_idx': current['idx']
                        })
                    break
        current = None

print(f"Total FE frames: {len(frames)}")
print()

# Find data frames (flag=0x80, cmd=0x01) and window acks (flag=0x80, cmd=0x1d)
print("=== DATA TRANSFER TIMING ===")
print()

data_frames = []
ack_frames = []
all_transfer = []

for f in frames:
    if f['flag'] == 0x80 and f['cmd'] == 0x01 and f['dir'] == 'TX':
        data_frames.append(f)
        all_transfer.append(f)
    elif f['flag'] == 0x80 and f['cmd'] == 0x1d:
        ack_frames.append(f)
        all_transfer.append(f)
    elif f['cmd'] in (0x20, 0x1c):
        all_transfer.append(f)

# Show timing for all transfer events
if all_transfer:
    t0 = all_transfer[0]['ts']
    prev_ts = t0
    window_num = 0
    chunk_in_window = 0
    
    for i, f in enumerate(all_transfer):
        dt_total = (f['ts'] - t0) / 1_000_000  # microseconds to seconds
        dt_prev = (f['ts'] - prev_ts) / 1_000_000
        
        if f['flag'] == 0x80 and f['cmd'] == 0x01:
            seq = f['body'][0] if f['body'] else -1
            slot = f['body'][2] if len(f['body']) > 2 else -1
            data_len = len(f['body']) - 5 if len(f['body']) > 5 else 0
            print(f"  [{dt_total:7.3f}s] +{dt_prev*1000:7.1f}ms  {f['dir']} DATA seq=0x{seq:02x} slot={slot} payload={data_len}B")
            chunk_in_window += 1
        elif f['flag'] == 0x80 and f['cmd'] == 0x1d:
            if f['body'] and len(f['body']) >= 8:
                ack_seq = f['body'][0]
                win_size = (f['body'][2] << 8) | f['body'][3]
                offset = (f['body'][4] << 24) | (f['body'][5] << 16) | (f['body'][6] << 8) | f['body'][7]
                print(f"  [{dt_total:7.3f}s] +{dt_prev*1000:7.1f}ms  {f['dir']} WACK seq={ack_seq} win={win_size} offset={offset}")
            else:
                print(f"  [{dt_total:7.3f}s] +{dt_prev*1000:7.1f}ms  {f['dir']} WACK body={f['body'].hex()}")
            window_num += 1
            chunk_in_window = 0
        elif f['cmd'] == 0x20:
            print(f"  [{dt_total:7.3f}s] +{dt_prev*1000:7.1f}ms  {f['dir']} CMD_0x20 (FILE_COMPLETE)")
        elif f['cmd'] == 0x1c:
            print(f"  [{dt_total:7.3f}s] +{dt_prev*1000:7.1f}ms  {f['dir']} CMD_0x1c (SESSION_CLOSE)")
        
        prev_ts = f['ts']
    
    total_time = (all_transfer[-1]['ts'] - t0) / 1_000_000
    print(f"\n  Total transfer time: {total_time:.3f}s")
    print(f"  Data frames: {len(data_frames)}")
    print(f"  Window acks: {len(ack_frames)}")

# Compute inter-frame delays for data frames only
if len(data_frames) > 1:
    delays_ms = []
    for i in range(1, len(data_frames)):
        dt = (data_frames[i]['ts'] - data_frames[i-1]['ts']) / 1000  # us to ms
        delays_ms.append(dt)
    
    print(f"\n=== INTER-FRAME DELAYS (data frames only) ===")
    print(f"  Min:    {min(delays_ms):.1f} ms")
    print(f"  Max:    {max(delays_ms):.1f} ms")
    print(f"  Mean:   {sum(delays_ms)/len(delays_ms):.1f} ms")
    print(f"  Median: {sorted(delays_ms)[len(delays_ms)//2]:.1f} ms")
    
    # Within-window delays (exclude ack waits)
    in_window = []
    for i in range(1, len(data_frames)):
        slot_prev = data_frames[i-1]['body'][2] if len(data_frames[i-1]['body']) > 2 else 0
        slot_curr = data_frames[i]['body'][2] if len(data_frames[i]['body']) > 2 else 0
        # If slot went from 7 to 0, this is across a window boundary
        if slot_curr == 0 and slot_prev == 7:
            continue
        in_window.append(delays_ms[i-1])
    
    if in_window:
        print(f"\n=== WITHIN-WINDOW DELAYS (same window) ===")
        print(f"  Min:    {min(in_window):.1f} ms")
        print(f"  Max:    {max(in_window):.1f} ms")
        print(f"  Mean:   {sum(in_window)/len(in_window):.1f} ms")
        print(f"  Median: {sorted(in_window)[len(in_window)//2]:.1f} ms")
