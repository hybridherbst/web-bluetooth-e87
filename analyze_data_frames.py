#!/usr/bin/env python3
"""Analyze all data frames and the full completion handshake sequence."""
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

# Parse all FE frames
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
            frame_end = idx + 7 + blen
            trailer = p[frame_end] if frame_end < len(p) else None
            direction = 'TX' if r['type'] == 2 else 'RX'
            events.append({
                'rec': r['idx'], 'dir': direction, 'flag': flag, 'cmd': cmd,
                'blen': blen, 'body': body, 'trailer': trailer, 'ts': r['ts'],
            })
            break

# Show all data frames
print('=== ALL DATA FRAMES (cmd 0x01, flag 0x80) ===')
data_frames = [e for e in events if e['cmd'] == 0x01 and e['flag'] == 0x80]
for e in data_frames:
    b = e['body']
    if len(b) >= 5:
        seq = b[0]
        subcmd = b[1]
        slot = b[2]
        crc = (b[3] << 8) | b[4]
        print(f"  seq=0x{seq:02x}({seq:3d}) subcmd=0x{subcmd:02x} slot={slot} crc=0x{crc:04x} payload={len(b)-5} bytes  first_data={b[5:9].hex() if len(b)>8 else '?'}")

print(f"\nTotal data frames: {len(data_frames)}")
if data_frames:
    print(f"First seq: 0x{data_frames[0]['body'][0]:02x}, Last seq: 0x{data_frames[-1]['body'][0]:02x}")
    # Last data frame details
    last = data_frames[-1]
    b = last['body']
    print(f"\nLast (commit) data frame body[5:15] hex: {b[5:15].hex()}")
    print(f"  Starts with FFD8? {b[5]==0xff and b[6]==0xd8}")

# Show all WIN_ACKs
print('\n=== ALL WIN_ACK (cmd 0x1d, flag 0x80, RX) ===')
for e in events:
    if e['cmd'] == 0x1d and e['dir'] == 'RX' and e['flag'] == 0x80:
        b = e['body']
        if len(b) >= 8:
            seq = b[0]
            status = b[1]
            ws = (b[2] << 8) | b[3]
            noff = (b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]
            print(f"  seq={seq} status=0x{status:02x} winSize={ws} nextOff={noff}")

# Show the FULL pre-upload handshake: cmd 0x1b and its response
print('\n=== FILE META (cmd 0x1b) ===')
for e in events:
    if e['cmd'] == 0x1b:
        print(f"  {e['dir']} flag=0x{e['flag']:02x} body({e['blen']}): {e['body'].hex()}")
        if e['dir'] == 'TX':
            b = e['body']
            print(f"    seq={b[0]}, byte1=0x{b[1]:02x}, byte2=0x{b[2]:02x}")
            if len(b) >= 5:
                fsize = (b[3] << 8) | b[4]
                print(f"    fileSize={fsize}")
            if len(b) >= 9:
                token = b[5:9].hex()
                print(f"    token={token}")
            if len(b) > 9:
                tmpname = b[9:]
                print(f"    tmpName={tmpname.decode('ascii', errors='replace')}")

# Show the full upload session: cmd 0x21, 0x27, 0x1b
print('\n=== FULL SESSION SETUP ===')
for e in events:
    if e['cmd'] in (0x06, 0x21, 0x27, 0x1b, 0x03, 0x07):
        cmd_names = {0x06: 'AUTH_INIT', 0x21: 'SESSION_OPEN', 0x27: 'FILE_INIT', 0x1b: 'FILE_META',
                     0x03: 'QUERY_03', 0x07: 'QUERY_07'}
        name = cmd_names.get(e['cmd'], f"0x{e['cmd']:02x}")
        print(f"  {e['dir']} flag=0x{e['flag']:02x} {name:16s} body({e['blen']:3d}): {e['body'].hex()}")
