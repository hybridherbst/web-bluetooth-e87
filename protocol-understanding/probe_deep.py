#!/usr/bin/env python3
"""Deep dive: check if 32 data frames is correct, or if some are JPEG artifacts.
Also look at window ack body details."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

# Window acks show: 
# WA0: 01 00 0f 50 00 00 01 ea  => 0f50 = 3920, 01ea = 490
# WA1: 02 00 0f 50 00 00 11 3a  => 113a = 4410
# WA2: 03 00 0f 50 00 00 20 8a  => 208a = 8330
# WA3: 04 00 0f 50 00 00 2f da  => 2fda = 12250
# WA4: 05 00 01 ea 00 00 00 00  => 01ea = 490, offset = 0

# Differences: 4410-490=3920, 8330-4410=3920, 12250-8330=3920
# 3920 = 8 * 490
# But 490 per chunk * 32 = 15680, not 7997

# Wait - maybe 490 is DATA per frame (not 492)?
# Each frame body is 495 bytes. body[0]=seq, body[1]=0x1D, body[2]=slot
# So payload = 495 - 3 = 492
# But window ack says 01ea = 490. Maybe seq+slot are 5 bytes of overhead?
# body = [seq(1), 0x1D(1), slot(1), crc?(2), payload(490)] = 495?

# Let me check if 490 * 8 = 3920 makes sense for each window
# And the offsets: WA0 offset=490, WA1=4410=490+3920, WA2=8330=490+3920*2, WA3=12250=490+3920*3
# Then after WA3: 12250 + 490 * 7 = 12250 + 3430 = 15680 (for 7 frames)
# Wait but last window has only 1 frame...

# Hmm. 7997 / 490 = 16.32 => 17 full frames (16 * 490 = 7840, remaining = 157)
# But we have 32 frames. That's way too many.

# Let me check if data IS duplicated - each chunk might be sent twice (once via each
# characteristic)?

# Actually let me check: are HALF of these frames RECEIVED (from device)?
# That would explain 32 = 16 sent + 16 received

# Look at surrounding HCI data to determine direction
# In pklg, type byte matters:
# type=0x00 = command (outgoing), type=0x01 = async data (outgoing), type=0x02 = incoming data

# Let me parse properly with pklg records
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'off': off + 13, 'len': rec_len - 9, 'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw):
        break

# Find records that contain FE DC BA 80 01
print("Records containing data frame headers (FE DC BA 80 01):")
for i, rec in enumerate(records):
    p = rec['payload']
    idx = p.find(b'\xFE\xDC\xBA\x80\x01')
    if idx >= 0 and idx + 7 < len(p):
        body_len = (p[idx+5] << 8) | p[idx+6]
        if body_len > 3 and body_len < 600:
            seq_b = p[idx+7] if idx+7 < len(p) else -1
            b1 = p[idx+8] if idx+8 < len(p) else -1
            slot = p[idx+9] if idx+9 < len(p) else -1
            direction = "OUT" if rec['type'] == 0x01 else ("IN" if rec['type'] == 0x02 else f"type={rec['type']}")
            print(f"  rec[{i}] type=0x{rec['type']:02x}({direction}) seq=0x{seq_b:02x} b1=0x{b1:02x} slot=0x{slot:02x} body_len={body_len} payload_off={idx}")

# Check FE DC BA 00 01 (flag=0x00 = device response)
print("\nRecords containing FE DC BA 00 01 (device response to cmd 0x01):")
for i, rec in enumerate(records):
    p = rec['payload']
    idx = p.find(b'\xFE\xDC\xBA\x00\x01')
    if idx >= 0 and idx + 7 < len(p):
        body_len = (p[idx+5] << 8) | p[idx+6]
        if body_len > 0 and body_len < 600:
            body_hex = ' '.join(f'{b:02x}' for b in p[idx+7:idx+7+min(body_len, 20)])
            direction = "OUT" if rec['type'] == 0x01 else ("IN" if rec['type'] == 0x02 else f"type={rec['type']}")
            print(f"  rec[{i}] type=0x{rec['type']:02x}({direction}) body_len={body_len} body: {body_hex}")

# Window ack offset analysis
wa_bodies = [
    bytes([0x01, 0x00, 0x0f, 0x50, 0x00, 0x00, 0x01, 0xea]),
    bytes([0x02, 0x00, 0x0f, 0x50, 0x00, 0x00, 0x11, 0x3a]),
    bytes([0x03, 0x00, 0x0f, 0x50, 0x00, 0x00, 0x20, 0x8a]),
    bytes([0x04, 0x00, 0x0f, 0x50, 0x00, 0x00, 0x2f, 0xda]),
    bytes([0x05, 0x00, 0x01, 0xea, 0x00, 0x00, 0x00, 0x00]),
]
print("\nWindow ack analysis:")
for i, wb in enumerate(wa_bodies):
    seq = wb[0]
    b1 = wb[1]
    win_size = (wb[2] << 8) | wb[3]
    zero = (wb[4] << 8) | wb[5]
    offset = (wb[6] << 8) | wb[7]
    print(f"  WA{i}: seq=0x{seq:02x} b1=0x{b1:02x} win_size=0x{win_size:04x}={win_size} zero=0x{zero:04x} offset=0x{offset:04x}={offset}")

# Let me also check: maybe offsets are LE not BE?
print("\nWindow ack analysis (LE offsets):")
for i, wb in enumerate(wa_bodies):
    seq = wb[0]
    win_size_be = (wb[2] << 8) | wb[3]
    win_size_le = (wb[3] << 8) | wb[2]
    offset_be = (wb[6] << 8) | wb[7]
    offset_le = struct.unpack_from('<H', wb, 6)[0]
    full_offset_be = struct.unpack_from('>I', wb, 4)[0]
    full_offset_le = struct.unpack_from('<I', wb, 4)[0]
    print(f"  WA{i}: win_BE={win_size_be} off_BE={offset_be}  |  win_LE={win_size_le} off_LE={offset_le}  |  fulloff_BE={full_offset_be} fulloff_LE={full_offset_le}")
