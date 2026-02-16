#!/usr/bin/env python3
"""
Analyze ALL AE01 writes (handle 0x0006) including both E87-framed and raw.
Also count AE02 notifications (0x0008).
The actual file data is likely sent as raw ATT writes, not E87-framed cmd 0x01.
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
        records.append({'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6})
        off += 4 + rec_len
        if off > len(raw):
            break
    return records

records = parse_pklg('/Users/herbst/git/bluetooth-tag/cap-extended.pklg')

# Separate E87-framed from raw writes on AE01 (0x0006)
# And also look at all handles used
handle_counts = {}
for r in records:
    if r['type'] not in (2, 3):
        continue
    p = r['payload']
    if len(p) < 12:
        continue
    att_op = p[8]
    att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
    direction = 'TX' if r['type'] == 2 else 'RX'
    key = (direction, att_handle, att_op)
    handle_counts[key] = handle_counts.get(key, 0) + 1

print("=== Handle/op usage summary ===")
for k in sorted(handle_counts.keys()):
    d, h, op = k
    op_names = {0x52: 'Write_NoRsp', 0x12: 'Write_Req', 0x1b: 'Notify', 0x1d: 'Indicate', 0x13: 'Write_Rsp'}
    oname = op_names.get(op, f'0x{op:02x}')
    print(f"  {d} handle=0x{h:04x} op={oname}: {handle_counts[k]} packets")

# Now trace the timeline of AE01 writes — separate E87 frames from raw data
print("\n=== AE01 write analysis (per-session) ===")

# Identify session boundaries from SESS_OPEN (0x21)
# For each session, count raw vs E87 writes
all_ae01_writes = []  # (ts, att_value, is_e87)
for r in records:
    if r['type'] != 2:  # TX only
        continue
    p = r['payload']
    if len(p) < 12:
        continue
    att_op = p[8]
    att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
    if att_handle != 0x0006:
        continue
    if att_op not in (0x52, 0x12):
        continue
    att_value = p[11:]
    is_e87 = len(att_value) >= 7 and att_value[0:3] == b'\xfe\xdc\xba' and att_value[-1] == 0xef
    all_ae01_writes.append({'ts': r['ts'], 'value': att_value, 'is_e87': is_e87})

# Find session boundaries (SESS_OPEN TX)
sess_starts = []
for w in all_ae01_writes:
    if w['is_e87']:
        flag = w['value'][3]
        cmd = w['value'][4]
        if cmd == 0x21:  # SESS_OPEN
            sess_starts.append(w['ts'])

print(f"Session start timestamps: {sess_starts}")

for s_idx, start_ts in enumerate(sess_starts):
    end_ts = sess_starts[s_idx + 1] if s_idx + 1 < len(sess_starts) else float('inf')
    raw_writes = []
    e87_writes = []
    for w in all_ae01_writes:
        if start_ts <= w['ts'] < end_ts:
            if w['is_e87']:
                e87_writes.append(w)
            else:
                raw_writes.append(w)
    
    print(f"\n--- Session {s_idx+1} (ts={start_ts:.3f}) ---")
    print(f"  E87-framed writes: {len(e87_writes)}")
    print(f"  Raw (non-E87) writes: {len(raw_writes)}")
    
    # Show E87 cmd breakdown
    cmd_counts = {}
    for w in e87_writes:
        cmd = w['value'][4]
        cmd_counts[cmd] = cmd_counts.get(cmd, 0) + 1
    names = {0x01: 'DATA', 0x03: 'Q03', 0x06: 'AUTH', 0x07: 'Q07',
             0x1b: 'FILE_META', 0x1c: 'SESS_CLOSE', 0x20: 'FILE_COMP',
             0x21: 'SESS_OPEN', 0x27: 'XFER_PAR'}
    for cmd, cnt in sorted(cmd_counts.items()):
        nm = names.get(cmd, f'0x{cmd:02x}')
        print(f"    {nm}: {cnt}")
    
    # Show raw write details
    total_raw_bytes = sum(len(w['value']) for w in raw_writes)
    print(f"  Total raw bytes: {total_raw_bytes}")
    if raw_writes:
        print(f"  First raw write ({len(raw_writes[0]['value'])} bytes): {raw_writes[0]['value'][:20].hex()}")
        print(f"  Last raw write ({len(raw_writes[-1]['value'])} bytes): {raw_writes[-1]['value'][:20].hex()}")
        
        # Check if raw writes have any structure (seq/slot/crc header?)
        w0 = raw_writes[0]['value']
        print(f"  First raw write full ({len(w0)} bytes): {w0.hex()}" if len(w0) <= 50 else f"  First raw write first 50: {w0[:50].hex()}")
