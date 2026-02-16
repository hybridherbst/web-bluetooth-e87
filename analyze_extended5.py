#!/usr/bin/env python3
"""
Parse cap-extended.pklg with L2CAP/ATT reassembly.
The PKLG records are HCI ACL packets — each may be a fragment.
L2CAP header: len(2) + cid(2), then ATT data follows.
HCI ACL header includes PB flag for first/continuation.
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

# HCI ACL: payload = handle(2) + data
# handle word: bits 0-11 = conn handle, bits 12-13 = PB flag, bits 14-15 = BC flag
# PB flag: 0x00 = first non-auto-flushable, 0x01 = continuation, 0x02 = first auto-flushable
# For first packet: L2CAP header = length(2LE) + CID(2LE), then L2CAP payload
# ATT is CID=0x0004

# Reassemble L2CAP packets
reassembly = {}  # conn_handle -> (l2cap_len, cid, buffer, ts, ptype)
att_packets = []

for r in records:
    if r['type'] not in (2, 3):
        continue
    p = r['payload']
    if len(p) < 4:
        continue
    
    hw = p[0] | (p[1] << 8)
    conn_handle = hw & 0x0FFF
    pb_flag = (hw >> 12) & 0x03
    acl_data = p[4:]  # skip handle(2) + acl_len(2)
    
    direction = 'TX' if r['type'] == 2 else 'RX'
    
    if pb_flag in (0x00, 0x02):  # First packet
        if len(acl_data) < 4:
            continue
        l2cap_len = acl_data[0] | (acl_data[1] << 8)
        cid = acl_data[2] | (acl_data[3] << 8)
        l2cap_payload = acl_data[4:]
        
        if cid == 0x0004:  # ATT
            if len(l2cap_payload) >= l2cap_len:
                # Complete in one packet
                att_packets.append({
                    'ts': r['ts'], 'dir': direction, 
                    'data': l2cap_payload[:l2cap_len]
                })
            else:
                # Need reassembly
                reassembly[conn_handle] = {
                    'l2cap_len': l2cap_len, 'cid': cid,
                    'buf': bytearray(l2cap_payload),
                    'ts': r['ts'], 'dir': direction
                }
        else:
            # Non-ATT L2CAP - skip for now
            pass
    
    elif pb_flag == 0x01:  # Continuation
        if conn_handle in reassembly:
            ra = reassembly[conn_handle]
            ra['buf'].extend(acl_data)
            if len(ra['buf']) >= ra['l2cap_len']:
                att_packets.append({
                    'ts': ra['ts'], 'dir': ra['dir'],
                    'data': bytes(ra['buf'][:ra['l2cap_len']])
                })
                del reassembly[conn_handle]

print(f"Reassembled {len(att_packets)} ATT packets")

# Now parse ATT packets for AE01/AE02 E87 frames
# ATT Write Command (0x52): op(1) + handle(2LE) + value
# ATT Notification (0x1b): op(1) + handle(2LE) + value
sess_starts = []
file_meta_count = 0

# Identify sessions
for ap in att_packets:
    d = ap['data']
    if len(d) < 4:
        continue
    op = d[0]
    handle = d[1] | (d[2] << 8)
    value = d[3:]
    
    if handle in (0x0006, 0x0008) and len(value) >= 8:
        if value[0:3] == b'\xfe\xdc\xba' and value[-1] == 0xef:
            cmd = value[4]
            if cmd == 0x21 and ap['dir'] == 'TX':
                sess_starts.append(ap['ts'])

print(f"Found {len(sess_starts)} sessions")

# Now analyze each session with proper reassembly
for s_idx, start_ts in enumerate(sess_starts):
    end_ts = sess_starts[s_idx + 1] if s_idx + 1 < len(sess_starts) else float('inf')
    
    data_chunks = []
    file_meta_tx = None
    file_meta_rx = None
    file_comp_tx = None
    win_acks = []
    
    for ap in att_packets:
        if not (start_ts <= ap['ts'] < end_ts):
            continue
        d = ap['data']
        if len(d) < 4:
            continue
        op = d[0]
        handle = d[1] | (d[2] << 8)
        value = d[3:]
        
        if handle not in (0x0006, 0x0008):
            continue
        if len(value) < 8:
            continue
        if value[0:3] != b'\xfe\xdc\xba' or value[-1] != 0xef:
            continue
        
        flag = value[3]
        cmd = value[4]
        blen = (value[5] << 8) | value[6]
        body = value[7:-1]
        
        if cmd == 0x01 and ap['dir'] == 'TX':
            data_chunks.append({'ts': ap['ts'], 'body': body, 'blen': blen})
        elif cmd == 0x1b and ap['dir'] == 'TX':
            file_meta_tx = body
        elif cmd == 0x1b and ap['dir'] == 'RX':
            file_meta_rx = body
        elif cmd == 0x1d and ap['dir'] == 'RX':
            win_acks.append(body)
        elif cmd == 0x20 and ap['dir'] == 'TX':
            file_comp_tx = body
    
    print(f"\n{'='*80}")
    print(f"SESSION {s_idx+1}")
    print(f"{'='*80}")
    
    if file_meta_tx:
        b = file_meta_tx
        seq = b[0]
        fsize = (b[3] << 8) | b[4] if len(b) >= 5 else 0
        fcrc = (b[5] << 8) | b[6] if len(b) >= 7 else 0
        name = ''
        if len(b) > 9:
            ne = len(b)
            for j in range(9, len(b)):
                if b[j] == 0:
                    ne = j
                    break
            name = b[9:ne].decode('ascii', errors='replace')
        print(f"  FILE_META: seq={seq} [1:3]={b[1:3].hex()} size={fsize} crc=0x{fcrc:04x} name='{name}'")
    
    if file_meta_rx:
        b = file_meta_rx
        chunk_size = (b[2] << 8) | b[3] if len(b) >= 4 else 0
        print(f"  FILE_META ACK: status={b[0]} seq={b[1]} chunk_size={chunk_size}")
    
    print(f"  DATA CHUNKS: {len(data_chunks)}")
    
    # Analyze data chunk structure
    total_payload = 0
    for i, dc in enumerate(data_chunks):
        b = dc['body']
        if len(b) >= 5:
            seq = b[0]
            subcmd = b[1]
            slot = b[2]
            crc = (b[3] << 8) | b[4]
            payload = b[5:]
            total_payload += len(payload)
            if i < 10 or i >= len(data_chunks) - 3:
                # Check first 4 bytes of payload for magic
                magic = payload[:8].hex() if len(payload) >= 8 else payload.hex()
                print(f"    [{i:3d}] seq={seq:3d} sub=0x{subcmd:02x} slot={slot} crc=0x{crc:04x} plen={len(payload)} first8={magic}")
    
    if len(data_chunks) > 13:
        print(f"    ... ({len(data_chunks) - 13} more chunks)")
    
    print(f"  Total payload: {total_payload} bytes")
    
    # WIN_ACK analysis
    print(f"  WIN_ACKs: {len(win_acks)}")
    for i, wa in enumerate(win_acks[:5]):
        if len(wa) >= 8:
            aseq = wa[0]
            st = wa[1]
            ws = (wa[2] << 8) | wa[3]
            noff = (wa[4] << 24) | (wa[5] << 16) | (wa[6] << 8) | wa[7]
            print(f"    [{i}] ackSeq={aseq} st={st} ws={ws} noff={noff}")
    if len(win_acks) > 5:
        wa = win_acks[-1]
        if len(wa) >= 8:
            aseq = wa[0]
            ws = (wa[2] << 8) | wa[3]
            noff = (wa[4] << 24) | (wa[5] << 16) | (wa[6] << 8) | wa[7]
            print(f"    LAST: ackSeq={aseq} ws={ws} noff={noff}")
    
    # FILE_COMP analysis
    if file_comp_tx:
        # Decode the filename (UTF-16LE after first 2 bytes)
        status = file_comp_tx[0]
        devseq = file_comp_tx[1]
        # Rest is UTF-16LE filename
        name_bytes = file_comp_tx[2:]
        try:
            # Find null terminator
            null_pos = len(name_bytes)
            for j in range(0, len(name_bytes) - 1, 2):
                if name_bytes[j] == 0 and name_bytes[j+1] == 0:
                    null_pos = j
                    break
            filename = name_bytes[:null_pos].decode('utf-16-le')
        except:
            filename = name_bytes.hex()
        print(f"  FILE_COMP: status={status} devSeq={devseq} filename='{filename}'")
