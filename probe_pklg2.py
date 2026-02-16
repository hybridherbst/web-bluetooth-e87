#!/usr/bin/env python3
"""Deep analysis of data transfer between window acks in pklg capture."""
import struct

path = '/Users/herbst/git/bluetooth-tag/cap.pklg'
data = open(path, 'rb').read()

# Parse records with LE format
records = []
pos = 0
while pos + 13 < len(data):
    rec_len = struct.unpack('<I', data[pos:pos+4])[0]
    if rec_len < 9 or rec_len > 100000 or pos + 4 + rec_len > len(data):
        break
    ts = struct.unpack('<Q', data[pos+4:pos+12])[0]
    pkt_type = data[pos+12]
    payload = data[pos+13:pos+4+rec_len]
    records.append({
        'offset': pos,
        'ts': ts,
        'type': pkt_type,
        'payload': bytes(payload),
    })
    pos += 4 + rec_len

print(f"Total records: {len(records)}")

# Find the record offsets that contain FE DC BA frames
fe_record_indices = set()
for i, rec in enumerate(records):
    pl = rec['payload']
    for j in range(len(pl) - 6):
        if pl[j] == 0xFE and pl[j+1] == 0xDC and pl[j+2] == 0xBA:
            fe_record_indices.add(i)

# Find first FE DC BA frame (cmd 0x06 = start of upload)
first_fe = min(fe_record_indices)
# Find the window ack records
window_ack_records = []
for i, rec in enumerate(records):
    pl = rec['payload']
    for j in range(len(pl) - 6):
        if pl[j] == 0xFE and pl[j+1] == 0xDC and pl[j+2] == 0xBA:
            cmd = pl[j+4]
            if cmd == 0x1d:
                window_ack_records.append(i)

print(f"First FE record: {first_fe}")
print(f"Window ack records: {window_ack_records}")

# Analyze records between first window ack and second window ack
# The first window ack is after cmd 0x1b metadata
# Data transfer happens between window acks

# Find cmd 0x1b record
meta_record = None
for i, rec in enumerate(records):
    pl = rec['payload']
    for j in range(len(pl) - 6):
        if pl[j] == 0xFE and pl[j+1] == 0xDC and pl[j+2] == 0xBA:
            if pl[j+4] == 0x1b and pl[j+3] == 0xc0:
                meta_record = i
                break

print(f"Metadata cmd 0x1b TX record: {meta_record}")

# Now let's look at records between first and second window acks
if len(window_ack_records) >= 2:
    wa1 = window_ack_records[0]
    wa2 = window_ack_records[1]
    print(f"\nRecords between first window ack [{wa1}] and second [{wa2}]:")
    print(f"Count: {wa2 - wa1 - 1}")
    
    for i in range(wa1, min(wa2 + 1, wa1 + 25)):
        rec = records[i]
        pl = rec['payload']
        direction = "TX" if rec['type'] == 0x00 else "RX"
        hex_first = ' '.join(f'{b:02x}' for b in pl[:min(30, len(pl))])
        if len(pl) > 30:
            hex_first += '...'
        
        # Check if this is a FE frame
        is_fe = False
        for j in range(len(pl) - 6):
            if pl[j] == 0xFE and pl[j+1] == 0xDC and pl[j+2] == 0xBA:
                flag = pl[j+3]
                cmd = pl[j+4]
                blen = (pl[j+5] << 8) | pl[j+6]
                print(f"  [{i:4d}] {direction} len={len(pl):4d}  FE_FRAME flag=0x{flag:02x} cmd=0x{cmd:02x} body_len={blen}")
                is_fe = True
                break
        
        if not is_fe:
            print(f"  [{i:4d}] {direction} len={len(pl):4d}  raw: {hex_first}")

# Look at the raw data sent between window acks - these are likely the data chunks
# sent on AE01 without FE framing
print(f"\n{'='*60}")
print("DEEP ANALYSIS: TX records between first two window acks")
print(f"{'='*60}")

if len(window_ack_records) >= 2:
    wa1 = window_ack_records[0]
    wa2 = window_ack_records[1]
    
    tx_records = []
    for i in range(wa1 + 1, wa2):
        rec = records[i]
        if rec['type'] == 0x00:  # TX
            tx_records.append((i, rec))
    
    print(f"TX records in first window: {len(tx_records)}")
    for idx, (i, rec) in enumerate(tx_records[:10]):
        pl = rec['payload']
        hex_data = ' '.join(f'{b:02x}' for b in pl[:min(40, len(pl))])
        if len(pl) > 40:
            hex_data += '...'
        print(f"  TX[{idx}] rec[{i}] len={len(pl)}  {hex_data}")

# Now check: maybe the data IS in FE frames but with cmd != 0x01
# Let's look at ALL FE frames between window acks
print(f"\n{'='*60}")
print("ALL records between meta ack and last window ack") 
print(f"{'='*60}")

if meta_record and window_ack_records:
    # Get the record after meta ack
    meta_ack_rec = None
    for i, rec in enumerate(records):
        pl = rec['payload']
        for j in range(len(pl) - 6):
            if pl[j] == 0xFE and pl[j+1] == 0xDC and pl[j+2] == 0xBA:
                if pl[j+4] == 0x1b and pl[j+3] == 0x00:  # RX ack for 0x1b
                    meta_ack_rec = i
    
    start_rec = meta_ack_rec or meta_record
    end_rec = window_ack_records[-1] + 5  # include some after last window ack
    end_rec = min(end_rec, len(records))
    
    # Count and analyze TX payloads that are NOT FE frames
    non_fe_tx = 0
    total_non_fe_bytes = 0
    
    for i in range(start_rec, end_rec):
        rec = records[i]
        pl = rec['payload']
        direction = "TX" if rec['type'] == 0x00 else "RX"
        
        has_fe = False
        for j in range(len(pl) - 6):
            if pl[j] == 0xFE and pl[j+1] == 0xDC and pl[j+2] == 0xBA:
                has_fe = True
                break
        
        if not has_fe and rec['type'] == 0x00 and len(pl) > 5:
            non_fe_tx += 1
            total_non_fe_bytes += len(pl)
    
    print(f"Non-FE TX records: {non_fe_tx}")
    print(f"Total non-FE TX bytes: {total_non_fe_bytes}")

