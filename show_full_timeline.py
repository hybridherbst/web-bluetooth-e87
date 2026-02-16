#!/usr/bin/env python3
"""Show ALL events (TX and RX) in chronological order between the last tail data chunk and session close."""
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
    if off > len(raw):
        break

# Parse all FE frames with timestamps
events = []
for r in records:
    if r['type'] not in (2, 3):
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            body = p[idx+7:idx+7+blen]
            direction = 'TX' if r['type'] == 2 else 'RX'
            events.append({
                'dir': direction, 'flag': flag, 'cmd': cmd, 'blen': blen,
                'body': body, 'ts': r['ts'], 'rec_idx': r['idx']
            })
            break

# Also look for non-FE frames (raw BLE notifications/writes)
for r in records:
    p = r['payload']
    if len(p) > 11:
        att_op = p[8] if len(p) > 8 else 0
        att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
        # Check if this record has an FE frame
        has_fe = any(p[idx] == 0xFE and idx+2 < len(p) and p[idx+1] == 0xDC and p[idx+2] == 0xBA for idx in range(len(p)-7))
        if not has_fe and att_op in (0x1b, 0x52):  # ATT notification or write
            direction = 'TX' if r['type'] == 2 else 'RX'
            att_value = p[11:min(len(p), 30)]
            events.append({
                'dir': direction, 'flag': -1, 'cmd': -1, 'blen': len(p)-11,
                'body': att_value, 'ts': r['ts'], 'rec_idx': r['idx'],
                'att_op': att_op, 'att_handle': att_handle, 'raw': True
            })

events.sort(key=lambda e: e['ts'])

# Find the last 0x1b meta ack timestamp as a reference
meta_ts = None
for e in events:
    if e.get('cmd') == 0x1b and e['dir'] == 'RX':
        meta_ts = e['ts']

if meta_ts:
    print("=== ALL EVENTS FROM FILE META TO END ===")
    print(f"Reference time: {meta_ts:.6f}")
    for e in events:
        if e['ts'] < meta_ts - 0.1:
            continue
        t_rel = (e['ts'] - meta_ts) * 1000  # ms relative to meta ack
        
        if e.get('raw'):
            print(f"  +{t_rel:8.1f}ms  {e['dir']:2s}  RAW att_op=0x{e['att_op']:02x} handle=0x{e['att_handle']:04x} value={e['body'].hex()}")
            continue
            
        cmd_names = {0x01: 'DATA', 0x1b: 'FILE_META', 0x1d: 'WIN_ACK', 0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE'}
        name = cmd_names.get(e['cmd'], f"cmd_0x{e['cmd']:02x}")
        
        extra = ''
        if e['cmd'] == 0x1d and e['dir'] == 'RX' and len(e['body']) >= 8:
            b = e['body']
            seq = b[0]
            ws = (b[2] << 8) | b[3]
            noff = (b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]
            extra = f" seq={seq} winSize={ws} nextOff={noff}"
        elif e['cmd'] == 0x01 and len(e['body']) >= 5:
            extra = f" seq={e['body'][0]} slot={e['body'][2]}"
        elif e['cmd'] in (0x20, 0x1c):
            extra = f" body={e['body'].hex()}"
        
        print(f"  +{t_rel:8.1f}ms  {e['dir']:2s}  flag=0x{e['flag']:02x} {name:16s}{extra}")
