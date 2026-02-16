#!/usr/bin/env python3
"""Show ALL FE frames during data transfer to find window acks."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    secs = struct.unpack_from('<I', raw, off + 4)[0]
    usecs = struct.unpack_from('<I', raw, off + 8)[0]
    ts_us = secs * 1_000_000 + usecs
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'type': ptype, 'payload': payload, 'ts': ts_us})
    off += 4 + rec_len
    if off > len(raw): break

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

# Find the first data frame
data_start = None
for f in fe_frames:
    if f['flag'] == 0x80 and f['cmd'] == 0x01 and f['dir'] == 'TX':
        data_start = f['ts']
        break

print(f"Total FE frames: {len(fe_frames)}")
print(f"\nALL FE frames from data transfer onward:\n")
for f in fe_frames:
    if f['ts'] >= data_start - 100000:
        rel = (f['ts'] - data_start) / 1000
        body_hex = f['body'][:16].hex() if f['body'] else ''
        label = ''
        if f['flag'] == 0x80 and f['cmd'] == 0x01:
            label = 'DATA'
        elif f['flag'] == 0x80 and f['cmd'] == 0x1d:
            label = 'WACK'
            if len(f['body']) >= 8:
                ack_seq = f['body'][0]
                win = (f['body'][2] << 8) | f['body'][3]
                foff = (f['body'][4] << 24) | (f['body'][5] << 16) | (f['body'][6] << 8) | f['body'][7]
                label = f'WACK ackseq={ack_seq} win={win} off={foff}'
        elif f['cmd'] == 0x20:
            label = 'FILE_COMPLETE'
        elif f['cmd'] == 0x1c:
            label = 'SESSION_CLOSE'
        else:
            label = f'cmd=0x{f["cmd"]:02x}'
        
        print(f'  {rel:8.1f}ms  {f["dir"]} flag=0x{f["flag"]:02x} {label:40s} body={body_hex}')
