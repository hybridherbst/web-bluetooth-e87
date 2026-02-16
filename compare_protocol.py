#!/usr/bin/env python3
"""
Byte-for-byte comparison of what our app sends vs what the capture shows.
Simulates the EXACT JS code path for the ground-truth captured_image.jpg.
"""
import struct

CHUNK_SIZE = 490

def crc16xmodem(data):
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def build_e87_frame(flag, cmd, body):
    out = bytearray(3 + 1 + 1 + 2 + len(body) + 1)
    out[0] = 0xFE
    out[1] = 0xDC
    out[2] = 0xBA
    out[3] = flag & 0xFF
    out[4] = cmd & 0xFF
    out[5] = (len(body) >> 8) & 0xFF
    out[6] = len(body) & 0xFF
    out[7:7+len(body)] = body
    out[-1] = 0xEF
    return bytes(out)

# ─── Parse ALL FE-framed TX packets from the capture ───
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

# Reassemble L2CAP and extract FE-framed packets from TX (type=2) records
current = None
capture_fe_frames = []  # (flag, cmd, body_bytes, full_frame_bytes, timestamp)

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
    else: continue
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        direction = current['dir']
        ts = current['ts']
        current = None
        if len(data) < 3 or direction != 2: continue  # TX only
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
                    full_frame = bytes(att_val[idx:end+1])
                    capture_fe_frames.append((flag, cmd, body, full_frame, ts))
                break

# Separate data frames (flag=0x80, cmd=0x01) and command frames
capture_cmd_frames = []
capture_data_frames = []
for flag, cmd, body, full, ts in capture_fe_frames:
    if flag == 0x80 and cmd == 0x01:
        capture_data_frames.append((flag, cmd, body, full, ts))
    else:
        capture_cmd_frames.append((flag, cmd, body, full, ts))

print(f"Capture: {len(capture_fe_frames)} total FE frames, {len(capture_cmd_frames)} commands, {len(capture_data_frames)} data")
print()

# ─── Print ALL command frames for reference ───
print("=== COMMAND FRAMES (non-data) ===")
for i, (flag, cmd, body, full, ts) in enumerate(capture_cmd_frames):
    print(f"  [{i:2d}] flag=0x{flag:02x} cmd=0x{cmd:02x} body({len(body)}): {body[:20].hex()}")
print()

# ─── Now simulate what our JS code sends ───
jpeg = open('/Users/herbst/git/bluetooth-tag/captured_image.jpg', 'rb').read()
print(f"JPEG: {len(jpeg)} bytes, starts with {jpeg[:4].hex()}")
print()

# Our JS code (Phase 9):
# seqCounter starts at some value after phases 1-8
# From the capture, the first data frame has seq=0x06 in body[0]
# Let's check what seq the capture uses
print("=== CAPTURE DATA FRAMES: header analysis ===")
for i, (flag, cmd, body, full, ts) in enumerate(capture_data_frames):
    seq = body[0]
    xm_op = body[1]
    slot = body[2]
    crc_hi = body[3]
    crc_lo = body[4]
    crc = (crc_hi << 8) | crc_lo
    file_data = body[5:]
    print(f"  [{i:2d}] seq=0x{seq:02x} xm_op=0x{xm_op:02x} slot={slot} crc=0x{crc:04x} data_len={len(file_data)}")

print()

# ─── Compare data frame by data frame ───
print("=== BYTE-FOR-BYTE COMPARISON: Our code vs Capture ===")
print()

# Our code starts seq at seqCounter (= 0x05 after phases 1-7 increment it 5 times, but 
# the capture shows first data frame seq=0x06, so seqCounter must be 0x06)
# Let's just read it from the capture's first data frame
cap_start_seq = capture_data_frames[0][2][0]
print(f"Capture's first data seq: 0x{cap_start_seq:02x}")
print()

seq = cap_start_seq
slot = 0
all_match = True

