#!/usr/bin/env python3
"""Extract the JPEG file from the pklg capture data frames and save to disk."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

off = 0
records = []
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts = struct.unpack_from('<Q', raw, off + 4)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': len(records), 'type': ptype, 'payload': payload})
    off += 4 + rec_len
    if off > len(raw):
        break

# Reconstruct L2CAP frames and extract data
current = None
data_chunks = []  # list of (seq, file_data_bytes)

for rec in records:
    if rec['type'] not in (2, 3): continue
    p = rec['payload']
    if len(p) < 4: continue
    acl_hdr = struct.unpack_from('<H', p, 0)[0]
    flags = (acl_hdr >> 12) & 0x0F
    
    if flags == 0x00:
        if len(p) < 8: continue
        l2cap_len = struct.unpack_from('<H', p, 4)[0]
        current = {'dir': rec['type'], 'data': bytearray(p[8:]), 'expected': l2cap_len}
    elif flags == 0x01 and current:
        current['data'].extend(p[4:])
    else:
        continue
    
    if current and len(current['data']) >= current['expected']:
        data = bytes(current['data'][:current['expected']])
        if len(data) >= 3 and current['dir'] == 2:  # TX only
            op = data[0]
            if op == 0x52 and len(data) > 5:  # WriteWithoutResponse
                att_val = data[3:]
                for idx in range(len(att_val)):
                    if (idx + 7 < len(att_val) and 
                        att_val[idx] == 0xFE and att_val[idx+1] == 0xDC and att_val[idx+2] == 0xBA):
                        flag = att_val[idx+3]
                        cmd = att_val[idx+4]
                        blen = (att_val[idx+5] << 8) | att_val[idx+6]
                        end = idx + 7 + blen
                        if end < len(att_val) and att_val[end] == 0xEF:
                            body = att_val[idx+7:end]
                            if flag == 0x80 and cmd == 0x01 and len(body) >= 5:
                                seq = body[0]
                                slot = body[2]
                                file_data = bytes(body[5:])
                                data_chunks.append((seq, slot, file_data))
                        break
        current = None

print(f"Extracted {len(data_chunks)} data frames")

# The chunks are in seq order (0x06 to 0x25)
# But the LAST chunk (seq=0x25, slot=0) is actually the FIRST chunk of the file
# re-sent at offset 0. The file order is seq 0x06-0x24 (first 31 chunks)
# then the file data at offset 0 is a duplicate/verification.

# So the actual file is: chunks seq 0x06 through 0x24 in order
# seq 0x25 is the re-sent first chunk (verification), we skip it for reconstruction

# But actually, the file is reconstructed by taking chunks in ORDER of file offset,
# not in order of seq. The first 31 chunks (seq 0x06-0x24) contain the file in order.
# The 32nd (seq 0x25) is a duplicate of offset 0.

# Let's just take the first 31 chunks in seq order
file_chunks = data_chunks[:31]  # Skip the re-sent chunk

print(f"Using first {len(file_chunks)} chunks for file reconstruction")
for i, (seq, slot, data) in enumerate(file_chunks):
    print(f"  chunk {i}: seq=0x{seq:02x} slot={slot} data_len={len(data)} "
          f"preview={' '.join(f'{b:02x}' for b in data[:8])}")

# Concatenate file data
jpeg_data = b''.join(data for _, _, data in file_chunks)
print(f"\nTotal file size: {len(jpeg_data)} bytes")

# Check JPEG markers
if jpeg_data[:2] == b'\xff\xd8':
    print("✓ Starts with JPEG SOI marker (FF D8)")
else:
    print(f"✗ Does NOT start with JPEG SOI marker, starts with: {jpeg_data[:4].hex()}")

# Find JPEG EOI marker
eoi_pos = jpeg_data.rfind(b'\xff\xd9')
if eoi_pos >= 0:
    print(f"✓ JPEG EOI marker (FF D9) found at offset {eoi_pos} (of {len(jpeg_data)})")
    if eoi_pos + 2 < len(jpeg_data):
        print(f"  {len(jpeg_data) - eoi_pos - 2} bytes after EOI (padding/junk)")
else:
    print("✗ No JPEG EOI marker found")

# Save to disk
output_path = '/Users/herbst/git/bluetooth-tag/captured_image.jpg'
with open(output_path, 'wb') as f:
    f.write(jpeg_data)
print(f"\nSaved to: {output_path}")

# Also check the re-sent chunk matches the first chunk
if len(data_chunks) >= 32:
    resent = data_chunks[31][2]
    original = data_chunks[0][2]
    if resent == original:
        print(f"\n✓ Re-sent chunk (seq=0x25) matches original first chunk — verification passed")
    else:
        print(f"\n✗ Re-sent chunk differs from original!")
        print(f"  Original ({len(original)} bytes): {original[:16].hex()}")
        print(f"  Re-sent  ({len(resent)} bytes): {resent[:16].hex()}")

# Now let's check: the first chunk in the capture does NOT start with FF D8 (JFIF)
# because seq 0x06 has preview "44 45 46 47 48 49..." which is ASCII "DEFGHI..."
# That's the Huffman table continuation in JFIF.
# The re-sent chunk (seq 0x25) starts with "ff d8 ff e0" which IS the JFIF header.
# So maybe the file data is: re-sent chunk first, then chunks 0x06-0x24?
# NO — the re-sent chunk is at offset 0, meaning it IS the first 490 bytes.
# But chunk seq 0x06 would be offset 0 too (the first data frame sent).

# Let me check if chunk 0x06's data matches chunk 0x25's data
if len(data_chunks) >= 32:
    first_sent = data_chunks[0][2]  # seq 0x06
    resent = data_chunks[31][2]     # seq 0x25
    print(f"\nFirst sent chunk (seq=0x06): {first_sent[:16].hex()}")
    print(f"Re-sent chunk   (seq=0x25): {resent[:16].hex()}")
    
    if first_sent[:16] == resent[:16]:
        print("They match!")
    else:
        print("They differ — maybe the file order is different than expected")
        # Maybe seq 0x06 starts at offset 490 (second chunk)?
        # And seq 0x25 (the re-sent one) is the ACTUAL first chunk?
        # Let's reconstruct with seq 0x25 first, then 0x06-0x24
        
        alt_jpeg = resent + b''.join(data for _, _, data in data_chunks[:31])
        alt_path = '/Users/herbst/git/bluetooth-tag/captured_image_alt.jpg'
        with open(alt_path, 'wb') as f:
            f.write(alt_jpeg)
        print(f"  Alt reconstruction (resent first): {alt_path} ({len(alt_jpeg)} bytes)")
        if alt_jpeg[:2] == b'\xff\xd8':
            print(f"  ✓ Alt starts with JPEG SOI marker")
