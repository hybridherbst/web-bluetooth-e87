#!/usr/bin/env python3
"""
Analyze capture Phase 9-10: window acks and completion.
Uses same pklg parser as compare_protocol.py but also extracts RX frames.
"""
import struct

CHUNK_SIZE = 490

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_sec = struct.unpack_from('<I', raw, off+4)[0]
    ts_usec = struct.unpack_from('<I', raw, off+8)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload, 'ts': ts_sec + ts_usec/1e6})
    off += 4 + rec_len
    if off > len(raw): break

# Reassemble L2CAP and extract FE-framed packets from BOTH TX and RX
current_tx = None
current_rx = None
all_fe_frames = []  # (direction, flag, cmd, body, ts)

for rec in records:
    if rec['type'] not in (2, 3):  # type 2=TX, type 3=RX
        continue
    p = rec['payload']
    if len(p) < 4:
        continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    pb_flags = (acl_hdr >> 12) & 0x0F
    is_tx = (rec['type'] == 2)
    current_ref = current_tx if is_tx else current_rx
    
    if pb_flags == 0x00:
        if len(p) < 8:
            continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        new_current = {'dir': 'TX' if is_tx else 'RX', 'data': bytearray(p[8:]), 'expected': l2cap_len, 'ts': rec['ts']}
        if is_tx:
            current_tx = new_current
        else:
            current_rx = new_current
        current_ref = new_current
    elif pb_flags == 0x01 and current_ref:
        current_ref['data'].extend(p[4:])
    else:
        continue
    
    if current_ref and len(current_ref['data']) >= current_ref['expected']:
        data = bytes(current_ref['data'][:current_ref['expected']])
        direction = current_ref['dir']
        ts = current_ref['ts']
        if is_tx:
            current_tx = None
        else:
            current_rx = None
        if len(data) < 3:
            continue
        att_val = data[3:]  # skip ATT header
        # Find FE DC BA in the ATT value
        for idx in range(len(att_val)):
            if (idx + 7 < len(att_val) and
                att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                flag = att_val[idx+3]
                cmd = att_val[idx+4]
                blen = (att_val[idx+5] << 8) | att_val[idx+6]
                end = idx + 7 + blen
                if end < len(att_val) and att_val[end] == 0xEF:
                    body = bytes(att_val[idx+7:end])
                    all_fe_frames.append((direction, flag, cmd, body, ts))
                break

# Also extract non-FE-framed notifications (auth, control)
# Re-parse to get those too
all_raw_values = []
current_tx = None
current_rx = None
for rec in records:
    if rec['type'] not in (2, 3):
        continue
    p = rec['payload']
    if len(p) < 4:
        continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    pb_flags = (acl_hdr >> 12) & 0x0F
    is_tx = (rec['type'] == 2)
    current_ref = current_tx if is_tx else current_rx
    
    if pb_flags == 0x00:
        if len(p) < 8:
            continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        new_current = {'dir': 'TX' if is_tx else 'RX', 'data': bytearray(p[8:]), 'expected': l2cap_len, 'ts': rec['ts']}
        if is_tx:
            current_tx = new_current
        else:
            current_rx = new_current
        current_ref = new_current
    elif pb_flags == 0x01 and current_ref:
        current_ref['data'].extend(p[4:])
    else:
        continue
    
    if current_ref and len(current_ref['data']) >= current_ref['expected']:
        data = bytes(current_ref['data'][:current_ref['expected']])
        direction = current_ref['dir']
        ts = current_ref['ts']
        if is_tx:
            current_tx = None
        else:
            current_rx = None
        if len(data) >= 3:
            att_val = data[3:]
            all_raw_values.append((direction, att_val, ts))


# Find cmd 0x1b (file metadata) — marks start of transfer
start_idx = None
for i, (d, flag, cmd, body, ts) in enumerate(all_fe_frames):
    if cmd == 0x1b and flag == 0xc0:
        start_idx = i
        break

if start_idx is None:
    print("ERROR: Could not find cmd 0x1b")
    exit(1)

print("=" * 80)
print("ALL FE FRAMES FROM PHASE 8 (cmd 0x1b) ONWARDS")
print("=" * 80)
print()

data_count = 0
for i in range(start_idx, len(all_fe_frames)):
    d, flag, cmd, body, ts = all_fe_frames[i]
    
    if cmd == 0x01 and flag == 0x80:
        seq = body[0]
        subcmd = body[1]
        slot = body[2]
        crc = (body[3] << 8) | body[4]
        payload_len = len(body) - 5
        data_count += 1
        print(f"  [{i:3d}] {d:2s} DATA  #{data_count:2d} seq=0x{seq:02x} sub=0x{subcmd:02x} slot={slot} crc=0x{crc:04x} data={payload_len}b  ts={ts:.6f}")
    elif cmd == 0x1d:
        print(f"  [{i:3d}] {d:2s} WIN_ACK flag=0x{flag:02x} body({len(body)})={body.hex()}")
        if len(body) >= 8:
            ack_seq = body[0]
            ack_status = body[1]
            win_size = (body[2] << 8) | body[3]
            offset = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
            print(f"           seq=0x{ack_seq:02x} status=0x{ack_status:02x} winSize={win_size} offset={offset}")
    elif cmd == 0x1b:
        print(f"  [{i:3d}] {d:2s} FILE_META flag=0x{flag:02x} body={body.hex()}")
    elif cmd == 0x20:
        print(f"  [{i:3d}] {d:2s} FILE_COMPLETE flag=0x{flag:02x} body({len(body)})={body.hex()}")
    elif cmd == 0x1c:
        print(f"  [{i:3d}] {d:2s} SESSION_CLOSE flag=0x{flag:02x} body({len(body)})={body.hex()}")
    elif cmd == 0x27:
        print(f"  [{i:3d}] {d:2s} XFER_PARAMS flag=0x{flag:02x} body={body.hex()}")
    elif cmd == 0x21:
        print(f"  [{i:3d}] {d:2s} BEGIN_UPLOAD flag=0x{flag:02x} body={body.hex()}")
    else:
        print(f"  [{i:3d}] {d:2s} FRAME flag=0x{flag:02x} cmd=0x{cmd:02x} body({len(body)})={body[:20].hex()}")

print()
print("=" * 80)
print(f"Total data frames: {data_count}")
print()

# Summarize window acks
print("=== WINDOW ACK SUMMARY ===")
for i in range(start_idx, len(all_fe_frames)):
    d, flag, cmd, body, ts = all_fe_frames[i]
    if cmd == 0x1d:
        if len(body) >= 8:
            ack_seq = body[0]
            status = body[1]
            win_size = (body[2] << 8) | body[3]
            offset = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
            print(f"  {d:2s} flag=0x{flag:02x} seq=0x{ack_seq:02x} status=0x{status:02x} winSize={win_size} nextOffset={offset}")
        else:
            print(f"  {d:2s} flag=0x{flag:02x} body={body.hex()}")

print()
print("=== COMPLETION HANDSHAKE ===")
for i in range(start_idx, len(all_fe_frames)):
    d, flag, cmd, body, ts = all_fe_frames[i]
    if cmd in (0x20, 0x1c):
        name = {0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE'}[cmd]
        print(f"  [{i}] {d:2s} {name} flag=0x{flag:02x} body({len(body)})={body.hex()}")
