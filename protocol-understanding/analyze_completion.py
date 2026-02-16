#!/usr/bin/env python3
"""
Analyze the packet capture's Phase 9 data transfer and Phase 10 completion
to understand window ack protocol and completion handshake exactly.
"""
import struct

def parse_pklg(path):
    frames = []
    with open(path, 'rb') as f:
        hdr = f.read(4)  # pklg header
        while True:
            rec_hdr = f.read(9)
            if len(rec_hdr) < 9:
                break
            rec_len = struct.unpack('>I', rec_hdr[:4])[0]
            payload_len = rec_len - 9
            if payload_len <= 0:
                continue
            rec_type = rec_hdr[4]
            ts = struct.unpack('>I', rec_hdr[5:9])[0]
            payload = f.read(payload_len)
            if len(payload) < payload_len:
                break
            frames.append({
                'type': rec_type,
                'ts': ts,
                'data': payload,
                'direction': 'TX' if rec_type == 0x00 else 'RX'
            })
    return frames

def parse_e87_frame(data):
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

frames = parse_pklg('cap.pklg')

# Find all E87 data frames (cmd 0x01) and window acks (cmd 0x1d)
# and completion frames (cmd 0x20, 0x1c)
print("=== ALL FRAMES FROM PHASE 8 ONWARDS ===")
print()

# Find first cmd 0x1b (file metadata) to mark start
phase8_idx = None
for i, f in enumerate(frames):
    e = parse_e87_frame(f['data'])
    if e and e['cmd'] == 0x1b:
        phase8_idx = i
        break

if phase8_idx is None:
    print("ERROR: Could not find cmd 0x1b")
    exit(1)

print(f"Phase 8 starts at frame index {phase8_idx}")
print()

# Print everything from phase 8 to end
for i in range(phase8_idx, len(frames)):
    f = frames[i]
    d = f['direction']
    raw = f['data']
    
    e = parse_e87_frame(raw)
    if e:
        cmd = e['cmd']
        flag = e['flag']
        body = e['body']
        body_hex = body[:32].hex()
        
        if cmd == 0x01 and flag == 0x80:
            # Data frame
            seq = body[0]
            subcmd = body[1]
            slot = body[2]
            crc_hi = body[3]
            crc_lo = body[4]
            payload_len = len(body) - 5
            print(f"[{i:3d}] {d} DATA  seq=0x{seq:02x} subcmd=0x{subcmd:02x} slot={slot} crc=0x{crc_hi:02x}{crc_lo:02x} payload={payload_len}b")
        elif cmd == 0x1d:
            # Window ack
            print(f"[{i:3d}] {d} WIN_ACK flag=0x{flag:02x} cmd=0x{cmd:02x} body({len(body)})={body.hex()}")
            if len(body) >= 8:
                ack_seq = body[0]
                ack_status = body[1]
                win_size = (body[2] << 8) | body[3]
                offset = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
                print(f"        → seq=0x{ack_seq:02x} status=0x{ack_status:02x} winSize={win_size} offset={offset}")
        elif cmd == 0x1b:
            print(f"[{i:3d}] {d} FILE_META flag=0x{flag:02x} body({len(body)})={body.hex()}")
        elif cmd == 0x20:
            print(f"[{i:3d}] {d} FILE_COMPLETE flag=0x{flag:02x} body({len(body)})={body.hex()}")
        elif cmd == 0x1c:
            print(f"[{i:3d}] {d} SESSION_CLOSE flag=0x{flag:02x} body({len(body)})={body.hex()}")
        elif cmd == 0x27:
            print(f"[{i:3d}] {d} XFER_PARAMS flag=0x{flag:02x} body({len(body)})={body.hex()}")
        elif cmd == 0x21:
            print(f"[{i:3d}] {d} BEGIN_UPLOAD flag=0x{flag:02x} body({len(body)})={body.hex()}")
        else:
            print(f"[{i:3d}] {d} FRAME flag=0x{flag:02x} cmd=0x{cmd:02x} body({len(body)})={body_hex}")
    else:
        # Non-E87 frame
        if len(raw) <= 32:
            print(f"[{i:3d}] {d} RAW({len(raw)}): {raw.hex()}")
        else:
            print(f"[{i:3d}] {d} RAW({len(raw)}): {raw[:32].hex()}...")

print()
print("=== SUMMARY: WINDOW ACKS ===")
for i in range(phase8_idx, len(frames)):
    f = frames[i]
    e = parse_e87_frame(f['data'])
    if e and e['cmd'] == 0x1d:
        body = e['body']
        d = f['direction']
        if len(body) >= 8:
            ack_seq = body[0]
            ack_status = body[1]
            win_size = (body[2] << 8) | body[3]
            offset = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
            print(f"  {d} WIN_ACK seq=0x{ack_seq:02x} status=0x{ack_status:02x} winSize={win_size} offset={offset}")
        else:
            print(f"  {d} WIN_ACK body={body.hex()}")

print()
print("=== TIMING BETWEEN DATA FRAMES ===")
data_frames = []
for i in range(phase8_idx, len(frames)):
    f = frames[i]
    e = parse_e87_frame(f['data'])
    if e and e['cmd'] == 0x01 and e['flag'] == 0x80 and f['direction'] == 'TX':
        data_frames.append((i, f['ts']))

for j in range(1, len(data_frames)):
    delta = data_frames[j][1] - data_frames[j-1][1]
    print(f"  frame {j}: delta={delta} ticks from previous")

print()
print("=== CHECKING: DO WINDOW ACKS ARRIVE BETWEEN DATA FRAMES? ===")
data_frame_indices = set(idx for idx, _ in data_frames)
for i in range(phase8_idx, len(frames)):
    f = frames[i]
    e = parse_e87_frame(f['data'])
    if e and e['cmd'] == 0x1d:
        # Find surrounding data frames
        prev_data = max((idx for idx in data_frame_indices if idx < i), default=None)
        next_data = min((idx for idx in data_frame_indices if idx > i), default=None)
        body = e['body']
        print(f"  WIN_ACK at index {i} ({f['direction']}), between data frames {prev_data} and {next_data}, body={body.hex()}")
