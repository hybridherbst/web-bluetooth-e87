#!/usr/bin/env python3
"""Analyze the exact interleaving of TX data chunks and RX window acks in the capture.
This tells us whether the original app waited for acks before sending more data."""
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

# Find all FE DC BA frames, track their order
print("=== Chronological FE frames during/after data transfer ===")
print("Looking for: TX data (cmd 0x01), RX win acks (cmd 0x1d), cmd 0x1b, 0x20, 0x1c")
print()

# First find the cmd 0x1b frame to know where data transfer starts
events = []
for r in records:
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            body = p[idx+7:idx+7+blen] if blen <= 100 else p[idx+7:idx+7+20]
            direction = 'TX' if r['type'] == 2 else 'RX' if r['type'] == 3 else f"t{r['type']}"
            events.append({
                'rec': r['idx'],
                'dir': direction,
                'flag': flag,
                'cmd': cmd,
                'blen': blen,
                'body': body,
                'ts': r['ts']
            })
            break

# Find where cmd 0x1b TX happens
start_idx = None
for i, e in enumerate(events):
    if e['cmd'] == 0x1b and e['dir'] == 'TX':
        start_idx = i
        break

if start_idx is None:
    print("Could not find cmd 0x1b TX!")
    exit(1)

# Print everything from cmd 0x1b onward
first_ts = events[start_idx]['ts']
data_chunk_count = 0
for e in events[start_idx:]:
    dt = e['ts'] - first_ts
    cmd_name = {0x1b: 'FILE_META', 0x01: 'DATA', 0x1d: 'WIN_ACK', 0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE', 0x21: 'BEGIN_UPLOAD', 0x27: 'XFER_PARAMS'}.get(e['cmd'], f"cmd_0x{e['cmd']:02x}")
    
    extra = ''
    if e['cmd'] == 0x01 and e['dir'] == 'TX':
        data_chunk_count += 1
        # Parse: body[0]=seq, body[1]=0x1d, body[2]=slot, body[3:5]=crc, body[5:]=payload
        if len(e['body']) >= 5:
            seq = e['body'][0]
            slot = e['body'][2]
            extra = f' seq={seq} slot={slot} chunk#{data_chunk_count}'
    elif e['cmd'] == 0x1d and e['dir'] == 'RX':
        # body: [seq, status, winSize_BE16, nextOffset_BE32]
        if len(e['body']) >= 8:
            seq = e['body'][0]
            status = e['body'][1]
            ws = (e['body'][2] << 8) | e['body'][3]
            noff = (e['body'][4] << 24) | (e['body'][5] << 16) | (e['body'][6] << 8) | e['body'][7]
            extra = f' seq={seq} status=0x{status:02x} winSize={ws} nextOff={noff}'
    elif e['cmd'] == 0x1b:
        extra = f' body={e["body"].hex()}'

    print(f'  +{dt:7.3f}s  {e["dir"]:2s}  flag=0x{e["flag"]:02x}  {cmd_name:16s}{extra}')

print(f'\nTotal data chunks: {data_chunk_count}')