# The key insight: look at what's actually being sent via BLE writes
# In HCI, ATT write commands are opcode 0x52 (write without response) or 0x12 (write request)
# The ATT data starts after HCI ACL header + L2CAP header
# HCI ACL: handle(2 LE) + len(2 LE)
# L2CAP:   len(2 LE) + CID(2 LE)   CID=0x0004 for ATT
# ATT:     opcode(1) + handle(2 LE) + data...
# Write without response: opcode=0x52
# Write request: opcode=0x12

print(f"\n{'='*60}")
print("ATT WRITE ANALYSIS (looking for opcode 0x52 or 0x12)")
print(f"{'='*60}")

# For TX records (type=0x00), the payload should be HCI ACL data
att_writes = []
for i, rec in enumerate(records):
    pl = rec['payload']
    if rec['type'] != 0x00:
        continue
    if len(pl) < 9:
        continue
    
    # HCI ACL: handle(2) + total_len(2)
    # L2CAP: l2cap_len(2) + cid(2)
    # ATT: opcode(1) + att_handle(2) + data...
    
    # The payload in pklg might be raw HCI or might skip the HCI header
    # Let's look for ATT opcode at various offsets
    for att_off in range(len(pl) - 3):
        if pl[att_off] in (0x52, 0x12):  # Write without response / Write request
            att_handle = struct.unpack_from('<H', pl, att_off + 1)[0]
            att_data = pl[att_off + 3:]
            if 0x0001 <= att_handle <= 0x00ff and len(att_data) > 0:
                att_writes.append({
                    'rec_idx': i,
                    'att_off': att_off,
                    'handle': att_handle,
                    'data': bytes(att_data),
                    'opcode': pl[att_off],
                })
                break

# Group by ATT handle
handle_counts = {}
for w in att_writes:
    h = w['handle']
    handle_counts[h] = handle_counts.get(h, 0) + 1

print(f"ATT writes by handle: {', '.join(f'0x{h:04x}: {c}' for h, c in sorted(handle_counts.items()))}")

# Look at writes to the most-used handle (likely AE01 data)
if handle_counts:
    main_handle = max(handle_counts, key=handle_counts.get)
    main_writes = [w for w in att_writes if w['handle'] == main_handle]
    print(f"\nMost-used handle: 0x{main_handle:04x} ({len(main_writes)} writes)")
    
    # Show first few
    for idx, w in enumerate(main_writes[:10]):
        d = w['data']
        hex_data = ' '.join(f'{b:02x}' for b in d[:min(30, len(d))])
        if len(d) > 30:
            hex_data += '...'
        print(f"  Write[{idx:3d}] rec[{w['rec_idx']}] opcode=0x{w['opcode']:02x} data_len={len(d)} {hex_data}")
    
    print("  ...")
    
    for idx in range(max(0, len(main_writes) - 5), len(main_writes)):
        w = main_writes[idx]
        d = w['data']
        hex_data = ' '.join(f'{b:02x}' for b in d[:min(30, len(d))])
        if len(d) > 30:
            hex_data += '...'
        print(f"  Write[{idx:3d}] rec[{w['rec_idx']}] opcode=0x{w['opcode']:02x} data_len={len(d)} {hex_data}")
    
    # Analyze the data pattern
    # After the FE-framed setup, data chunks should start
    # Find where FE frames end and raw data begins
    fe_write_indices = set()
    for w in main_writes:
        d = w['data']
        if len(d) >= 7 and d[0] == 0xFE and d[1] == 0xDC and d[2] == 0xBA:
            fe_write_indices.add(w['rec_idx'])
    
    # Find writes that are NOT FE frames on this handle
    non_fe_writes = [w for w in main_writes if w['rec_idx'] not in fe_write_indices and not (len(w['data']) >= 3 and w['data'][0] == 0xFE and w['data'][1] == 0xDC)]
    print(f"\nNon-FE writes on handle 0x{main_handle:04x}: {len(non_fe_writes)}")
    
    if non_fe_writes:
        # These are the raw data chunks!
        print(f"First 5 non-FE writes:")
        for idx, w in enumerate(non_fe_writes[:5]):
            d = w['data']
            hex_data = ' '.join(f'{b:02x}' for b in d[:min(30, len(d))])
            if len(d) > 30:
                hex_data += '...'
            print(f"  [{idx:3d}] rec[{w['rec_idx']}] len={len(d)} {hex_data}")
        
        print(f"Last 5 non-FE writes:")
        for idx in range(max(0, len(non_fe_writes) - 5), len(non_fe_writes)):
            w = non_fe_writes[idx]
            d = w['data']
            hex_data = ' '.join(f'{b:02x}' for b in d[:min(30, len(d))])
            if len(d) > 30:
                hex_data += '...'
            print(f"  [{idx:3d}] rec[{w['rec_idx']}] len={len(d)} {hex_data}")
        
        total_data = sum(len(w['data']) for w in non_fe_writes)
        print(f"Total non-FE data: {total_data} bytes")
