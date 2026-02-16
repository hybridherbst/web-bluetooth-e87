#!/usr/bin/env python3
"""Check what's really in each data frame - are the payloads unique or repeated?"""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'len': rec_len - 9, 'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw):
        break

# For each data frame, extract the first few bytes of payload after the header
# Data frames are in specific records, spanning multiple BLE packets
# The FE DC BA header starts at payload offset 11 (after ACL(4) + L2CAP(4) + ATT_opcode(1) + ATT_handle(2))
# Then: FE(1) DC(1) BA(1) flag(1) cmd(1) len_hi(1) len_lo(1) = 7 bytes
# Body starts at offset 11+7 = 18

data_frames = []
for i, rec in enumerate(records):
    p = rec['payload']
    if rec['type'] != 0x02:  # Only outgoing ACL
        continue
    idx = p.find(b'\xFE\xDC\xBA\x80\x01')
    if idx < 0:
        continue
    body_len = (p[idx+5] << 8) | p[idx+6]
    if body_len < 3 or body_len > 600:
        continue
    
    # Body starts at idx+7
    body_start = idx + 7
    body_available = len(p) - body_start
    body_preview = p[body_start:body_start + min(10, body_available)]
    
    seq = body_preview[0]
    subcmd = body_preview[1]
    slot = body_preview[2]
    
    if subcmd != 0x1D:
        continue
    
    # First 10 bytes of actual data (after seq, 0x1D, slot)
    data_preview = p[body_start+3:body_start+13]
    data_hex = ' '.join(f'{b:02x}' for b in data_preview)
    
    data_frames.append({
        'rec': i, 'seq': seq, 'slot': slot, 'body_len': body_len,
        'data_start': data_preview
    })
    
    print(f"Frame seq=0x{seq:02x} slot={slot} body_len={body_len} data[0:10]: {data_hex}")

# Check if frame with seq=0x25 contains JPEG header
print(f"\n--- Last frame (seq=0x25) details ---")
rec = records[1761]
p = rec['payload']
idx = p.find(b'\xFE\xDC\xBA\x80\x01')
body_start = idx + 7
body_hex = ' '.join(f'{b:02x}' for b in p[body_start:body_start+30])
print(f"Body first 30 bytes: {body_hex}")
# Look for JPEG markers in the data
jpeg_idx = p.find(b'\xff\xd8\xff')
if jpeg_idx >= 0:
    print(f"JPEG header found at payload offset {jpeg_idx} (relative to body: {jpeg_idx - body_start})")

# Check the small frame (seq=0x24, body_len=462)
print(f"\n--- Short frame (seq=0x24) details ---")
rec = records[1751]
p = rec['payload']
idx = p.find(b'\xFE\xDC\xBA\x80\x01')
body_start = idx + 7
body_len = (p[idx+5] << 8) | p[idx+6]
print(f"Body len = {body_len}")
body_hex = ' '.join(f'{b:02x}' for b in p[body_start:body_start+30])
print(f"Body first 30 bytes: {body_hex}")

# Check the ACTUAL file data: seq 0x06 data should start with the beginning of the file
# If 490 bytes per frame and 7997 total:
#   Frame 0x06: offset 0-489
#   Frame 0x07: offset 490-979
# etc.
# If 492 bytes per frame:
#   Frame 0x06: offset 0-491
#   Frame 0x07: offset 492-983
# etc.

# Let me reconstruct what payload looks like
# We need ALL the bytes from each frame's body after (seq, 0x1D, slot)
# But the frame body spans multiple BLE packets!

# Each BLE ATT write is max 251 bytes (ACL MTU)
# ATT Write Without Response: opcode(1) + handle(2) + data = 251 => data = 248
# L2CAP: len(2) + CID(2) + ATT = 4 + 251 = 255... wait
# Record len = 255 = ACL_header(4) + L2CAP(varies) + ATT(varies)
# First fragment: ACL(4) + L2CAP_header(4) + ATT_opcode(1) + handle(2) + data = 4+4+3+data=11+data
# With record len 255: data = 244 bytes
# But the frame starts: FE(7 header) + body(495) + EF(1) = 503 total ATT data
# 503 - 244 = 259 bytes remaining for continuation packets

# Actually L2CAP length is 506 (0x01fa): L2CAP len = ATT PDU length = 1 + 2 + 503 = 506
# So total ATT data = 503 bytes

