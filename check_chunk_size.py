#!/usr/bin/env python3
"""Check the actual FE body length field vs available bytes in first data frame."""
import struct

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()
off = 0
records = []
rec_idx = 0
while off + 13 <= len(raw):
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_secs = struct.unpack_from('<I', raw, off+4)[0]
    ts_usecs = struct.unpack_from('<I', raw, off+8)[0]
    ptype = raw[off + 12]
    payload = raw[off + 13:off + 13 + rec_len - 9]
    records.append({'idx': rec_idx, 'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6, 'rec_len': rec_len})
    rec_idx += 1
    off += 4 + rec_len
    if off > len(raw):
        break

found = 0
for r in records:
    if r['type'] != 2:
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd == 0x01 and flag == 0x80:
                avail = len(p) - (idx + 7)
                print(f"Record {r['idx']}: rec_len={r['rec_len']} payload_len={len(p)}")
                print(f"  FE header at offset {idx}")
                print(f"  flag=0x{flag:02x} cmd=0x{cmd:02x} blen={blen} (0x{blen:04x})")
                print(f"  Available body bytes: {avail}")
                print(f"  TRUNCATED: {avail < blen}")
                if avail < blen:
                    print(f"  Missing: {blen - avail} bytes")
                    # Check if the FE frame spans across BLE segments
                    # L2CAP length should tell us the real size
                    if len(p) >= 6:
                        hci_handle = (p[0] | (p[1]<<8)) & 0x0fff
                        hci_pb = (p[1] >> 4) & 0x03
                        hci_len = p[2] | (p[3]<<8)
                        l2cap_len = p[4] | (p[5]<<8)
                        l2cap_cid = p[6] | (p[7]<<8)
                        print(f"  HCI: handle=0x{hci_handle:04x} pb={hci_pb} hci_len={hci_len}")
                        print(f"  L2CAP: len={l2cap_len} cid=0x{l2cap_cid:04x}")
                        att_op = p[8] if len(p) > 8 else 0
                        att_handle = (p[9] | (p[10]<<8)) if len(p) > 10 else 0
                        print(f"  ATT: op=0x{att_op:02x} handle=0x{att_handle:04x}")
                        print(f"  ATT payload length (from L2CAP): {l2cap_len - 3}")
                        print(f"  Expected FE frame total: {3+1+1+2+blen+1} = {3+1+1+2+blen+1} bytes")
                print()
                found += 1
                if found >= 3:
                    break
    if found >= 3:
        break

# Also check: the FILE_META 0x1b ack: body = 000501ea
# byte[0]=0x00 status, byte[1]=0x05 seq, byte[2:4] = 0x01ea = 490
# This is the chunk size the device tells us to use!
print("\n=== 0x1b ACK ANALYSIS ===")
for r in records:
    if r['type'] != 3:
        continue
    p = r['payload']
    for idx in range(len(p) - 7):
        if p[idx] == 0xFE and p[idx+1] == 0xDC and p[idx+2] == 0xBA:
            flag = p[idx+3]
            cmd = p[idx+4]
            blen = (p[idx+5] << 8) | p[idx+6]
            if cmd == 0x1b and flag == 0x00:
                body = p[idx+7:idx+7+blen]
                print(f"0x1b ack body: {body.hex()}")
                if len(body) >= 4:
                    status = body[0]
                    seq = body[1]
                    chunk_size = (body[2] << 8) | body[3]
                    print(f"  status=0x{status:02x} seq={seq} chunk_size={chunk_size}")
                    print(f"  So the device says: use chunks of {chunk_size} bytes")
                break
    break

# Verify: 15647 bytes / 490 bytes per chunk = 31.93 = 32 chunks. 32 * 490 = 15680 > 15647
# With 490 byte chunks: 32 chunks (last one is 15647 - 31*490 = 15647 - 15190 = 457 bytes)
# BUT: tail = jpeg[490:] = 15157 bytes. head = jpeg[0:490] = 490 bytes.
# tail chunks: ceil(15157/490) = 31 chunks. head chunk: 1 chunk (490 bytes). Total: 32. Matches!
print("\n=== CHUNK SIZE VERIFICATION ===")
fsize = 15647
chunk_size = 490
tail_len = fsize - chunk_size  # 15157
head_len = chunk_size  # 490
tail_chunks = (tail_len + chunk_size - 1) // chunk_size  # ceil(15157/490) = 31
print(f"File size: {fsize}")
print(f"Chunk size: {chunk_size}")
print(f"Tail (jpeg[490:]): {tail_len} bytes, {tail_chunks} chunks")
print(f"Head (jpeg[0:490]): {head_len} bytes, 1 chunk")
print(f"Total chunks: {tail_chunks + 1} = {tail_chunks + 1}")
print(f"Data frames in capture: 32")
print(f"Match: {tail_chunks + 1 == 32}")

# The FE frame for a 490-byte payload:
# body = [seq(1), subcmd(1), slot(1), crc_hi(1), crc_lo(1), data(490)] = 495 bytes
# FE frame = [FE DC BA flag cmd len_hi len_lo body(495) EF] = 503 bytes
# This is sent as a single ATT Write Without Response
# In the .pklg capture, each HCI ACL record may be truncated!
print(f"\nFE frame for 490-byte payload: {3+1+1+2+495+1} = 503 bytes")
print(f"iOS probably negotiated a higher MTU (e.g. 512) to fit this in one write")
