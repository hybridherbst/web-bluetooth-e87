#!/usr/bin/env python3
"""Final focused analysis of window acks, data flow, and completion."""
import struct

path = '/Users/herbst/git/bluetooth-tag/cap.pklg'
data = open(path, 'rb').read()

# Parse pklg records (LE format)
records = []
pos = 0
while pos + 13 < len(data):
    rec_len = struct.unpack('<I', data[pos:pos+4])[0]
    if rec_len < 9 or rec_len > 100000 or pos + 4 + rec_len > len(data):
        break
    ts = struct.unpack('<Q', data[pos+4:pos+12])[0]
    pkt_type = data[pos+12]
    payload = data[pos+13:pos+4+rec_len]
    records.append({'ts': ts, 'type': pkt_type, 'payload': bytes(payload)})
    pos += 4 + rec_len

# Find all FE DC BA frames with raw file offsets
fe_frames = []
for j in range(len(data) - 7):
    if data[j] == 0xFE and data[j+1] == 0xDC and data[j+2] == 0xBA:
        flag = data[j+3]
        cmd = data[j+4]
        length = (data[j+5] << 8) | data[j+6]
        body_end = j + 7 + length
        if body_end < len(data) and data[body_end] == 0xEF:
            body = data[j+7:body_end]
            fe_frames.append({'offset': j, 'flag': flag, 'cmd': cmd, 'length': length, 'body': body})

print("=" * 70)
print("WINDOW ACK (cmd 0x1d) BODY ANALYSIS")
print("=" * 70)
for f in fe_frames:
    if f['cmd'] == 0x1d:
        b = f['body']
        body_hex = ' '.join(f'{b[i]:02x}' for i in range(len(b)))
        print(f"  flag=0x{f['flag']:02x} body: {body_hex}")
        if len(b) >= 8:
            seq = b[0]
            b1 = b[1]
            # bytes 2-3 could be window size (BE or LE)
            w_be = (b[2] << 8) | b[3]
            w_le = (b[3] << 8) | b[2]
            # bytes 4-5
            v2_be = (b[4] << 8) | b[5]
            v2_le = (b[5] << 8) | b[4]
            # bytes 6-7 could be offset/progress
            off_be = (b[6] << 8) | b[7]
            off_le = (b[7] << 8) | b[6]
            print(f"    [0]=seq={seq}, [1]={b1}, [2:4] BE={w_be} LE={w_le}")
            print(f"    [4:6] BE={v2_be} LE={v2_le}, [6:8] BE={off_be} LE={off_le}")
            # Try 4-byte values
            off32_le = struct.unpack_from('<I', bytes(b), 4)[0]
            print(f"    [4:8] as LE32 = {off32_le} (0x{off32_le:08x})")

# Total file size from metadata
print("\n" + "=" * 70)
print("FILE SIZE FROM METADATA")
print("=" * 70)
for f in fe_frames:
    if f['cmd'] == 0x1b and f['flag'] == 0xc0:
        b = f['body']
        # body[3:5] as LE16
        size_le16 = (b[4] << 8) | b[3]
        size32 = struct.unpack_from('<I', bytes(b), 3)[0] if len(b) >= 7 else 0
        print(f"  body[3:5] LE16 = {size_le16} = 0x{size_le16:04x}")
        print(f"  body[3:7] LE32 = {size32} = 0x{size32:08x}")
        # Check body[1:3]
        print(f"  body[0:3] = {b[0]:02x} {b[1]:02x} {b[2]:02x}")
        # The body is: seq, 00, 00, size_lo, size_hi, token(4), filename, 00
        # OR: seq, offset_lo, offset_hi, size_lo, size_hi, ...
        print(f"  Full body hex: {' '.join(f'{x:02x}' for x in b)}")
        # Find filename
        for k in range(5, len(b)):
            if b[k] == 0x00 and k > 9:
                try:
                    name = bytes(b[9:k]).decode('ascii')
                    print(f"  Token bytes[5:9]: {' '.join(f'{b[i]:02x}' for i in range(5, 9))}")
                    print(f"  Filename: '{name}'")
                    break
                except:
                    pass

