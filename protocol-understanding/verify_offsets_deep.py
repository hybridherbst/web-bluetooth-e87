#!/usr/bin/env python3
"""Deep analysis: verify EXACT byte offsets from the capture.
Compare chunk content against original image at both possible interpretations:
  A) WIN_ACK nextOffset = offset into ORIGINAL image (our new code)
  B) WIN_ACK nextOffset = offset into ROTATED buffer (our old code)
Also check: does the device ALWAYS start at offset=chunk_size?
"""
import struct

img = open('/Users/herbst/git/bluetooth-tag/web/public/captured_image.jpg', 'rb').read()

def crc16_xmodem(data):
    crc = 0x0000
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xffff
            else:
                crc = (crc << 1) & 0xffff
    return crc

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
rec_idx = 0
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_secs = struct.unpack_from('<I', raw, off+4)[0]
    ts_usecs = struct.unpack_from('<I', raw, off+8)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': rec_idx, 'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6})
    rec_idx += 1
    off += 4 + rec_len
    if off > len(raw):
        break

# Extract all FE frames
events = []
for r in records:
    if r['type'] not in (2, 3):
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            body = p[idx+7:idx+7+blen]
            direction = 'TX' if r['type'] == 2 else 'RX'
            events.append({'dir': direction, 'flag': flag, 'cmd': cmd, 'blen': blen, 'body': body, 'ts': r['ts']})
            break

# Find the 0x1b TX and RX
for e in events:
    if e['cmd'] == 0x1b and e['dir'] == 'TX':
        b = e['body']
        print(f"TX 0x1b body: {b.hex()}")
        print(f"  seq={b[0]}, flags=0x{b[1]:02x}{b[2]:02x}")
        fsize = (b[3] << 8) | b[4]
        print(f"  fileSize={fsize} (0x{fsize:04x})")
    if e['cmd'] == 0x1b and e['dir'] == 'RX':
        b = e['body']
        print(f"RX 0x1b ack body: {b.hex()}")
        status = b[0]
        seq = b[1]
        chunk_size = (b[2] << 8) | b[3]
        print(f"  status={status}, seq={seq}, chunk_size={chunk_size} (0x{chunk_size:04x})")

print()

# Now let's look at each WIN_ACK and verify what offset+chunk maps to what image data
win_acks = []
for e in events:
    if e['cmd'] == 0x1d and e['dir'] == 'RX' and e['flag'] == 0x80:
        b = e['body']
        if len(b) >= 8:
            seq = b[0]
            status = b[1]
            ws = (b[2] << 8) | b[3]
            noff = (b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]
            win_acks.append((seq, status, ws, noff))

# Get the data chunks with their CRCs and first visible bytes
data_chunks = []
for e in events:
    if e['cmd'] == 0x01 and e['flag'] == 0x80 and e['dir'] == 'TX':
        b = e['body']
        if len(b) >= 5:
            seq = b[0]
            subcmd = b[1]
            slot = b[2]
            crc = (b[3] << 8) | b[4]
            first_data = b[5:9] if len(b) > 8 else b[5:]
            data_chunks.append((seq, subcmd, slot, crc, first_data, len(b)-5))

print(f"WIN_ACKs: {len(win_acks)}")
print(f"Data chunks: {len(data_chunks)}")
print(f"Image size: {len(img)} bytes")
print()

# Map each win_ack to its data chunks
chunk_idx = 0
total_bytes_sent = 0
for wseq, wstatus, wsize, woff in win_acks:
    print(f"WIN_ACK seq={wseq}: offset={woff}, winSize={wsize}")
    window_bytes = 0
    while chunk_idx < len(data_chunks) and window_bytes < wsize:
        seq, subcmd, slot, crc, first_data, payload_len = data_chunks[chunk_idx]
        # Verify CRC against img[woff + window_bytes]
        src_offset = woff + window_bytes
        chunk_len = min(490, wsize - window_bytes, len(img) - src_offset)
        src_data = img[src_offset:src_offset + chunk_len]
        computed_crc = crc16_xmodem(src_data)
        match = "✓" if computed_crc == crc else "✗"
        if computed_crc != crc:
            print(f"  chunk {chunk_idx}: seq={seq} slot={slot} img[{src_offset}:{src_offset+chunk_len}]={chunk_len}B crc=0x{crc:04x} computed=0x{computed_crc:04x} {match} MISMATCH!")
        window_bytes += chunk_len
        total_bytes_sent += chunk_len
        chunk_idx += 1
        if src_offset + chunk_len >= len(img):
            break
    print(f"  → sent {window_bytes} bytes in this window")

print(f"\nTotal bytes sent across all windows: {total_bytes_sent}")
print(f"Image size: {len(img)}")
print(f"Match: {total_bytes_sent == len(img)}")

# KEY CHECK: Does the first WIN_ACK offset ALWAYS equal the chunk_size from 0x1b ack?
print(f"\nFirst WIN_ACK offset: {win_acks[0][3]}")
print(f"Chunk size from 0x1b: 490")
print(f"They match: {win_acks[0][3] == 490}")

# ANOTHER KEY CHECK: What is the sequence of offsets?
print("\nWIN_ACK offset sequence:")
for wseq, _, wsize, woff in win_acks:
    print(f"  #{wseq}: offset={woff} winSize={wsize}")
