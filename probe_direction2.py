#!/usr/bin/env python3
"""Analyze cmd 0x20 and 0x1C exchange, and the final window ack sequence."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'off': off + 13, 'len': rec_len - 9, 'type': ptype, 'payload': payload, 'ts': ts})
    off += 4 + rec_len
    if off > len(raw):
        break

# Show records around the end of data transfer
# Data frames end around rec 1761 (seq=0x25)
# Then completion should follow
print("Records 1750-1800:")
for rec in records[1750:1800]:
    p = rec['payload']
    direction = {0: 'CMD_OUT', 1: 'EVT_IN', 2: 'ACL_TX', 3: 'ACL_RX'}.get(rec['type'], f'type_{rec['type']}')
    
    # Check for FE DC BA pattern
    fe_info = ""
    for idx in range(len(p)):
        if idx + 7 < len(p) and p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            body_len = (p[idx+5] << 8) | p[idx+6]
            if body_len < 600:
                body = p[idx+7:idx+7+min(body_len, 50)]
                body_hex = ' '.join(f'{b:02x}' for b in body)
                fe_info = f" | FE frame: flag=0x{flag:02x} cmd=0x{cmd:02x} body_len={body_len} body: {body_hex}"
            break
    
    # Show ATT info
    att_info = ""
    if rec['type'] in (2, 3) and len(p) > 8:
        acl_hdr = struct.unpack_from('<H', p, 0)[0]
        acl_handle = acl_hdr & 0x0FFF
        acl_flags = (acl_hdr >> 12) & 0x0F
        if len(p) > 8:
            opcode = p[8]
            opcodes = {0x52: 'WriteWoR', 0x12: 'WriteReq', 0x13: 'WriteRsp', 0x1B: 'Notify', 0x1D: 'Indicate'}
            opname = opcodes.get(opcode, f'0x{opcode:02x}')
            if opcode in (0x52, 0x12, 0x1B, 0x1D) and len(p) > 10:
                att_handle = struct.unpack_from('<H', p, 9)[0]
                att_info = f" | ATT {opname} h=0x{att_handle:04x}"
            else:
                att_info = f" | ATT {opname}"
    
    data_hex = ' '.join(f'{b:02x}' for b in p[:20])
    print(f"  [{rec['idx']:4d}] {direction:8s} len={len(p):3d} | {data_hex}{att_info}{fe_info}")

# Now let's focus specifically on what happens after the last data frame
# The last data frame is seq=0x25 in rec 1761
# The last window ack (cmd 0x1D) should be somewhere around there

print("\n\n=== COMPLETE PROTOCOL SEQUENCE (FE-framed messages only) ===")
for i, rec in enumerate(records):
    p = rec['payload']
    direction = {0: 'CMD_OUT', 1: 'EVT_IN', 2: 'ACL_TX', 3: 'ACL_RX'}.get(rec['type'], f'type_{rec['type']}')
    
    for idx in range(len(p)):
        if idx + 7 < len(p) and p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            body_len = (p[idx+5] << 8) | p[idx+6]
            if body_len < 600 and cmd != 0x01:  # Skip data frames (too many)
                body = p[idx+7:idx+7+min(body_len, 50)]
                body_hex = ' '.join(f'{b:02x}' for b in body)
                flagname = "TX" if flag & 0xC0 else "RX"
                print(f"  [{i:4d}] {direction:8s} {flagname} cmd=0x{cmd:02x} flag=0x{flag:02x} body({body_len}): {body_hex}")
            elif cmd == 0x01:
                # Summarize data frames
                if idx + 9 < len(p):
                    seq = p[idx+7]
                    slot = p[idx+9]
                    print(f"  [{i:4d}] {direction:8s} DATA seq=0x{seq:02x} slot=0x{slot:02x} body_len={body_len}")
            break

# Check: the window ack (cmd 0x1D) direction
print("\n\n=== WINDOW ACKS (cmd 0x1D) with direction ===")
for i, rec in enumerate(records):
    p = rec['payload']
    direction = {0: 'CMD_OUT', 1: 'EVT_IN', 2: 'ACL_TX', 3: 'ACL_RX'}.get(rec['type'], f'type_{rec['type']}')
    for idx in range(len(p)):
        if idx + 7 < len(p) and p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            cmd = p[idx+4]
            flag = p[idx+3]
            if cmd == 0x1D:
                body_len = (p[idx+5] << 8) | p[idx+6]
                body = p[idx+7:idx+7+body_len]
                body_hex = ' '.join(f'{b:02x}' for b in body)
                print(f"  [{i:4d}] {direction:8s} flag=0x{flag:02x} body({body_len}): {body_hex}")
            break

# Check total data payload
# 490 per full frame, but what about overhead?
# Window ack says 01ea=490. WA offsets progress by 3920=8*490
# But the frame body has: [seq(1), 0x1D(1), slot(1), data(492)] = 495
# OR: [seq(1), 0x1D(1), slot(1), data(490)] = 493?
# Let me check: frame body_len is 495 for full frames
# If payload per frame is 490, then overhead = 495 - 490 = 5 bytes
# body = [seq(1), 0x1D(1), slot(1), ?(2), data(490)] = 495
# What are those 2 mystery bytes?

print("\n\n=== First data frame body hex (first 20 bytes) ===")
rec = records[1614]
p = rec['payload']
idx = p.find(b'\xFE\xDC\xBA\x80\x01')
body_start = idx + 7
print(f"Frame body bytes: {' '.join(f'{b:02x}' for b in p[body_start:body_start+20])}")
print(f"  byte 0 (seq): 0x{p[body_start]:02x}")
print(f"  byte 1 (cmd?): 0x{p[body_start+1]:02x}")
print(f"  byte 2 (slot): 0x{p[body_start+2]:02x}")
print(f"  bytes 3-4: 0x{p[body_start+3]:02x} 0x{p[body_start+4]:02x}")
print(f"  bytes 5+: {' '.join(f'{b:02x}' for b in p[body_start+5:body_start+15])}")

# Also check the SMALL frame (seq=0x24, body_len=462)
# It should be the last frame with actual file data
# Payload = 462 - 5 = 457 (if 5-byte overhead) or 462 - 3 = 459
# 31 * 490 + remainder = 7997 => remainder = 7997 - 31*490 = 7997 - 15190 = -7193 (NEGATIVE!)
# That can't be right. 
# Try: 15 * 490 + (462-5) = 7350 + 457 = 7807 (nope)
# Try: 16 * 490 + (462-5) = 7840 + 457 = 8297 (nope)

# Let me reconsider. Maybe the data is sent as 245 bytes per BLE write, 
# and each "frame" contains 2 BLE writes?

# Check: L2CAP len=506, but ACL MTU=251.
# L2CAP len=506 means the ATT PDU is 506 bytes
# ATT WriteWoR: opcode(1) + handle(2) + data = 506, so data = 503 bytes
# But frame header is 7 bytes (FE DC BA flag cmd len_hi len_lo)
# So: 503 - 7 = 496... + (EF terminator) = 495 body + 7 header + 1 terminator = 503
# Actually: FE DC BA [flag] [cmd] [len_hi] [len_lo] [body...] [EF]
# Total = 7 + body_len + 1 = 7 + 495 + 1 = 503
# ATT data = 503, ATT PDU = 503 + 3 (opcode+handle) = 506 ✓
# So body_len=495 means 495 bytes of body. With 3-byte header (seq, 0x1D, slot) that's 492 payload.
# But window ack says 490. So maybe 5-byte header?

# File size 7997 / 490 = 16.32 => need 17 frames
# 16 * 490 = 7840, remaining = 157 bytes
# Last frame payload = 157, body = 157 + 5 = 162? But we see body_len=462 for the short one.
# 462 - 5 = 457. 16*490+457 = 8297 ≠ 7997

# Try 492:
# 7997 / 492 = 16.25 => 17 frames
# 16*492 = 7872, remaining = 125
# 16*492+125 = 7997 ✓
# Short frame body = 125+3 = 128? But we see 462, not 128.

# I think the 32 data frames sending 15K+ data is REAL.
# Maybe the file on the device ends up being larger?
# Or maybe the window ack offsets tell the real story:
# WA0 offset=490, WA1=4410, WA2=8330, WA3=12250, WA4 offset=0 win=490
# Differences: 4410-490=3920, 8330-4410=3920, 12250-8330=3920
# After WA3: 8 more frames, then WA4 with win=490 (just 1 frame left)
# Total: 12250 + 3920 = 16170? And the last window has win=490
# Maybe total = 12250 + 490 = 12740? Nope, doesn't match 7997 either.
# OR: 490 is NOT the file offset, it's something else

# Let's be pragmatic: 32 frames, 31*492+459=15711
# Maybe the file is actually 15711 bytes and the metadata "7997" is wrong?
# Or maybe 7997 is not the file size.

# Let me re-read the metadata frame
print("\n=== METADATA FRAME (cmd 0x1b) ===")
for i, rec in enumerate(records):
    p = rec['payload']
    for idx in range(len(p)):
        if idx + 7 < len(p) and p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            if p[idx+4] == 0x1B:
                flag = p[idx+3]
                body_len = (p[idx+5] << 8) | p[idx+6]
                body = p[idx+7:idx+7+body_len]
                body_hex = ' '.join(f'{b:02x}' for b in body)
                print(f"  [{i}] flag=0x{flag:02x} body({body_len}): {body_hex}")
                # Parse: seq, 00, 00, size_LE16?, token, filename
                if flag == 0xC0:
                    seq = body[0]
                    sz_le16 = struct.unpack_from('<H', body, 3)[0]
                    sz_be16 = struct.unpack_from('>H', body, 3)[0]
                    sz_le32 = struct.unpack_from('<I', body, 3)[0] if len(body) > 6 else 0
                    sz_be32 = struct.unpack_from('>I', body, 3)[0] if len(body) > 6 else 0
                    sz2_le16 = struct.unpack_from('<H', body, 1)[0]
                    sz2_be16 = struct.unpack_from('>H', body, 1)[0]
                    print(f"    seq={seq}")
                    print(f"    body[1:3] LE16={sz2_le16} BE16={sz2_be16}")
                    print(f"    body[3:5] LE16={sz_le16} BE16={sz_be16}")
                    print(f"    body[3:7] LE32={sz_le32} BE32={sz_be32}")
                    # Full hex analysis
                    for j, b in enumerate(body):
                        if 0x20 <= b <= 0x7e:
                            print(f"    body[{j}] = 0x{b:02x} = {b:3d} = '{chr(b)}'")
                        else:
                            print(f"    body[{j}] = 0x{b:02x} = {b:3d}")
