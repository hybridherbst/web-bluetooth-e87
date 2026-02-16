#!/usr/bin/env python3
"""Extract and analyze all data chunks from the capture file."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_secs = struct.unpack_from('<I', raw, off+4)[0]
    ts_usecs = struct.unpack_from('<I', raw, off+8)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6})
    off += 4 + rec_len

# Scan for FE DC BA data frames in TX records
data_chunks = []
win_acks = []
for r in records:
    p = r['payload']
    direction = 'TX' if r['type'] == 2 else 'RX'
    for i in range(len(p) - 10):
        if p[i:i+3] == b'\xfe\xdc\xba':
            flag = p[i+3]
            cmd = p[i+4]
            blen = (p[i+5] << 8) | p[i+6]
            body = p[i+7:i+7+blen]
            
            if cmd == 0x01 and flag == 0x80 and direction == 'TX' and len(body) >= 5:
                seq = body[0]
                slot = body[2]
                crc = (body[3] << 8) | body[4]
                plen = blen - 5
                first4 = body[5:9].hex() if len(body) > 8 else ''
                jfif = ' [JFIF!]' if first4.startswith('ffd8') else ''
                data_chunks.append((seq, slot, crc, plen, jfif, r['ts']))
            
            elif cmd == 0x1d and flag == 0x80 and direction == 'RX' and len(body) >= 8:
                ack_seq = body[0]
                status = body[1]
                win_size = (body[2] << 8) | body[3]
                next_off = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
                win_acks.append((ack_seq, status, win_size, next_off, r['ts']))
            break

total_bytes = sum(c[3] for c in data_chunks)
print(f'Total data chunks: {len(data_chunks)}')
print(f'Total payload bytes: {total_bytes}')
print()

# Show data chunks grouped by window
chunk_idx = 0
for wa_idx, (ack_seq, status, win_size, next_off, wa_ts) in enumerate(win_acks):
    # Chunks before this ack (sent before ack timestamp)
    win_chunks = []
    while chunk_idx < len(data_chunks) and data_chunks[chunk_idx][5] < wa_ts:
        win_chunks.append(data_chunks[chunk_idx])
        chunk_idx += 1
    
    if win_chunks:
        psum = sum(c[3] for c in win_chunks)
        print(f'Window (before ack #{ack_seq}): {len(win_chunks)} chunks, {psum} bytes')
        for c in win_chunks:
            print(f'  seq={c[0]:2d} slot={c[1]} crc=0x{c[2]:04x} pLen={c[3]:3d}{c[4]}')
    
    print(f'  -> WIN_ACK ackSeq={ack_seq} st={status} wSz={win_size} nOff={next_off}')
    print()

# Remaining chunks (after last ack = commit)
if chunk_idx < len(data_chunks):
    remaining = data_chunks[chunk_idx:]
    psum = sum(c[3] for c in remaining)
    print(f'COMMIT ({len(remaining)} chunks, {psum} bytes):')
    for c in remaining:
        print(f'  seq={c[0]:2d} slot={c[1]} crc=0x{c[2]:04x} pLen={c[3]:3d}{c[4]}')

# Show WIN_ACK sequence
print()
print('WIN_ACK SEQUENCE:')
for ack_seq, status, win_size, next_off, _ in win_acks:
    print(f'  ackSeq={ack_seq} st={status} wSz={win_size} nOff={next_off}')
