#!/usr/bin/env python3
"""Probe pklg format and extract FE DC BA frames."""
import struct, sys

path = '/Users/herbst/git/bluetooth-tag/cap.pklg'
data = open(path, 'rb').read()
print(f"File size: {len(data)} bytes")
print(f"First 64 bytes: {' '.join(f'{b:02x}' for b in data[:64])}")
print()

# The earlier parser had this working with LE fields. Try that.
# Apple PacketLogger format (as discovered earlier):
# 4-byte LE length (includes everything after length field)
# 8-byte LE timestamp
# 1-byte type
# payload

records = []
pos = 0
while pos + 13 < len(data):
    rec_len = struct.unpack('<I', data[pos:pos+4])[0]
    if rec_len < 9 or rec_len > 100000 or pos + 4 + rec_len > len(data):
        # Try skipping to find next valid record
        break
    ts = struct.unpack('<Q', data[pos+4:pos+12])[0]
    pkt_type = data[pos+12]
    payload = data[pos+13:pos+4+rec_len]
    records.append((ts, pkt_type, payload))
    pos += 4 + rec_len

print(f"Format A (LE len, LE ts): {len(records)} records")
if records:
    for i, (ts, pt, pl) in enumerate(records[:3]):
        print(f"  [{i}] type=0x{pt:02x} payload_len={len(pl)} first_bytes={' '.join(f'{b:02x}' for b in pl[:20])}")

# If that didn't work, try other layouts
if len(records) < 5:
    records = []
    pos = 0
    while pos + 13 < len(data):
        rec_len = struct.unpack('>I', data[pos:pos+4])[0]
        if rec_len < 9 or rec_len > 100000 or pos + 4 + rec_len > len(data):
            break
        ts = struct.unpack('>Q', data[pos+4:pos+12])[0]
        pkt_type = data[pos+12]
        payload = data[pos+13:pos+4+rec_len]
        records.append((ts, pkt_type, payload))
        pos += 4 + rec_len
    
    print(f"Format B (BE len, BE ts): {len(records)} records")
    if records:
        for i, (ts, pt, pl) in enumerate(records[:3]):
            print(f"  [{i}] type=0x{pt:02x} payload_len={len(pl)} first_bytes={' '.join(f'{b:02x}' for b in pl[:20])}")

# Maybe it's: 4-byte BE length that includes its own 4 bytes
if len(records) < 5:
    records = []
    pos = 0
    while pos + 4 < len(data):
        total_len = struct.unpack('>I', data[pos:pos+4])[0]
        payload_len = total_len - 4
        if payload_len < 9 or payload_len > 100000 or pos + total_len > len(data):
            break
        ts = struct.unpack('>Q', data[pos+4:pos+12])[0]
        pkt_type = data[pos+12]
        payload = data[pos+13:pos+total_len]
        records.append((ts, pkt_type, payload))
        pos += total_len
    
    print(f"Format C (BE total_len incl self): {len(records)} records")
    if records:
        for i, (ts, pt, pl) in enumerate(records[:3]):
            print(f"  [{i}] type=0x{pt:02x} payload_len={len(pl)} first_bytes={' '.join(f'{b:02x}' for b in pl[:20])}")

# Now scan raw file for all FE DC BA sequences regardless of framing
print(f"\n{'='*60}")
print("RAW SCAN for FE DC BA frames")
print(f"{'='*60}")

fe_frames = []
for j in range(len(data) - 7):
    if data[j] == 0xFE and data[j+1] == 0xDC and data[j+2] == 0xBA:
        flag = data[j+3]
        cmd = data[j+4]
        length = (data[j+5] << 8) | data[j+6]
        body_end = j + 7 + length
        if body_end < len(data) and data[body_end] == 0xEF:
            body = data[j+7:body_end]
            
            # Determine direction: look backwards for HCI framing clues
            # In pklg, each record has a type byte. We need to find which record contains this offset.
            fe_frames.append({
                'offset': j,
                'flag': flag,
                'cmd': cmd,
                'length': length,
                'body': body,
            })

print(f"Total FE DC BA frames: {len(fe_frames)}")

# Categorize
cmd_counts = {}
for f in fe_frames:
    key = f'0x{f["cmd"]:02x}'
    cmd_counts[key] = cmd_counts.get(key, 0) + 1

print(f"Command distribution: {cmd_counts}")

