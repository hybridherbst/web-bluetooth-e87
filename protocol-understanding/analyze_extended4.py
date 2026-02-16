#!/usr/bin/env python3
"""
Deep analysis: look at the raw bytes of "data" writes.
They start with FE DC BA 80 01 01 EF ... which looks like
a short E87 frame followed by raw data in the same ATT write.
"""
import struct

def parse_pklg(path):
    raw = open(path, 'rb').read()
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
        if off > len(raw):
            break
    return records

records = parse_pklg('/Users/herbst/git/bluetooth-tag/cap-extended.pklg')

# Find all AE01 TX writes in session 1 timeframe
sess1_start = 1771267414.0
sess1_end = 1771267494.0

count = 0
for r in records:
    if r['type'] != 2:  # TX
        continue
    p = r['payload']
    if len(p) < 12:
        continue
    att_op = p[8]
    att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
    if att_handle != 0x0006:
        continue
    if not (sess1_start <= r['ts'] <= sess1_end):
        continue
    att_value = p[11:]
    
    count += 1
    if count <= 20:
        # Show first 40 bytes of value
        hx = att_value[:60].hex()
        # Check if it starts with FE DC BA
        if att_value[:3] == b'\xfe\xdc\xba':
            flag = att_value[3]
            cmd = att_value[4]
            blen = (att_value[5] << 8) | att_value[6]
            # Check for EF byte
            ef_pos = None
            if blen + 7 < len(att_value) and att_value[blen + 7] == 0xef:
                ef_pos = blen + 7
            elif len(att_value) > 7 and att_value[7] == 0xef:
                ef_pos = 7
            
            print(f"[{count:4d}] ts={r['ts']:.3f} len={len(att_value):>4d} FE-DC-BA flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen} ef@{ef_pos}")
            
            # If there's data after the E87 frame...
            if ef_pos is not None and ef_pos + 1 < len(att_value):
                after = att_value[ef_pos+1:]
                print(f"       After EF ({len(after)} bytes): {after[:40].hex()}")
        else:
            print(f"[{count:4d}] ts={r['ts']:.3f} len={len(att_value):>4d} {hx}")
    
    if count == 20:
        print("... (showing first 20, looking for patterns)")
        break

# Now let's understand the REAL structure
# Look at the first "raw" data write more carefully
print("\n\n=== Examining long writes in detail ===")
count = 0
for r in records:
    if r['type'] != 2:
        continue
    p = r['payload']
    if len(p) < 12:
        continue
    att_op = p[8]
    att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
    if att_handle != 0x0006:
        continue
    if not (sess1_start <= r['ts'] <= sess1_end):
        continue
    att_value = p[11:]
    
    if len(att_value) > 100:  # Long write
        count += 1
        if count <= 5:
            # Parse E87 header
            if att_value[:3] == b'\xfe\xdc\xba':
                flag = att_value[3]
                cmd = att_value[4]
                blen = (att_value[5] << 8) | att_value[6]
                body = att_value[7:7+blen]
                ef_idx = 7 + blen
                
                print(f"\nLong write #{count}: total={len(att_value)} bytes")
                print(f"  E87: flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen}")
                print(f"  body: {body.hex()}")
                if ef_idx < len(att_value):
                    print(f"  byte[{ef_idx}]=0x{att_value[ef_idx]:02x} (should be EF)")
                    after = att_value[ef_idx+1:]
                    print(f"  After EF: {len(after)} bytes")
                    print(f"  After first 40: {after[:40].hex()}")
                    print(f"  After last 20: {after[-20:].hex()}")
                    
                    # Check if there's ANOTHER E87 frame in the after data
                    for i in range(len(after) - 3):
                        if after[i:i+3] == b'\xfe\xdc\xba':
                            print(f"  *** Found another FE DC BA at offset {i} in after-data! ***")
                            f2 = after[i+3]
                            c2 = after[i+4]
                            bl2 = (after[i+5] << 8) | after[i+6]
                            print(f"      flag=0x{f2:02x} cmd=0x{c2:02x} blen={bl2}")
                            break
