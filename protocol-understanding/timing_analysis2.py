#!/usr/bin/env python3
"""Analyze timing between data frames in the pklg capture.
   Apple PacketLogger uses big-endian uint64 timestamp in microseconds since 2001-01-01."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

# First, let's just dump raw timestamp bytes for the first few records to understand the format
off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    # Try different timestamp formats
    ts_le = struct.unpack_from('<Q', raw, off + 4)[0]
    ts_be = struct.unpack_from('>Q', raw, off + 4)[0]
    ts_bytes = raw[off+4:off+12]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({
        'idx': len(records), 'type': ptype, 'payload': payload,
        'ts_le': ts_le, 'ts_be': ts_be, 'ts_bytes': ts_bytes
    })
    off += 4 + rec_len
    if off > len(raw):
        break

# Show first few timestamps both ways
print("First 5 records timestamp bytes:")
for r in records[:5]:
    print(f"  rec {r['idx']}: type={r['type']} bytes={r['ts_bytes'].hex()} LE={r['ts_le']} BE={r['ts_be']}")

# Apple pklg uses big-endian microseconds since 2001-01-01
# Let's check: 2025 - 2001 = 24 years ≈ 24*365.25*24*3600 ≈ 757,382,400 seconds
# In microseconds: ~757,382,400,000,000 ≈ 0x2B1_06F8_6AAE_0000
# That's within uint64 range
print()

# Try BE timestamp interpretation
ts0_be = records[0]['ts_be']
print(f"First BE timestamp: {ts0_be} = 0x{ts0_be:016x}")
print(f"  As seconds since 2001: {ts0_be / 1_000_000:.0f}")
print(f"  As years since 2001: {ts0_be / 1_000_000 / 365.25 / 24 / 3600:.2f}")

ts0_le = records[0]['ts_le']
print(f"\nFirst LE timestamp: {ts0_le} = 0x{ts0_le:016x}")
print(f"  As seconds since 2001: {ts0_le / 1_000_000:.0f}")
print(f"  As years since 2001: {ts0_le / 1_000_000 / 365.25 / 24 / 3600:.2f}")

# One of them should give ~24 years
# Let's use the correct one
# Apple usually uses big-endian
if 20 < (ts0_be / 1_000_000 / 365.25 / 24 / 3600) < 30:
    print("\nUsing BIG-ENDIAN timestamps")
    ts_key = 'ts_be'
elif 20 < (ts0_le / 1_000_000 / 365.25 / 24 / 3600) < 30:
    print("\nUsing LITTLE-ENDIAN timestamps")
    ts_key = 'ts_le'
else:
    # Maybe it's in a different epoch or units
    # Try nanoseconds
    for key, label in [('ts_be', 'BE'), ('ts_le', 'LE')]:
        v = records[0][key]
        for unit_name, divisor in [('ns', 1_000_000_000), ('us', 1_000_000), ('ms', 1_000), ('s', 1)]:
            years = v / divisor / 365.25 / 24 / 3600
            if 20 < years < 30:
                print(f"\nUsing {label} timestamps in {unit_name} (years={years:.2f})")
                break
    # Just use BE/us as default
    ts_key = 'ts_be'
    print("Falling back to BE/us")

# Now do the actual analysis
print("\n=== TIMING ANALYSIS ===\n")

# Reconstruct FE frames with correct timestamps
current = None
fe_frames = []

for rec in records:
    if rec['type'] not in (2, 3): continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'dir': rec['type'], 'data': bytearray(p[8:]), 'expected': l2cap_len, 'ts': rec[ts_key], 'idx': rec['idx']}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    else:
        continue
    
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        direction = 'TX' if current['dir'] == 2 else 'RX'
        
        # Parse for FE-framed data
        if len(data) >= 3:
            att_val = data[3:] if len(data) > 3 else b''
            
            for idx in range(len(att_val)):
                if (idx + 7 < len(att_val) and 
                    att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                    flag = att_val[idx+3]
                    cmd = att_val[idx+4]
                    blen = (att_val[idx+5] << 8) | att_val[idx+6]
                    end = idx + 7 + blen
                    if end < len(att_val) and att_val[end] == 0xEF:
                        body = att_val[idx+7:end]
                        fe_frames.append({
                            'ts': current['ts'],
                            'dir': direction,
                            'flag': flag,
                            'cmd': cmd,
                            'body_len': blen,
                            'body': body,
                        })
                    break
        current = None

# Filter to data transfer events
transfer = []
for f in fe_frames:
    if f['flag'] == 0x80 and f['cmd'] == 0x01 and f['dir'] == 'TX':
        transfer.append(('DATA', f))
    elif f['flag'] == 0x80 and f['cmd'] == 0x1d:
        transfer.append(('WACK', f))
    elif f['cmd'] in (0x20, 0x1c):
        transfer.append((f'CMD_0x{f["cmd"]:02x}', f))

if not transfer:
    print("No transfer frames found!")
    exit()

t0 = transfer[0][1]['ts']
prev_ts = t0

for label, f in transfer:
    dt_ms = (f['ts'] - prev_ts) / 1000  # us to ms
    rel_ms = (f['ts'] - t0) / 1000
    
    extra = ""
    if label == 'DATA':
        seq = f['body'][0] if f['body'] else -1
        slot = f['body'][2] if len(f['body']) > 2 else -1
        data_len = len(f['body']) - 5 if len(f['body']) > 5 else 0
        extra = f"seq=0x{seq:02x} slot={slot} len={data_len}"
    elif label == 'WACK':
        if len(f['body']) >= 8:
            ack_seq = f['body'][0]
            win = (f['body'][2] << 8) | f['body'][3]
            off = (f['body'][4] << 24) | (f['body'][5] << 16) | (f['body'][6] << 8) | f['body'][7]
            extra = f"ackseq={ack_seq} win={win} off={off} dir={f['dir']}"
    else:
        extra = f"dir={f['dir']}"
    
    print(f"  {rel_ms:8.1f}ms  +{dt_ms:7.1f}ms  {label:8s} {extra}")
    prev_ts = f['ts']

# Stats for within-window data frame delays
data_only = [(l, f) for l, f in transfer if l == 'DATA']
if len(data_only) > 1:
    in_window_delays = []
    cross_window_delays = []
    for i in range(1, len(data_only)):
        dt = (data_only[i][1]['ts'] - data_only[i-1][1]['ts']) / 1000  # ms
        slot = data_only[i][1]['body'][2] if len(data_only[i][1]['body']) > 2 else 0
        if slot == 0:
            cross_window_delays.append(dt)
        else:
            in_window_delays.append(dt)
    
    print(f"\n=== WITHIN-WINDOW DELAYS ===")
    if in_window_delays:
        # Filter out obviously wrong values
        valid = [d for d in in_window_delays if -1000 < d < 10000]
        if valid:
            print(f"  Count:  {len(valid)}")
            print(f"  Min:    {min(valid):.1f} ms")
            print(f"  Max:    {max(valid):.1f} ms")
            print(f"  Mean:   {sum(valid)/len(valid):.1f} ms")
        else:
            print(f"  All delays seem invalid (timestamp parsing issue)")
            print(f"  Raw: {in_window_delays[:5]}")
    
    print(f"\n=== CROSS-WINDOW DELAYS (after ack wait) ===")
    if cross_window_delays:
        valid = [d for d in cross_window_delays if -1000 < d < 100000]
        if valid:
            print(f"  Count:  {len(valid)}")
            print(f"  Min:    {min(valid):.1f} ms")
            print(f"  Max:    {max(valid):.1f} ms")
            print(f"  Mean:   {sum(valid)/len(valid):.1f} ms")
