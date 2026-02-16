#!/usr/bin/env python3
"""
Parse Apple PacketLogger (.pklg) capture to extract the full FE-framed
upload protocol exchange. Focuses on the data transfer and completion phases.
"""
import struct, sys

def parse_pklg(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    records = []
    pos = 0
    while pos + 4 < len(data):
        rec_len = struct.unpack('>I', data[pos:pos+4])[0]
        if rec_len > 0 and rec_len < 100000 and pos + 4 + rec_len <= len(data):
            rec_data = data[pos+4:pos+4+rec_len]
            if len(rec_data) >= 9:
                ts = struct.unpack('>Q', rec_data[:8])[0]
                pkt_type = rec_data[8]
                payload = rec_data[9:]
                records.append((ts, pkt_type, payload))
            pos += 4 + rec_len
        else:
            break

    print(f"Total records: {len(records)}")
    return records


def find_fe_frames(records):
    """Extract all FE DC BA framed packets with direction info."""
    frames = []
    for ts, pkt_type, payload in records:
        # pkt_type: 0x00 = sent (Host→Controller), 0x01 = received (Controller→Host)
        # We need to find FE DC BA sequences in the ATT payload
        # HCI ACL data typically has: handle(2) + length(2) + L2CAP length(2) + CID(2) + ATT...
        # The FE DC BA sequence could be at various offsets depending on HCI framing
        
        for offset in range(len(payload) - 7):
            if payload[offset] == 0xFE and payload[offset+1] == 0xDC and payload[offset+2] == 0xBA:
                # Found frame header
                flag = payload[offset+3]
                cmd = payload[offset+4]
                length = (payload[offset+5] << 8) | payload[offset+6]
                body_start = offset + 7
                body_end = body_start + length
                
                # Check for EF terminator
                if body_end < len(payload) and payload[body_end] == 0xEF:
                    body = payload[body_start:body_end]
                    direction = "TX" if pkt_type == 0x00 else "RX"
                    frames.append({
                        'ts': ts,
                        'dir': direction,
                        'flag': flag,
                        'cmd': cmd,
                        'length': length,
                        'body': bytes(body),
                        'pkt_type': pkt_type,
                    })
    
    return frames


def find_9e_packets(records):
    """Extract 9E-prefixed control packets."""
    packets = []
    for ts, pkt_type, payload in records:
        for offset in range(len(payload) - 3):
            if payload[offset] == 0x9E:
                # Could be a 9E control packet — grab a reasonable chunk
                remaining = min(len(payload) - offset, 30)
                direction = "TX" if pkt_type == 0x00 else "RX"
                data = bytes(payload[offset:offset+remaining])
                packets.append({
                    'ts': ts,
                    'dir': direction,
                    'data': data,
                })
                break  # one per record
    return packets


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'cap.pklg'
    records = parse_pklg(path)
    frames = find_fe_frames(records)
    
    print(f"\n{'='*80}")
    print(f"FE DC BA frames found: {len(frames)}")
    print(f"{'='*80}\n")
    
    # Group by phase
    data_frame_count = 0
    window_ack_count = 0
    last_data_seq = -1
    last_data_slot = -1
    window_size_samples = []
    cur_window = 0
    
    for i, f in enumerate(frames):
        body_hex = ' '.join(f'{b:02x}' for b in f['body'][:min(32, len(f['body']))])
        if len(f['body']) > 32:
            body_hex += '...'
        
        cmd_name = {
            0x01: 'DATA',
            0x03: 'DEV_INFO',
            0x06: 'RESET_AUTH',
            0x07: 'DEV_CONFIG',
            0x1b: 'FILE_META',
            0x1c: 'COMPLETE_1C',
            0x1d: 'WINDOW_ACK',
            0x20: 'COMPLETE_20',
            0x21: 'BEGIN_UPLOAD',
            0x27: 'TRANSFER_PARAMS',
        }.get(f['cmd'], f'CMD_{f["cmd"]:02X}')
        
        # Track data frames
        if f['cmd'] == 0x01 and f['flag'] == 0x80:
            data_frame_count += 1
            cur_window += 1
            if len(f['body']) >= 3:
                last_data_seq = f['body'][0]
                last_data_slot = f['body'][2] if len(f['body']) > 2 else -1
            # Only print first/last few data frames and window boundaries
            if data_frame_count <= 3 or (data_frame_count % 100 == 0):
                print(f"  [{i:4d}] {f['dir']} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}")
        elif f['cmd'] == 0x1d:
            if cur_window > 0:
                window_size_samples.append(cur_window)
            cur_window = 0
            window_ack_count += 1
            print(f"  [{i:4d}] {f['dir']} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}  [after {window_size_samples[-1] if window_size_samples else '?'} data frames]")
        else:
            print(f"  [{i:4d}] {f['dir']} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}")
    
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total data frames (cmd 0x01):      {data_frame_count}")
    print(f"Total window acks (cmd 0x1d):      {window_ack_count}")
    print(f"Window sizes:                      {window_size_samples}")
    print(f"Last data seq:                     0x{last_data_seq:02x} ({last_data_seq})")
    
    # Analyze the body structure of first few data frames
    print(f"\n{'='*80}")
    print(f"DATA FRAME BODY ANALYSIS (first 5)")
    print(f"{'='*80}")
    data_frames = [f for f in frames if f['cmd'] == 0x01 and f['flag'] == 0x80]
    for i, f in enumerate(data_frames[:5]):
        body = f['body']
        print(f"  Frame {i}: len={len(body)}, first 16 bytes: {' '.join(f'{b:02x}' for b in body[:16])}")
        if len(body) >= 3:
            print(f"    body[0]=seq=0x{body[0]:02x}, body[1]=0x{body[1]:02x}, body[2]=slot=0x{body[2]:02x}")
    
    # Last 5 data frames
    print(f"\nDATA FRAME BODY ANALYSIS (last 5)")
    for i, f in enumerate(data_frames[-5:]):
        body = f['body']
        idx = len(data_frames) - 5 + i
        print(f"  Frame {idx}: len={len(body)}, first 16 bytes: {' '.join(f'{b:02x}' for b in body[:16])}")
        if len(body) >= 3:
            print(f"    body[0]=seq=0x{body[0]:02x}, body[1]=0x{body[1]:02x}, body[2]=slot=0x{body[2]:02x}")
    
    # Analyze completion sequence (everything after last data frame)
    print(f"\n{'='*80}")
    print(f"COMPLETION SEQUENCE (after last data frame)")
    print(f"{'='*80}")
    last_data_idx = -1
    for i, f in enumerate(frames):
        if f['cmd'] == 0x01 and f['flag'] == 0x80:
            last_data_idx = i
    
    if last_data_idx >= 0:
        for i in range(last_data_idx + 1, len(frames)):
            f = frames[i]
            body_hex = ' '.join(f'{b:02x}' for b in f['body'])
            cmd_name = {
                0x01: 'DATA', 0x03: 'DEV_INFO', 0x06: 'RESET_AUTH', 0x07: 'DEV_CONFIG',
                0x1b: 'FILE_META', 0x1c: 'COMPLETE_1C', 0x1d: 'WINDOW_ACK',
                0x20: 'COMPLETE_20', 0x21: 'BEGIN_UPLOAD', 0x27: 'TRANSFER_PARAMS',
            }.get(f['cmd'], f'CMD_{f["cmd"]:02X}')
            print(f"  [{i:4d}] {f['dir']} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} ({cmd_name:15s}) len={f['length']:5d}  body: {body_hex}")
    
    # Analyze cmd 0x1b body (file metadata)
    print(f"\n{'='*80}")
    print(f"FILE METADATA (cmd 0x1b) BODY ANALYSIS")
    print(f"{'='*80}")
    meta_frames = [f for f in frames if f['cmd'] == 0x1b]
    for f in meta_frames:
        body = f['body']
        body_hex = ' '.join(f'{b:02x}' for b in body)
        print(f"  {f['dir']} len={len(body)} body: {body_hex}")
        if len(body) >= 10 and f['dir'] == 'TX':
            seq = body[0]
            size_lo = body[3]
            size_hi = body[4]
            size = (size_hi << 8) | size_lo
            print(f"    seq=0x{seq:02x}, bytes[1:3]={body[1]:02x} {body[2]:02x}, size_le16={size} (0x{size:04x})")
            # Check for a 4-byte size 
            if len(body) >= 7:
                size32 = struct.unpack_from('<I', bytes(body), 1)[0]
                print(f"    Or body[1:5] as LE32 size = {size32} (0x{size32:08x})")
            # Try to find filename
            for j in range(5, len(body)):
                if body[j] == 0x00 and j > 5:
                    try:
                        name_candidate = bytes(body[5:j]).decode('ascii', errors='replace')
                        if any(c.isalpha() for c in name_candidate):
                            print(f"    Possible filename at [5:{j}]: '{name_candidate}'")
                    except:
                        pass

    # Analyze cmd 0x27 body
    print(f"\n{'='*80}")
    print(f"TRANSFER PARAMS (cmd 0x27) BODY ANALYSIS")
    print(f"{'='*80}")
    param_frames = [f for f in frames if f['cmd'] == 0x27]
    for f in param_frames:
        body = f['body']
        body_hex = ' '.join(f'{b:02x}' for b in body)
        print(f"  {f['dir']} len={len(body)} body: {body_hex}")

    # Analyze cmd 0x21 body
    print(f"\n{'='*80}")
    print(f"BEGIN UPLOAD (cmd 0x21) BODY ANALYSIS")
    print(f"{'='*80}")
    begin_frames = [f for f in frames if f['cmd'] == 0x21]
    for f in begin_frames:
        body = f['body']
        body_hex = ' '.join(f'{b:02x}' for b in body)
        print(f"  {f['dir']} len={len(body)} body: {body_hex}")


if __name__ == '__main__':
    main()
