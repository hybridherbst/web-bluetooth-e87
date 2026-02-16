#!/usr/bin/env python3
"""Analyze the EXACT completion handshake bytes in the capture - every byte matters."""
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
    if off > len(raw): break

# Find all FE frames for cmd 0x20, 0x1c, and the last 0x1d
print("=== COMPLETION HANDSHAKE (cmd 0x1c, 0x20, last 0x1d) ===\n")

events = []
for r in records:
    if r['type'] not in (2, 3): continue
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
                'raw_att': p[11:] if len(p) > 11 else p  # ATT value
            })
            break

# Find last WIN_ACK and everything after
last_1d_idx = None
for i, e in enumerate(events):
    if e['cmd'] == 0x1d and e['dir'] == 'RX':
        last_1d_idx = i

if last_1d_idx:
    print("Starting from last WIN_ACK:\n")
    for e in events[last_1d_idx:]:
        cmd_name = {0x1d: 'WIN_ACK', 0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE', 0x01: 'DATA'}.get(e['cmd'], f"cmd_0x{e['cmd']:02x}")
        print(f"  {e['dir']:2s}  flag=0x{e['flag']:02x}  {cmd_name:16s}  body({e['blen']:3d})= {e['body'].hex()}")
        print(f"      ATT value hex: {e['raw_att'].hex()}")
        print(f"      Trailer byte: 0x{e['trailer']:02x}" if e['trailer'] is not None else "      No trailer")
        
        # Decode body fields
        if e['cmd'] == 0x20:
            if e['dir'] == 'RX':
                print(f"      → Device FILE_COMPLETE: seq={e['body'][0] if len(e['body'])>=1 else '?'}")
            else:
                print(f"      → App response: status=0x{e['body'][0]:02x} seq=0x{e['body'][1]:02x}" if len(e['body'])>=2 else "")
                if len(e['body']) > 2:
                    path_bytes = e['body'][2:]
                    # Try UTF-16LE decode
                    try:
                        path_str = path_bytes.decode('utf-16-le').rstrip('\x00')
                        print(f"      → Path (UTF-16LE): '{path_str}'")
                    except:
                        print(f"      → Path bytes: {path_bytes.hex()}")
        elif e['cmd'] == 0x1c:
            if len(e['body']) >= 2:
                print(f"      → byte[0]=0x{e['body'][0]:02x} byte[1]=0x{e['body'][1]:02x}")
            if e['dir'] == 'RX':
                print(f"      → Device SESSION_CLOSE")
            else:
                print(f"      → App SESSION_CLOSE response")
        elif e['cmd'] == 0x1d:
            if len(e['body']) >= 8:
                seq = e['body'][0]
                status = e['body'][1]
                ws = (e['body'][2] << 8) | e['body'][3]
                noff = (e['body'][4] << 24) | (e['body'][5] << 16) | (e['body'][6] << 8) | e['body'][7]
                print(f"      → seq={seq} status=0x{status:02x} winSize={ws} nextOff={noff}")
        print()

# Also show the FULL raw FE frame bytes for each completion frame
print("\n=== RAW FE FRAME BYTES ===")
for e in events[last_1d_idx:]:
    cmd_name = {0x1d: 'WIN_ACK', 0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE', 0x01: 'DATA'}.get(e['cmd'], f"cmd_0x{e['cmd']:02x}")
    # Reconstruct the full FE frame
    frame = bytes([0xFE, 0xDC, 0xBA, e['flag'], e['cmd'], (e['blen']>>8)&0xff, e['blen']&0xff]) + e['body'] + (bytes([e['trailer']]) if e['trailer'] is not None else b'')
    print(f"  {e['dir']:2s} {cmd_name:16s}: {frame.hex()}")