# Print non-data frames and a few data frames
data_count = 0
for i, f in enumerate(fe_frames):
    body_hex = ' '.join(f'{b:02x}' for b in f['body'][:min(40, len(f['body']))])
    if len(f['body']) > 40:
        body_hex += '...'
    
    cmd_name = {
        0x01: 'DATA', 0x03: 'DEV_INFO', 0x06: 'RESET_AUTH', 0x07: 'DEV_CONFIG',
        0x1b: 'FILE_META', 0x1c: 'COMPLETE_1C', 0x1d: 'WINDOW_ACK',
        0x20: 'COMPLETE_20', 0x21: 'BEGIN_UPLOAD', 0x27: 'XFER_PARAMS',
    }.get(f['cmd'], f'CMD_{f["cmd"]:02X}')
    
    if f['cmd'] == 0x01 and f['flag'] == 0x80:
        data_count += 1
        if data_count <= 5 or data_count == len([x for x in fe_frames if x['cmd'] == 0x01]):
            print(f"  [{i:4d}] @0x{f['offset']:06x} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}")
        elif data_count == 6:
            print(f"  ... (more data frames) ...")
    else:
        print(f"  [{i:4d}] @0x{f['offset']:06x} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}")

# Completion sequence analysis
print(f"\n{'='*60}")
print("COMPLETION SEQUENCE (everything after last DATA frame)")
print(f"{'='*60}")
last_data_i = -1
for i, f in enumerate(fe_frames):
    if f['cmd'] == 0x01 and f['flag'] == 0x80:
        last_data_i = i

if last_data_i >= 0:
    for i in range(max(0, last_data_i - 2), len(fe_frames)):
        f = fe_frames[i]
        body_hex = ' '.join(f'{b:02x}' for b in f['body'])
        cmd_name = {
            0x01: 'DATA', 0x03: 'DEV_INFO', 0x06: 'RESET_AUTH', 0x07: 'DEV_CONFIG',
            0x1b: 'FILE_META', 0x1c: 'COMPLETE_1C', 0x1d: 'WINDOW_ACK',
            0x20: 'COMPLETE_20', 0x21: 'BEGIN_UPLOAD', 0x27: 'XFER_PARAMS',
        }.get(f['cmd'], f'CMD_{f["cmd"]:02X}')
        marker = " <<<LAST DATA" if i == last_data_i else ""
        print(f"  [{i:4d}] @0x{f['offset']:06x} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}{marker}")

# Window size analysis
print(f"\n{'='*60}")
print("WINDOW SIZE ANALYSIS")
print(f"{'='*60}")
cur_window = 0
window_sizes = []
for f in fe_frames:
    if f['cmd'] == 0x01 and f['flag'] == 0x80:
        cur_window += 1
    elif f['cmd'] == 0x1d:
        if cur_window > 0:
            window_sizes.append(cur_window)
        cur_window = 0
print(f"Window sizes: {window_sizes}")
if window_sizes:
    print(f"Min: {min(window_sizes)}, Max: {max(window_sizes)}, Avg: {sum(window_sizes)/len(window_sizes):.1f}")

# Data frame seq/slot analysis
print(f"\n{'='*60}")
print("DATA FRAME SEQ/SLOT ANALYSIS")
print(f"{'='*60}")
data_frames = [f for f in fe_frames if f['cmd'] == 0x01 and f['flag'] == 0x80]
for i, f in enumerate(data_frames[:10]):
    b = f['body']
    if len(b) >= 3:
        print(f"  Data[{i:3d}]: seq=0x{b[0]:02x} byte1=0x{b[1]:02x} byte2=0x{b[2]:02x} payload_len={len(b)-3}")
print("  ...")
for i in range(max(0, len(data_frames)-5), len(data_frames)):
    f = data_frames[i]
    b = f['body']
    if len(b) >= 3:
        print(f"  Data[{i:3d}]: seq=0x{b[0]:02x} byte1=0x{b[1]:02x} byte2=0x{b[2]:02x} payload_len={len(b)-3}")

# cmd 0x1b analysis
print(f"\n{'='*60}")
print("FILE METADATA (cmd 0x1b)")
print(f"{'='*60}")
for f in fe_frames:
    if f['cmd'] == 0x1b:
        body_hex = ' '.join(f'{b:02x}' for b in f['body'])
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")
        b = f['body']
        if f['flag'] in (0xc0, 0x40) and len(b) >= 5:
            # Analyze TX metadata body
            print(f"    seq=0x{b[0]:02x}")
            # Try different size interpretations
            if len(b) >= 5:
                s16 = struct.unpack_from('<H', bytes(b), 3)[0]
                print(f"    body[3:5] as LE16 = {s16}")
            if len(b) >= 7:
                s32 = struct.unpack_from('<I', bytes(b), 3)[0]
                print(f"    body[3:7] as LE32 = {s32}")
            if len(b) >= 7:
                s32b = struct.unpack_from('<I', bytes(b), 1)[0]
                print(f"    body[1:5] as LE32 = {s32b}")
            # Try to find filename
            try:
                txt = bytes(b).decode('ascii', errors='replace')
                print(f"    ascii: {txt}")
            except:
                pass
