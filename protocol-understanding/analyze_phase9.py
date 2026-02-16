#!/usr/bin/env python3
"""
Analyze Phase 9-10 from btsnoop capture: window acks, re-sends, and completion.
"""
import struct

def parse_btsnoop(path):
    records = []
    with open(path, 'rb') as f:
        hdr = f.read(16)  # btsnoop header
        while True:
            rec_hdr = f.read(24)
            if len(rec_hdr) < 24:
                break
            orig_len, inc_len, flags, drops = struct.unpack('>IIII', rec_hdr[:16])
            ts = struct.unpack('>Q', rec_hdr[16:24])[0]
            data = f.read(inc_len)
            if len(data) < inc_len:
                break
            records.append((flags, ts, data))
    return records

def extract_att_values(records):
    """Extract ATT write/notify values with direction and handle."""
    result = []
    for flags, ts, data in records:
        if len(data) < 10:
            continue
        if data[0] != 0x02:  # HCI ACL
            continue
        acl_len = struct.unpack('<H', data[3:5])[0]
        if len(data) < 5 + acl_len:
            continue
        l2cap_cid = struct.unpack('<H', data[7:9])[0]
        if l2cap_cid != 0x0004:  # ATT
            continue
        att_opcode = data[9]
        att_payload = data[9:]
        direction = "TX" if (flags & 1) == 0 else "RX"
        att_handle = 0
        att_value = b''
        if att_opcode in (0x12, 0x52) and len(att_payload) >= 4:
            att_handle = struct.unpack('<H', att_payload[1:3])[0]
            att_value = att_payload[3:]
        elif att_opcode == 0x1B and len(att_payload) >= 4:
            att_handle = struct.unpack('<H', att_payload[1:3])[0]
            att_value = att_payload[3:]
        elif att_opcode == 0x13:  # Write Response (empty)
            continue
        else:
            continue
        if att_value:
            result.append({
                'dir': direction,
                'handle': att_handle,
                'value': att_value,
                'ts': ts,
                'opcode': att_opcode,
            })
    return result

def parse_e87(data):
    if len(data) < 8:
        return None
    if data[0] != 0xFE or data[1] != 0xDC or data[2] != 0xBA:
        return None
    if data[-1] != 0xEF:
        return None
    flag = data[3]
    cmd = data[4]
    length = (data[5] << 8) | data[6]
    body = data[7:-1]
    if len(body) != length:
        return None
    return {'flag': flag, 'cmd': cmd, 'length': length, 'body': body}

records = parse_btsnoop('cap.btsnoop')
att_values = extract_att_values(records)

print(f"Total ATT value transfers: {len(att_values)}")
print()

# Find start of data transfer (cmd 0x1b metadata)
start_idx = None
for i, v in enumerate(att_values):
    e = parse_e87(v['value'])
    if e and e['cmd'] == 0x1b:
        start_idx = i
        break

if start_idx is None:
    print("ERROR: Could not find cmd 0x1b")
    exit(1)

print("=" * 80)
print("PHASE 8 ONWARDS — ALL TRANSFERS")
print("=" * 80)
print()

data_frame_count = 0
first_data_ts = None
last_data_ts = None

for i in range(start_idx, len(att_values)):
    v = att_values[i]
    d = v['dir']
    raw = v['value']
    handle = v['handle']
    ts = v['ts']
    
    e = parse_e87(raw)
    if e:
        cmd = e['cmd']
        flag = e['flag']
        body = e['body']
        
        if cmd == 0x01 and flag == 0x80:
            # Data frame
            seq = body[0]
            subcmd = body[1]
            slot = body[2]
            crc = (body[3] << 8) | body[4]
            payload_len = len(body) - 5
            data_frame_count += 1
            if first_data_ts is None:
                first_data_ts = ts
            last_data_ts = ts
            print(f"[{i:3d}] {d} h=0x{handle:04x} DATA  #{data_frame_count:2d} seq=0x{seq:02x} sub=0x{subcmd:02x} slot={slot} crc=0x{crc:04x} payload={payload_len}b")
        elif cmd == 0x1d:
            body_hex = body.hex()
            print(f"[{i:3d}] {d} h=0x{handle:04x} WIN_ACK flag=0x{flag:02x} body({len(body)})={body_hex}")
            if len(body) >= 8:
                ack_seq = body[0]
                ack_status = body[1]
                win_size = (body[2] << 8) | body[3]
                offset = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
                print(f"        → seq=0x{ack_seq:02x} status=0x{ack_status:02x} winSize={win_size} offset={offset}")
        elif cmd == 0x1b:
            print(f"[{i:3d}] {d} h=0x{handle:04x} FILE_META flag=0x{flag:02x} body={body.hex()}")
        elif cmd == 0x20:
            print(f"[{i:3d}] {d} h=0x{handle:04x} FILE_COMPLETE flag=0x{flag:02x} body={body.hex()}")
        elif cmd == 0x1c:
            print(f"[{i:3d}] {d} h=0x{handle:04x} SESSION_CLOSE flag=0x{flag:02x} body={body.hex()}")
        elif cmd == 0x27:
            print(f"[{i:3d}] {d} h=0x{handle:04x} XFER_PARAMS flag=0x{flag:02x} body={body.hex()}")
        elif cmd == 0x21:
            print(f"[{i:3d}] {d} h=0x{handle:04x} BEGIN_UPLOAD flag=0x{flag:02x} body={body.hex()}")
        else:
            print(f"[{i:3d}] {d} h=0x{handle:04x} FRAME flag=0x{flag:02x} cmd=0x{cmd:02x} body({len(body)})={body[:20].hex()}")
    else:
        if len(raw) <= 40:
            print(f"[{i:3d}] {d} h=0x{handle:04x} RAW({len(raw)}): {raw.hex()}")
        else:
            print(f"[{i:3d}] {d} h=0x{handle:04x} RAW({len(raw)}): {raw[:32].hex()}...")

print()
print("=" * 80)
print(f"SUMMARY: {data_frame_count} data frames total")
if first_data_ts and last_data_ts:
    total_us = last_data_ts - first_data_ts
    print(f"Total transfer time: {total_us} µs = {total_us/1000:.1f} ms")
print("=" * 80)

# Now let's specifically look at window acks
print()
print("=== WINDOW ACKS IN DETAIL ===")
for i in range(start_idx, len(att_values)):
    v = att_values[i]
    e = parse_e87(v['value'])
    if e and e['cmd'] == 0x1d:
        body = e['body']
        d = v['dir']
        flag = e['flag']
        if len(body) >= 8:
            ack_seq = body[0]
            ack_status = body[1]
            win_size = (body[2] << 8) | body[3]
            offset = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
            print(f"  {d} flag=0x{flag:02x} seq=0x{ack_seq:02x} status=0x{ack_status:02x} winSize={win_size} offset={offset}")
        else:
            print(f"  {d} flag=0x{flag:02x} body={body.hex()}")

# Look for completion handshake
print()
print("=== COMPLETION HANDSHAKE ===")
for i in range(start_idx, len(att_values)):
    v = att_values[i]
    e = parse_e87(v['value'])
    if e and e['cmd'] in (0x20, 0x1c):
        d = v['dir']
        cmd_name = {0x20: 'FILE_COMPLETE', 0x1c: 'SESSION_CLOSE'}[e['cmd']]
        print(f"  [{i}] {d} {cmd_name} flag=0x{e['flag']:02x} body={e['body'].hex()}")
