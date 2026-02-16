#!/usr/bin/env python3
"""
Deeper analysis of cap-extended.pklg — look at ALL E87 frames
in order, identify every cmd, track file boundaries.
"""
import struct

def parse_pklg(path):
    raw = open(path, 'rb').read()
    off = 0
    records = []
    while off + 13 <= len(raw):
        rec_len = struct.unpack_from('<I', raw, off)[0]
        ts_secs = struct.unpack_from('<I', raw, off+4)[0]
        ts_usecs = struct.unpack_from('<I', raw, off+8)[0]
        ptype = raw[off + 12]
        payload = raw[off + 13:off + 13 + rec_len - 9]
        records.append({'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6, 'raw_off': off})
        off += 4 + rec_len
        if off > len(raw):
            break
    return records

records = parse_pklg('/Users/herbst/git/bluetooth-tag/cap-extended.pklg')

# Print ALL E87 frames with cmd types, focusing on all AE01/AE02 traffic
session_start_ts = None
frame_count = 0
data_chunks_total = 0
file_meta_count = 0
win_ack_count = 0

print("=== ALL E87 COMMANDS IN ORDER (non-data) ===")
print(f"{'ts':>14} {'dir':>3} {'flag':>4} {'cmd':>6} {'blen':>5} {'body_hex'}")
print("-" * 100)

for r in records:
    if r['type'] not in (2, 3):
        continue
    p = r['payload']
    if len(p) < 12:
        continue
    att_op = p[8]
    att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
    direction = 'TX' if r['type'] == 2 else 'RX'
    
    if att_handle not in (0x0006, 0x0008):
        continue
    att_value = p[11:]
    if len(att_value) < 7:
        continue
    if att_value[0:3] != b'\xfe\xdc\xba' or att_value[-1] != 0xef:
        continue
    
    flag = att_value[3]
    cmd = att_value[4]
    blen = (att_value[5] << 8) | att_value[6]
    body = att_value[7:-1]
    
    # Count data chunks
    if cmd == 0x01:
        data_chunks_total += 1
        continue  # Don't print every data chunk
    
    if cmd == 0x1d:
        win_ack_count += 1
        # Print WIN_ACKs with meaningful info
        if len(body) >= 8:
            ack_seq = body[0]
            status = body[1]
            ws = (body[2] << 8) | body[3]
            noff = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
            if ws == 0 and noff == 0:
                print(f"{r['ts']:14.3f} {direction:>3} 0x{flag:02x} WIN_ACK {blen:>5} ackSeq={ack_seq} st={status} ws=0 noff=0 (COMMIT/DONE)")
            elif win_ack_count <= 5:
                print(f"{r['ts']:14.3f} {direction:>3} 0x{flag:02x} WIN_ACK {blen:>5} ackSeq={ack_seq} st={status} ws={ws} noff={noff}")
        continue
    
    # Name commands
    names = {
        0x03: 'Q03', 0x06: 'AUTH_FLAG', 0x07: 'Q07',
        0x1b: 'FILE_META', 0x1c: 'SESS_CLOSE', 0x1d: 'WIN_ACK',
        0x20: 'FILE_COMP', 0x21: 'SESS_OPEN', 0x27: 'XFER_PAR',
    }
    nm = names.get(cmd, f'cmd_0x{cmd:02x}')
    
    if cmd == 0x1b:
        file_meta_count += 1
    
    bodyh = body.hex() if len(body) < 60 else body[:60].hex() + '...'
    print(f"{r['ts']:14.3f} {direction:>3} 0x{flag:02x} {nm:>12} {blen:>5} {bodyh}")

print(f"\n--- Total data chunks (cmd 0x01): {data_chunks_total}")
print(f"--- Total WIN_ACKs: {win_ack_count}")
print(f"--- Total FILE_META: {file_meta_count}")
