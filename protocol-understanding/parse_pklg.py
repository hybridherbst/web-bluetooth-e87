#!/usr/bin/env python3
"""Parse Apple PacketLogger (.pklg) capture to find auth exchange data."""
import struct

def parse_pklg(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    print(f"File size: {len(data)} bytes")
    print(f"First 32 bytes: {' '.join(f'{b:02x}' for b in data[:32])}")
    
    # Apple PacketLogger format:
    # Each record: 4-byte length (big-endian), 4-byte timestamp, 1-byte type, N-byte data
    # OR: 4-byte length (little-endian), 8-byte timestamp, 1-byte type, N-byte data
    
    # Try to find the format
    records = []
    pos = 0
    
    # Try Apple PacketLogger format: each record is:
    # uint32 len (of remaining data after len field)
    # uint32 ts_secs
    # uint32 ts_usecs (or just 8 bytes of timestamp)
    # uint8 type
    # payload...
    
    while pos + 4 < len(data):
        # Try big-endian length
        rec_len = struct.unpack('>I', data[pos:pos+4])[0]
        if rec_len > 0 and rec_len < 10000 and pos + 4 + rec_len <= len(data):
            rec_data = data[pos+4:pos+4+rec_len]
            if len(rec_data) >= 9:  # at least timestamp(8) + type(1)
                ts = struct.unpack('>Q', rec_data[:8])[0]
                pkt_type = rec_data[8]
                payload = rec_data[9:]
                records.append((pos, rec_len, ts, pkt_type, payload))
            pos += 4 + rec_len
        else:
            break
    
    if len(records) < 5:
        # Try different format: length includes itself
        records = []
        pos = 0
        while pos + 4 < len(data):
            rec_len = struct.unpack('>I', data[pos:pos+4])[0]
            actual_payload_len = rec_len - 4
            if actual_payload_len > 0 and actual_payload_len < 10000 and pos + rec_len <= len(data):
                rec_data = data[pos+4:pos+rec_len]
                if len(rec_data) >= 9:
                    ts = struct.unpack('>Q', rec_data[:8])[0]
                    pkt_type = rec_data[8]
                    payload = rec_data[9:]
                    records.append((pos, rec_len, ts, pkt_type, payload))
                pos += rec_len
            else:
                break
    
    print(f"Records found: {len(records)}")
    
    # Print all records to understand the format
    auth_data = []
    for i, (offset, length, ts, pkt_type, payload) in enumerate(records):
        if len(payload) < 4:
            continue
        
        # Look for ATT data
        # HCI ACL: type=0x02 in HCI, or type=0x00/0x01 in PacketLogger (sent/recv)
        hex_payload = ' '.join(f'{b:02x}' for b in payload[:min(30, len(payload))])
        
        # Search for 17-byte sequences with first byte 0x00 or 0x01
        # in the raw payload
        for j in range(len(payload)):
            remaining = len(payload) - j
            if remaining >= 17 and payload[j] in (0x00, 0x01):
                # Check if this looks like auth data (not all zeros)
                candidate = payload[j:j+17]
                nonzero = sum(1 for b in candidate[1:] if b != 0)
                if nonzero >= 3:  # at least some non-zero data bytes
                    hex_val = ' '.join(f'{b:02x}' for b in candidate)
                    type_name = {0: "random", 1: "encrypted"}.get(candidate[0], "?")
                    print(f"  [{i:4d}] pkttype=0x{pkt_type:02x} offset={offset} +{j}: {hex_val}  ({type_name})")
                    auth_data.append((i, pkt_type, list(candidate)))
            
            # Also look for "pass" pattern
            if remaining >= 5 and payload[j] == 0x02:
                candidate = payload[j:j+5]
                if candidate == bytes([0x02, 0x70, 0x61, 0x73, 0x73]):
                    hex_val = ' '.join(f'{b:02x}' for b in candidate)
                    print(f"  [{i:4d}] pkttype=0x{pkt_type:02x} offset={offset} +{j}: {hex_val}  (AUTH PASS!)")
                    auth_data.append((i, pkt_type, list(candidate)))
    
    # Also try scanning raw file for auth patterns
    print(f"\n=== Raw scan for auth patterns ===")
    for j in range(len(data)):
        # Look for "pass" pattern
        if j + 5 <= len(data) and data[j:j+5] == bytes([0x02, 0x70, 0x61, 0x73, 0x73]):
            context_start = max(0, j-20)
            context = ' '.join(f'{b:02x}' for b in data[context_start:j+10])
            print(f"  'pass' found at offset 0x{j:x}: ...{context}...")
    
    return auth_data


def scan_raw_for_auth(path):
    """Brute-force scan for auth-like patterns in the file."""
    with open(path, 'rb') as f:
        data = f.read()
    
    print(f"\n=== Scanning {path} ({len(data)} bytes) for 17-byte auth patterns ===")
    
    # Look for "pass" 
    for j in range(len(data) - 4):
        if data[j:j+5] == bytes([0x02, 0x70, 0x61, 0x73, 0x73]):
            ctx = ' '.join(f'{b:02x}' for b in data[max(0,j-30):j+30])
            print(f"  'pass' at offset 0x{j:x}: {ctx}")
    
    # Find FE DC BA frames
    fe_count = 0
    for j in range(len(data) - 2):
        if data[j] == 0xFE and data[j+1] == 0xDC and data[j+2] == 0xBA:
            fe_count += 1
            if fe_count <= 5:
                ctx = ' '.join(f'{b:02x}' for b in data[j:min(j+30, len(data))])
                print(f"  FE DC BA frame at 0x{j:x}: {ctx}...")
    print(f"  Total FE DC BA frames: {fe_count}")


if __name__ == '__main__':
    print("=== Parsing cap.pklg ===")
    parse_pklg('cap.pklg')
    scan_raw_for_auth('cap.pklg')
    
    print("\n" + "="*60)
    scan_raw_for_auth('cap.btsnoop')
