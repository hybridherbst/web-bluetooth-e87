#!/usr/bin/env python3
"""Final data frame analysis."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

# Find ALL FE DC BA 80 01 sequences with any body length
seqs = []
for j in range(len(raw) - 8):
    if (raw[j] == 0xFE and raw[j+1] == 0xDC and raw[j+2] == 0xBA 
        and raw[j+3] == 0x80 and raw[j+4] == 0x01):
        length = (raw[j+5] << 8) | raw[j+6]
        if 3 < length < 600:
            body = raw[j+7:j+7+min(length, 10)]
            seqs.append({
                'off': j, 'len': length,
                'seq': body[0], 'b1': body[1], 'slot': body[2],
            })

print(f"All cmd 0x01 frames: {len(seqs)}")
for s in seqs:
    marker = "  <<<< SMALL" if s['len'] != 495 else ""
    print(f"  @0x{s['off']:06x} seq=0x{s['seq']:02x} b1=0x{s['b1']:02x} slot=0x{s['slot']:02x} body_len={s['len']}{marker}")

# The b1=0x1D constant tells us these are real data frames
# Some might be false positives from JPEG data containing FE DC BA

# Check which have b1 == 0x1D (real data frames)
real_data = [s for s in seqs if s['b1'] == 0x1d]
print(f"\nReal data frames (b1=0x1d): {len(real_data)}")
for s in real_data:
    marker = "  <<<< SMALL" if s['len'] != 495 else ""
    print(f"  @0x{s['off']:06x} seq=0x{s['seq']:02x} slot=0x{s['slot']:02x} body_len={s['len']}{marker}")

# Count total payload bytes
total = sum(s['len'] - 3 for s in real_data)
print(f"\nTotal payload: {total} bytes")
print(f"File size from metadata: 7997 = 0x1f3d")
print(f"Payload per full frame: 492")
print(f"Expected frames: ceil(7997/492) = {(7997+491)//492}")

# Check the FEDC BA 80 01 01 EF pattern
# In record 1614, we see: 52 06 00 FE DC BA 80 01 01 EF
# That's ATT Write Without Response (opcode 0x52, handle 0x0006)
# Then: 06 1D 00 ... (body starts)
# But the "01 EF" is suspicious — maybe body[0] contains the len?
# Actually the FE frame says: FE DC BA 80 01 [01 EF] 06 1D 00 ...
# len = (0x01 << 8) | 0xEF = 0x01EF = 495
# So len=495 is correct. body starts at 06.

# Actually wait: let me recheck. FE DC BA [flag=80] [cmd=01] [len_hi=01] [len_lo=EF]
# So length = 0x01EF = 495
# That means each data frame body = 495 bytes = 3 header + 492 JPEG data
# 7997 / 492 = 16.25 -> 17 frames
# But we found 32 with b1=0x1D? That means some are false positives from within fragmented HCI data

# Let me check the positions relative to window acks
wa_offsets = []
for j in range(len(raw) - 7):
    if (raw[j] == 0xFE and raw[j+1] == 0xDC and raw[j+2] == 0xBA
        and raw[j+3] == 0x80 and raw[j+4] == 0x1D):
        length = (raw[j+5] << 8) | raw[j+6]
        if length == 8:
            body = raw[j+7:j+15]
            wa_offsets.append({'off': j, 'body': body})
            
print(f"\nWindow acks at offsets:")
for wa in wa_offsets:
    body_hex = ' '.join(f'{b:02x}' for b in wa['body'])
    print(f"  @0x{wa['off']:06x} body: {body_hex}")

# Map data frames between window acks
print(f"\nData frames per window:")
wa_file_offsets = [wa['off'] for wa in wa_offsets]
for i in range(len(wa_file_offsets)):
    start = wa_file_offsets[i]
    end = wa_file_offsets[i+1] if i+1 < len(wa_file_offsets) else len(raw)
    frames_in_window = [s for s in real_data if start < s['off'] < end]
    print(f"  Window {i}: {len(frames_in_window)} frames between @0x{start:06x} and @0x{end:06x}")
    for f in frames_in_window:
        print(f"    seq=0x{f['seq']:02x} slot=0x{f['slot']:02x} len={f['len']}")

# Summary
print(f"\n{'='*60}")
print("PROTOCOL SUMMARY")
print(f"{'='*60}")
print(f"cmd 0x06 body: 00 01 (2 bytes, flag=0xC0)")
print(f"cmd 0x03 body: 01 FF FF FF FF 01 (seq=1)")
print(f"cmd 0x07 body: 02 FF FF FF FF FF (seq=2)")
print(f"cmd 0x21 body: 03 00 (seq=3, begin upload)")
print(f"cmd 0x27 body: 04 00 00 00 00 02 01 (seq=4, transfer params)")
print(f"cmd 0x1b body: 05 00 00 3D 1F ... (seq=5, file metadata)")
print(f"Data starts at seq=0x06, each body = [seq, 0x1D, slot, payload...]")
print(f"Window = 8 frames, slot cycles 0-7")
print(f"After all data:")
print(f"  cmd 0x20 TX: flag=0xC0, body = [next_seq] (1 byte)")
print(f"  cmd 0x20 RX: flag=0x00, body = [00, seq, path...]")
print(f"  cmd 0x1C TX: flag=0xC0, body = [next_seq, 00] (2 bytes)")
print(f"  cmd 0x1C RX: flag=0x00, body = [00, seq]")
