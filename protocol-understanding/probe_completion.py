#!/usr/bin/env python3
"""Extract the FULL protocol sequence from cap.pklg, focusing on everything
after the last data frame (0x80/0x01) to understand the completion handshake."""

import struct, sys

def parse_pklg(path):
    records = []
    with open(path, 'rb') as f:
        # Skip 4-byte pklg header
        hdr = f.read(4)
        while True:
            rec_hdr = f.read(13)
            if len(rec_hdr) < 13:
                break
            rec_len, ts_secs, ts_usecs, rec_type = struct.unpack('<I II B', rec_hdr)
            payload_len = rec_len - 9  # 13 - 4 = 9 bytes of header after length
            payload = f.read(payload_len)
            if len(payload) < payload_len:
                break
            records.append({
                'type': rec_type,
                'ts': ts_secs + ts_usecs / 1e6,
                'data': payload,
                'idx': len(records)
            })
    return records

def parse_fe_frame(data):
    """Parse FE DC BA ... EF frame"""
    if len(data) < 8:
        return None
    if data[0] != 0xFE or data[1] != 0xDC or data[2] != 0xBA:
        return None
    if data[-1] != 0xEF:
        return None
    flag = data[3]
    cmd = data[4]
    length = (data[5] << 8) | data[6]
    body = data[7:-1]
    return {'flag': flag, 'cmd': cmd, 'length': length, 'body': body}

def direction_str(rec_type):
    if rec_type == 0x02:
        return "TX (Phone→Device)"
    elif rec_type == 0x03:
        return "RX (Device→Phone)"
    else:
        return f"type=0x{rec_type:02x}"

def main():
    records = parse_pklg('cap.pklg')
    print(f"Total records: {len(records)}")
    
    # Find all FE-framed records
    fe_records = []
    for rec in records:
        data = rec['data']
        # Check if data contains FE DC BA
        # Sometimes BLE records are fragmented, look for FE DC BA at any offset
        for start in range(len(data)):
            if start + 7 < len(data) and data[start] == 0xFE and data[start+1] == 0xDC and data[start+2] == 0xBA:
                # Find EF terminator
                for end in range(start + 7, len(data)):
                    if data[end] == 0xEF:
                        frame_data = data[start:end+1]
                        frame = parse_fe_frame(frame_data)
                        if frame:
                            fe_records.append({
                                'rec': rec,
                                'frame': frame,
                                'raw': frame_data
                            })
                        break
    
    print(f"\nTotal FE-framed records: {len(fe_records)}")
    
    # Print ALL frames in sequence
    print("\n" + "="*100)
    print("FULL PROTOCOL SEQUENCE")
    print("="*100)
    
    last_data_idx = -1
    for i, entry in enumerate(fe_records):
        f = entry['frame']
        r = entry['rec']
        direction = direction_str(r['type'])
        body_hex = ''.join(f'{b:02x}' for b in f['body'][:40])
        if len(f['body']) > 40:
            body_hex += '...'
        
        is_data = (f['flag'] == 0x80 and f['cmd'] == 0x01)
        marker = " <<<DATA>>>" if is_data else ""
        if is_data:
            last_data_idx = i
        
        print(f"[{i:3d}] {direction:24s} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} len={f['length']:5d}  body={body_hex}{marker}")
    
    # Now focus on what happens after the last data frame
    print("\n" + "="*100)
    print(f"AFTER LAST DATA FRAME (index {last_data_idx})")
    print("="*100)
    
    for i in range(max(0, last_data_idx - 2), len(fe_records)):
        entry = fe_records[i]
        f = entry['frame']
        r = entry['rec']
        direction = direction_str(r['type'])
        body_hex = ''.join(f'{b:02x}' for b in f['body'])
        
        marker = ""
        if i == last_data_idx:
            marker = " <<<LAST DATA FRAME>>>"
        elif i > last_data_idx:
            marker = " <<<POST-DATA>>>"
        
        print(f"\n[{i:3d}] {direction:24s} flag=0x{f['flag']:02x} cmd=0x{f['cmd']:02x} len={f['length']}")
        print(f"      body ({len(f['body'])} bytes): {body_hex}")
        print(f"      raw frame: {''.join(f'{b:02x}' for b in entry['raw'])}{marker}")

    # Also look at ALL raw records after the last data FE frame's record index
    if last_data_idx >= 0:
        last_data_rec_idx = fe_records[last_data_idx]['rec']['idx']
        print("\n" + "="*100)
        print(f"ALL RAW RECORDS AFTER last data record (rec idx {last_data_rec_idx})")
        print("="*100)
        for rec in records:
            if rec['idx'] >= last_data_rec_idx - 2:
                data_hex = ''.join(f'{b:02x}' for b in rec['data'][:80])
                if len(rec['data']) > 80:
                    data_hex += '...'
                print(f"  rec[{rec['idx']:4d}] type=0x{rec['type']:02x} ({direction_str(rec['type']):24s}) len={len(rec['data']):4d}  data={data_hex}")

if __name__ == '__main__':
    main()