for i in range(len(capture_data_frames)):
    cap_flag, cap_cmd, cap_body, cap_full, cap_ts = capture_data_frames[i]
    
    # What our code would build for chunk i
    offset = i * CHUNK_SIZE
    payload = jpeg[offset:offset + CHUNK_SIZE]
    crc = crc16xmodem(payload)
    
    # Build the body: [seq, 0x1d, slot, crc_hi, crc_lo, ...data]
    our_body = bytearray(5 + len(payload))
    our_body[0] = seq & 0xFF
    our_body[1] = 0x1D
    our_body[2] = slot & 0xFF
    our_body[3] = (crc >> 8) & 0xFF
    our_body[4] = crc & 0xFF
    our_body[5:] = payload
    
    # Build the full FE frame
    our_frame = build_e87_frame(0x80, 0x01, bytes(our_body))
    
    # Compare
    body_match = (bytes(our_body) == cap_body)
    frame_match = (our_frame == cap_full)
    
    cap_seq = cap_body[0]
    cap_xm = cap_body[1] 
    cap_slot = cap_body[2]
    cap_crc = (cap_body[3] << 8) | cap_body[4]
    cap_data = cap_body[5:]
    
    our_crc = crc
    data_match = (payload == cap_data)
    
    status = "✓" if frame_match else "✗"
    
    if not frame_match:
        all_match = False
        diffs = []
        if seq & 0xFF != cap_seq:
            diffs.append(f"seq: ours=0x{seq&0xFF:02x} cap=0x{cap_seq:02x}")
        if 0x1D != cap_xm:
            diffs.append(f"xm_op: ours=0x1d cap=0x{cap_xm:02x}")
        if slot & 0xFF != cap_slot:
            diffs.append(f"slot: ours={slot&0xFF} cap={cap_slot}")
        if our_crc != cap_crc:
            diffs.append(f"crc: ours=0x{our_crc:04x} cap=0x{cap_crc:04x}")
        if not data_match:
            # Find first difference
            for j in range(min(len(payload), len(cap_data))):
                if payload[j] != cap_data[j]:
                    diffs.append(f"data differs at byte {j}: ours=0x{payload[j]:02x} cap=0x{cap_data[j]:02x}")
                    break
            if len(payload) != len(cap_data):
                diffs.append(f"data_len: ours={len(payload)} cap={len(cap_data)}")
        print(f"  {status} frame {i:2d}: {', '.join(diffs)}")
    else:
        print(f"  {status} frame {i:2d}: PERFECT MATCH (seq=0x{cap_seq:02x} slot={cap_slot} crc=0x{cap_crc:04x} len={len(cap_data)})")
    
    seq = (seq + 1) & 0xFF
    slot = (slot + 1) & 0x07

print()
if all_match:
    print("✓✓✓ ALL DATA FRAMES MATCH PERFECTLY! Sequential ordering is CORRECT!")
else:
    print("✗ Some frames don't match. See differences above.")
    
    # Also check if capture data is actually rotated
    print()
    print("=== CHECKING IF CAPTURE DATA IS A ROTATION OF OUR JPEG ===")
    cap_stream = b''.join(body[5:] for _, _, body, _, _ in capture_data_frames)
    print(f"Capture data stream: {len(cap_stream)} bytes")
    print(f"Our JPEG:            {len(jpeg)} bytes")
    print(f"Capture starts with: {cap_stream[:8].hex()}")
    print(f"JPEG starts with:    {jpeg[:8].hex()}")
    
    # Check if the capture stream is found inside jpeg+jpeg (rotation test)
    doubled = jpeg + jpeg
    pos = doubled.find(cap_stream[:CHUNK_SIZE])
    if pos >= 0:
        print(f"Capture chunk 0 data found in JPEG at offset {pos}")
        print(f"This means the capture data starts at JPEG offset {pos}")
        if pos == 0:
            print("→ Data is NOT rotated (starts at offset 0)")
        else:
            print(f"→ Data IS rotated by {pos} bytes")
            # Verify full rotation
            rotated = jpeg[pos:] + jpeg[:pos]
            if rotated == cap_stream:
                print(f"→ CONFIRMED: capture = jpeg[{pos}:] + jpeg[:{pos}]")
            else:
                # Check partial match
                match_len = 0
                for k in range(min(len(rotated), len(cap_stream))):
                    if rotated[k] == cap_stream[k]:
                        match_len += 1
                    else:
                        break
                print(f"→ Rotation hypothesis: first {match_len} bytes match, diverges at byte {match_len}")
    else:
        print("Capture chunk 0 NOT found in doubled JPEG - not a simple rotation")

# ─── Also compare metadata (cmd 0x1b) ───
print()
print("=== CMD 0x1B (metadata) ANALYSIS ===")
for flag, cmd, body, full, ts in capture_cmd_frames:
    if cmd == 0x1B and flag == 0xC0:
        print(f"  Capture cmd 0x1b body ({len(body)} bytes): {body.hex()}")
        print(f"    byte[0] (seq): 0x{body[0]:02x}")
        print(f"    byte[1-2]:     0x{body[1]:02x} 0x{body[2]:02x}")
        size_be16 = (body[3] << 8) | body[4]
        print(f"    byte[3-4] (size BE16): {size_be16} (0x{size_be16:04x})")
        print(f"    JPEG actual size:      {len(jpeg)} (0x{len(jpeg):04x})")
        print(f"    size match: {size_be16 == (len(jpeg) & 0xFFFF)}")
        print(f"    byte[5-8] (token): {body[5:9].hex()}")
        print(f"    byte[9:-1] (name): {body[9:-1].hex()} = '{body[9:-1].decode('ascii', errors='replace')}'")
        print(f"    byte[-1]:  0x{body[-1]:02x}")