# For a 255-byte record:
# ACL header(4) + L2CAP header(4) + ATT data = 255 => ATT data = 247
# But L2CAP header only in first fragment
# First fragment: 4 + 4 + 247 = 255, ATT data in first frag = 247
# ATT: opcode(1) + handle(2) + FE_header(7) + body_start = 247
# FE data in first frag = 247 - 3 = 244
# FE header(7) + body_start = 244 => body bytes in first = 244 - 7 = 237
# Wait that's not right, let me count from the actual data

print(f"\n--- Reconstructing first data frame from multiple BLE records ---")
# Record 1614 is the first BLE packet of frame seq=0x06
# Records 1615, 1616 should be continuations (ACL continuation fragments)

# Actually let me check records 1614, 1615, 1616
for r_idx in range(1614, 1618):
    rec = records[r_idx]
    p = rec['payload']
    direction = {0: 'CMD', 1: 'EVT', 2: 'TX', 3: 'RX'}.get(rec['type'], '?')
    acl_handle = struct.unpack_from('<H', p, 0)[0] & 0x0FFF if len(p) > 2 else 0
    acl_flags = (struct.unpack_from('<H', p, 0)[0] >> 12) & 0xF if len(p) > 2 else 0
    data_hex = ' '.join(f'{b:02x}' for b in p[:20])
    print(f"  [{r_idx}] {direction} len={len(p)} ACL_handle=0x{acl_handle:03x} flags=0x{acl_flags:x}: {data_hex}")

# acl_flags: 0x0 = first L2CAP fragment, 0x1 = continuation
# So let me find all fragments for the first data frame
# and reconstruct the full ATT data

first_frame_data = bytearray()
rec = records[1614]
p = rec['payload']
# First fragment: skip ACL(4) + L2CAP(4) + ATT opcode(1) + ATT handle(2) = 11
first_frame_data.extend(p[11:])
print(f"  First fragment contributes {len(p)-11} bytes")

# Look for continuation fragments (flags=0x1)
for r_idx in range(1615, 1620):
    rec = records[r_idx]
    if rec['type'] != 0x02:
        continue
    p = rec['payload']
    if len(p) < 4:
        continue
    acl_flags = (struct.unpack_from('<H', p, 0)[0] >> 12) & 0xF
    if acl_flags == 0x1:
        # Continuation: skip ACL header(4)
        first_frame_data.extend(p[4:])
        print(f"  Continuation [{r_idx}] contributes {len(p)-4} bytes")
    elif acl_flags == 0x0:
        break  # New L2CAP PDU

print(f"\nReconstructed first frame total ATT data: {len(first_frame_data)} bytes")
print(f"Expected: FE(7) + body(495) + EF(1) = 503")
# First 7 bytes should be FE DC BA 80 01 01 EF
print(f"First 10 bytes: {' '.join(f'{b:02x}' for b in first_frame_data[:10])}")
# body starts at byte 7
body = first_frame_data[7:7+495]
print(f"Body[0:3] = seq=0x{body[0]:02x} subcmd=0x{body[1]:02x} slot=0x{body[2]:02x}")
print(f"Body data (after header) first 20 bytes: {' '.join(f'{b:02x}' for b in body[3:23])}")

# Check if byte 502 is 0xEF (terminator)
if len(first_frame_data) > 502:
    print(f"Byte 502 (EF terminator?): 0x{first_frame_data[502]:02x}")

# Now check if there's ANY pattern - maybe the 0xC0 0xB8 at body[3:5] is a 2-byte CRC
# If overhead is 5 (seq + 0x1D + slot + crc16), payload = 490
# 490 * 16 + short = 7840 + ?
# Short frame body_len = 462 => payload = 462 - 5 = 457
# Total = 490 * 15 + 457 = 7350 + 457 = 7807 (nope)
# With 16: 490*16+457 = 8297 (nope)

# Actually maybe each frame's data[0:2] (after seq, 0x1D, slot) is a 2-byte big-endian
# offset into the file?
# Frame 0x06 data starts: C0 B8
# 0xC0B8 = 49336 — that's WAY too big for a file offset

# Maybe NOT offset. Let me check frame 0x07's data[0:2]
print(f"\n--- Frame offsets check ---")
for i, rec_idx in enumerate([1614, 1617, 1620, 1623, 1626, 1631]):
    rec = records[rec_idx]
    p = rec['payload']
    idx = p.find(b'\xFE\xDC\xBA\x80\x01')
    body_start = idx + 7
    seq = p[body_start]
    d0 = p[body_start+3]
    d1 = p[body_start+4]
    d0d1_be = (d0 << 8) | d1
    d0d1_le = (d1 << 8) | d0
    print(f"  Frame seq=0x{seq:02x}: data[0:2] = 0x{d0:02x} 0x{d1:02x} BE={d0d1_be} LE={d0d1_le}")