# Data frame analysis: count total frames, total data bytes, body structure
print("\n" + "=" * 70)
print("DATA FRAMES (cmd 0x01) ANALYSIS")
print("=" * 70)
data_frames = [f for f in fe_frames if f['cmd'] == 0x01 and f['flag'] == 0x80]
print(f"Total data frames: {len(data_frames)}")
total_payload = sum(len(f['body']) - 3 for f in data_frames)
print(f"Total payload bytes (body - 3 header bytes): {total_payload}")

# Look at body[0], body[1], body[2] pattern
print("\nBody header pattern (seq, byte1, byte2):")
for i, f in enumerate(data_frames):
    b = f['body']
    if len(b) >= 3:
        seq = b[0]
        b1 = b[1]
        b2 = b[2]
        payload_len = len(b) - 3
        if i < 10 or i >= len(data_frames) - 5:
            print(f"  Data[{i:3d}]: seq=0x{seq:02x}({seq:3d}) b1=0x{b1:02x} slot=0x{b2:02x} payload={payload_len}")
        elif i == 10:
            print("  ...")

# Now the COMPLETION sequence
print("\n" + "=" * 70)
print("FULL COMPLETION SEQUENCE")
print("=" * 70)

# cmd 0x06
print("\ncmd 0x06 (RESET AUTH):")
for f in fe_frames:
    if f['cmd'] == 0x06:
        b = f['body']
        body_hex = ' '.join(f'{x:02x}' for x in b)
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")

# cmd 0x21
print("\ncmd 0x21 (BEGIN UPLOAD):")
for f in fe_frames:
    if f['cmd'] == 0x21:
        b = f['body']
        body_hex = ' '.join(f'{x:02x}' for x in b)
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")

# cmd 0x27
print("\ncmd 0x27 (TRANSFER PARAMS):")
for f in fe_frames:
    if f['cmd'] == 0x27:
        b = f['body']
        body_hex = ' '.join(f'{x:02x}' for x in b)
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")

# cmd 0x1b
print("\ncmd 0x1b (FILE METADATA):")
for f in fe_frames:
    if f['cmd'] == 0x1b:
        b = f['body']
        body_hex = ' '.join(f'{x:02x}' for x in b)
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")

# cmd 0x20
print("\ncmd 0x20 (COMPLETE):")
for f in fe_frames:
    if f['cmd'] == 0x20:
        b = f['body']
        body_hex = ' '.join(f'{x:02x}' for x in b)
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")

# cmd 0x1c
print("\ncmd 0x1c (FINALIZE):")
for f in fe_frames:
    if f['cmd'] == 0x1c:
        b = f['body']
        body_hex = ' '.join(f'{x:02x}' for x in b)
        print(f"  flag=0x{f['flag']:02x} len={f['length']} body: {body_hex}")

# Window ack byte[6:8] as accumulated offset
print("\n" + "=" * 70)
print("WINDOW ACK OFFSET PROGRESSION")
print("=" * 70)
prev_offset = 0
for i, f in enumerate(fe_frames):
    if f['cmd'] == 0x1d:
        b = f['body']
        if len(b) >= 8:
            offset_le = struct.unpack_from('<H', bytes(b), 6)[0]
            offset_be = struct.unpack_from('>H', bytes(b), 6)[0]
            offset_le32 = struct.unpack_from('<I', bytes(b), 4)[0]
            window = struct.unpack_from('>H', bytes(b), 2)[0]
            # Count data frames between this and previous window ack
            delta_le = offset_le - prev_offset if i > 0 else offset_le
            delta_be = offset_be - prev_offset if i > 0 else offset_be
            print(f"  WA[{i}]: bytes={' '.join(f'{x:02x}' for x in b)}  window_be={window} offset_le={offset_le} offset_be={offset_be}")
            prev_offset = offset_le
