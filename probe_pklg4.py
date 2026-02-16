#!/usr/bin/env python3
"""Count FE DC BA data frames by scanning across record boundaries."""
import struct

path = '/Users/herbst/git/bluetooth-tag/cap.pklg'
raw = open(path, 'rb').read()

# First, reconstruct the full BLE data stream by concatenating payloads in order
records = []
pos = 0
while pos + 13 < len(raw):
    rec_len = struct.unpack('<I', raw[pos:pos+4])[0]
    if rec_len < 9 or rec_len > 100000 or pos + 4 + rec_len > len(raw):
        break
    ts = struct.unpack('<Q', raw[pos+4:pos+12])[0]
    pkt_type = raw[pos+12]
    payload = raw[pos+13:pos+4+rec_len]
    records.append({'ts': ts, 'type': pkt_type, 'payload': bytes(payload)})
    pos += 4 + rec_len

print(f"Total records: {len(records)}")

# The FE DC BA frames span multiple HCI records because the BLE MTU fragments them.
# Instead of trying to reassemble, let's just count ALL FE DC BA sequences in the raw file
# that have valid structure.

# But the 0x01 data frames ARE detected by the probe script — it found frames at specific offsets
# between window acks. It found them as RX records. Let me look at that differently.

# Let me search for ALL FEDC BA80 01 (data frames) in raw file
data_frame_offsets = []
for j in range(len(raw) - 7):
    if raw[j] == 0xFE and raw[j+1] == 0xDC and raw[j+2] == 0xBA and raw[j+3] == 0x80 and raw[j+4] == 0x01:
        length = (raw[j+5] << 8) | raw[j+6]
        body_end = j + 7 + length
        if body_end < len(raw) and raw[body_end] == 0xEF:
            body = raw[j+7:body_end]
            data_frame_offsets.append({
                'offset': j,
                'length': length,
                'seq': body[0] if len(body) > 0 else -1,
                'b1': body[1] if len(body) > 1 else -1,
                'b2': body[2] if len(body) > 2 else -1,
                'payload_len': len(body) - 3 if len(body) >= 3 else 0,
            })

print(f"Data frames (FEDC BA80 01 with valid EF): {len(data_frame_offsets)}")

if data_frame_offsets:
    print("\nFirst 10:")
    for i, f in enumerate(data_frame_offsets[:10]):
        print(f"  [{i:3d}] @0x{f['offset']:06x} len={f['length']} seq=0x{f['seq']:02x} b1=0x{f['b1']:02x} b2=0x{f['b2']:02x} payload={f['payload_len']}")
    
    print(f"\nLast 5:")
    for i in range(max(0, len(data_frame_offsets)-5), len(data_frame_offsets)):
        f = data_frame_offsets[i]
        print(f"  [{i:3d}] @0x{f['offset']:06x} len={f['length']} seq=0x{f['seq']:02x} b1=0x{f['b1']:02x} b2=0x{f['b2']:02x} payload={f['payload_len']}")
    
    total_payload = sum(f['payload_len'] for f in data_frame_offsets)
    print(f"\nTotal payload bytes: {total_payload}")
    print(f"File size from metadata: 7997")
    
    # Seq counter pattern
    seqs = [f['seq'] for f in data_frame_offsets]
    print(f"\nSeq progression: {seqs[:20]}...")
    
    # b1 pattern (should be 0x1d based on our code)
    b1s = set(f['b1'] for f in data_frame_offsets)
    print(f"Unique b1 values: {[f'0x{x:02x}' for x in sorted(b1s)]}")
    
    # b2 (slot) pattern
    b2s = [f['b2'] for f in data_frame_offsets]
    print(f"b2 (slot) pattern: {b2s[:20]}...")
    
    # Chunk size distribution
    sizes = [f['payload_len'] for f in data_frame_offsets]
    from collections import Counter
    print(f"Payload size distribution: {dict(Counter(sizes).most_common(5))}")
else:
    # Data frames might use different flag or the EF terminator is fragmented
    # Let's look for just FE DC BA 80 01 without checking EF
    print("\nSearching for FEDC BA80 01 without EF check...")
    count = 0
    for j in range(len(raw) - 7):
        if raw[j] == 0xFE and raw[j+1] == 0xDC and raw[j+2] == 0xBA and raw[j+3] == 0x80 and raw[j+4] == 0x01:
            length = (raw[j+5] << 8) | raw[j+6]
            body_start = j + 7
            if length > 0 and length < 1000:
                body = raw[body_start:min(body_start+16, len(raw))]
                hex_body = ' '.join(f'{b:02x}' for b in body)
                count += 1
                if count <= 10:
                    print(f"  @0x{j:06x} claimed_len={length} first_bytes: {hex_body}")
    print(f"Total FEDC BA80 01 sequences: {count}")

# Also look for records between the window ack file offsets
# Window ack offsets from earlier:
wa_offsets = [0x00f343, 0x010667, 0x01191b, 0x012bbb, 0x013bbc]
print(f"\nBytes between window acks:")
for i in range(len(wa_offsets) - 1):
    span = wa_offsets[i+1] - wa_offsets[i]
    print(f"  WA[{i+1}] to WA[{i+2}]: {span} bytes of file")
print(f"  WA[0] to first WA: @0x{wa_offsets[0]:x}")

# How many records between window ack records?
wa_record_indices = [1613, 1655, 1693, 1730, 1760]
for i in range(len(wa_record_indices) - 1):
    r1 = wa_record_indices[i]
    r2 = wa_record_indices[i+1]
    num_between = r2 - r1 - 1
    tx_count = sum(1 for j in range(r1+1, r2) if records[j]['type'] == 0x00)
    rx_count = sum(1 for j in range(r1+1, r2) if records[j]['type'] == 0x01)
    total_tx_bytes = sum(len(records[j]['payload']) for j in range(r1+1, r2) if records[j]['type'] == 0x00)
    total_rx_bytes = sum(len(records[j]['payload']) for j in range(r1+1, r2) if records[j]['type'] == 0x01)
    print(f"  Between WA[{i}] rec[{r1}] and WA[{i+1}] rec[{r2}]: {num_between} records (TX={tx_count}/{total_tx_bytes}B, RX={rx_count}/{total_rx_bytes}B)")

# Look at the actual TX data in these windows - maybe data is NOT FE-framed
# and is sent raw to AE01
print(f"\n{'='*70}")
print("TX PAYLOADS between WA[0] and WA[1]")
print(f"{'='*70}")
r1 = wa_record_indices[0]
r2 = wa_record_indices[1]
for i in range(r1+1, r2):
    rec = records[i]
    if rec['type'] == 0x00:
        pl = rec['payload']
        hex_data = ' '.join(f'{b:02x}' for b in pl[:min(40, len(pl))])
        if len(pl) > 40:
            hex_data += '...'
        print(f"  rec[{i}] TX len={len(pl)} {hex_data}")

print(f"\n{'='*70}")
print("DETAILED: Records around window ack 0")
print(f"{'='*70}")
wa0 = wa_record_indices[0]
for i in range(wa0 - 2, min(wa0 + 15, len(records))):
    rec = records[i]
    pl = rec['payload']
    direction = "TX" if rec['type'] == 0x00 else "RX"
    hex_data = ' '.join(f'{b:02x}' for b in pl[:min(50, len(pl))])
    if len(pl) > 50:
        hex_data += '...'
    
    marker = " <<<WA0" if i == wa0 else ""
    print(f"  rec[{i}] type=0x{rec['type']:02x} ({direction}) len={len(pl)} {hex_data}{marker}")
