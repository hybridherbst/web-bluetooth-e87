#!/usr/bin/env python3
"""Reconstruct the complete data transfer sequence by parsing ALL BLE records
for data frames, handling multi-record fragmentation."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'len': rec_len - 9, 'type': ptype, 'payload': payload, 'ts': ts})
    off += 4 + rec_len
    if off > len(raw):
        break

# Reconstruct L2CAP frames from ACL fragments
# ACL header: handle(2) + L2CAP length(2)
# First fragment has flag=0x00 (PB=00), continuation has flag=0x10 (PB=01)

assembled_frames = []
current_frame = None

for rec in records:
    if rec['type'] not in (2, 3):
        continue
    p = rec['payload']
    if len(p) < 4:
        continue
    
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    handle = acl_hdr & 0x0FFF
    flags = (acl_hdr >> 12) & 0x0F
    acl_data_len = struct.unpack_from('<H', p, 2)[0]
    
    if flags == 0x00:  # First fragment (PB=00)
        if len(p) < 8:
            continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        l2cap_cid = struct.unpack_from('<H', p, 6)[0]
        current_frame = {
            'direction': 'TX' if rec['type'] == 2 else 'RX',
            'rec_idx': rec['idx'],
            'l2cap_len': l2cap_len,
            'cid': l2cap_cid,
            'data': bytearray(p[8:]),  # ATT data starts at offset 8
            'expected': l2cap_len
        }
    elif flags == 0x01 and current_frame:  # Continuation (PB=01)
        current_frame['data'].extend(p[4:])
    else:
        continue
    
    if current_frame and len(current_frame['data']) >= current_frame['expected']:
        data = bytes(current_frame['data'][:current_frame['expected']])
        # Check if this is an ATT write (opcode 0x52=WriteWoR or 0x12=WriteReq)
        # or ATT notification (0x1B) with FE DC BA frame inside
        if len(data) >= 3:
            opcode = data[0]
            if opcode in (0x52, 0x1B) and len(data) > 2:
                att_handle = struct.unpack_from('<H', data, 1)[0]
                att_value = data[3:]
                
                # Look for FE DC BA in the ATT value
                for idx in range(len(att_value)):
                    if (idx + 7 < len(att_value) and 
                        att_value[idx] == 0xFE and att_value[idx+1] == 0xDC and att_value[idx+2] == 0xBA):
                        flag = att_value[idx+3]
                        cmd = att_value[idx+4]
                        body_len = (att_value[idx+5] << 8) | att_value[idx+6]
                        
                        # Find EF terminator
                        frame_end = idx + 7 + body_len
                        if frame_end < len(att_value) and att_value[frame_end] == 0xEF:
                            body = att_value[idx+7:frame_end]
                            assembled_frames.append({
                                'direction': current_frame['direction'],
                                'rec_idx': current_frame['rec_idx'],
                                'flag': flag,
                                'cmd': cmd,
                                'body': bytes(body),
                                'body_len': body_len
                            })
                        break
        current_frame = None

print(f"Assembled {len(assembled_frames)} FE frames")

# Now print the data transfer sequence
print("\nDATA TRANSFER SEQUENCE:")
print("="*100)

data_frames = []
for i, f in enumerate(assembled_frames):
    if f['flag'] == 0x80 and f['cmd'] == 0x01:
        body = f['body']
        seq = body[0]
        marker = body[1]
        slot = body[2]
        crc_hi = body[3]
        crc_lo = body[4]
        file_data = body[5:]
        data_frames.append({
            'idx': i, 'seq': seq, 'slot': slot,
            'crc': (crc_hi << 8) | crc_lo,
            'data_len': len(file_data),
            'data_preview': file_data[:16],
            'direction': f['direction']
        })
        
        print(f"  [{i:3d}] {f['direction']:3s} seq=0x{seq:02x} slot={slot} crc=0x{(crc_hi<<8)|crc_lo:04x} "
              f"data_len={len(file_data)} preview={' '.join(f'{b:02x}' for b in file_data[:16])}")
    
    elif f['flag'] == 0x80 and f['cmd'] == 0x1d:
        body = f['body']
        body_hex = ' '.join(f'{b:02x}' for b in body)
        
        # Parse window ack
        ack_seq = body[0]
        b1 = body[1]
        win_be = (body[2] << 8) | body[3]
        off_be32 = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
        
        print(f"  [{i:3d}] {f['direction']:3s} WINDOW ACK seq={ack_seq} win_size={win_be} ({win_be//490} chunks) offset={off_be32} body={body_hex}")
    
    elif f['cmd'] in (0x20, 0x1c, 0x1b):
        body_hex = ' '.join(f'{b:02x}' for b in f['body'][:30])
        print(f"  [{i:3d}] {f['direction']:3s} CMD 0x{f['cmd']:02x} flag=0x{f['flag']:02x} body={body_hex}")

print(f"\nTotal data frames: {len(data_frames)}")
print("Sequences:", [f'0x{d["seq"]:02x}' for d in data_frames])
print(f"Slots: {[d['slot'] for d in data_frames]}")
print(f"Data lengths: {[d['data_len'] for d in data_frames]}")
print(f"Total data bytes: {sum(d['data_len'] for d in data_frames)}")

# Check if last frame is really JFIF
last = data_frames[-1]
print(f"\nLast data frame: seq=0x{last['seq']:02x} slot={last['slot']} data_len={last['data_len']}")
print(f"  First 20 bytes: {' '.join(f'{b:02x}' for b in last['data_preview'])}")
if last['data_preview'][:4] == bytes([0xFF, 0xD8, 0xFF, 0xE0]):
    print("  ** THIS IS A JPEG HEADER (JFIF) **")
