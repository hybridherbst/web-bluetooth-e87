#!/usr/bin/env python3
"""
Extract AVI files from the capture by reassembling data chunks.
Analyze the AVI format structure.
"""
import struct, os

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

def reassemble_att(records):
    reassembly = {}
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
        acl_data = p[4:]
        direction = 'TX' if r['type'] == 2 else 'RX'
        if pb_flag in (0x00, 0x02):
            if len(acl_data) < 4:
                continue
            l2cap_len = acl_data[0] | (acl_data[1] << 8)
            cid = acl_data[2] | (acl_data[3] << 8)
            l2cap_payload = acl_data[4:]
            if cid == 0x0004:
                if len(l2cap_payload) >= l2cap_len:
                    att_packets.append({'ts': r['ts'], 'dir': direction, 'data': l2cap_payload[:l2cap_len]})
                else:
                    reassembly[conn_handle] = {'l2cap_len': l2cap_len, 'buf': bytearray(l2cap_payload), 'ts': r['ts'], 'dir': direction}
        elif pb_flag == 0x01:
            if conn_handle in reassembly:
                ra = reassembly[conn_handle]
                ra['buf'].extend(acl_data)
                if len(ra['buf']) >= ra['l2cap_len']:
                    att_packets.append({'ts': ra['ts'], 'dir': ra['dir'], 'data': bytes(ra['buf'][:ra['l2cap_len']])})
                    del reassembly[conn_handle]
    return att_packets

records = parse_pklg('/Users/herbst/git/bluetooth-tag/cap-extended.pklg')
att_packets = reassemble_att(records)

# Find sessions
sess_starts = []
for ap in att_packets:
    d = ap['data']
    if len(d) < 4:
        continue
    op = d[0]
    handle = d[1] | (d[2] << 8)
    value = d[3:]
    if handle in (0x0006,) and len(value) >= 8 and value[0:3] == b'\xfe\xdc\xba' and value[-1] == 0xef:
        cmd = value[4]
        if cmd == 0x21 and ap['dir'] == 'TX':
            sess_starts.append(ap['ts'])

# For each session, reassemble file from data chunks using WIN_ACK offsets
for s_idx, start_ts in enumerate(sess_starts):
    end_ts = sess_starts[s_idx + 1] if s_idx + 1 < len(sess_starts) else float('inf')
    
    data_chunks = []
    win_acks = []
    file_meta_tx = None
    
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
        if len(value) < 8 or value[0:3] != b'\xfe\xdc\xba' or value[-1] != 0xef:
            continue
        cmd = value[4]
        body = value[7:-1]
        if cmd == 0x01 and ap['dir'] == 'TX':
            data_chunks.append({'ts': ap['ts'], 'body': body})
        elif cmd == 0x1d and ap['dir'] == 'RX':
            win_acks.append(body)
        elif cmd == 0x1b and ap['dir'] == 'TX':
            file_meta_tx = body
    
    if not file_meta_tx:
        continue
    
    fsize = (file_meta_tx[3] << 8) | file_meta_tx[4]
    fcrc = (file_meta_tx[5] << 8) | file_meta_tx[6]
    meta_12 = file_meta_tx[1:3].hex()
    name = ''
    if len(file_meta_tx) > 9:
        ne = len(file_meta_tx)
        for j in range(9, len(file_meta_tx)):
            if file_meta_tx[j] == 0:
                ne = j
                break
        name = file_meta_tx[9:ne].decode('ascii', errors='replace')
    
    print(f"\n{'='*80}")
    print(f"SESSION {s_idx+1}: size={fsize} crc=0x{fcrc:04x} meta[1:3]={meta_12} name='{name}'")
    print(f"  Data chunks: {len(data_chunks)}")
    print(f"  WIN_ACKs: {len(win_acks)}")
    
    # Compute total payload size
    total_size = 0
    for dc in data_chunks:
        b = dc['body']
        if len(b) >= 5:
            total_size += len(b) - 5  # subtract header
    print(f"  Total payload: {total_size} bytes")
    
    # The FILE_META size field is only 16 bits (max 65535)
    # but total_payload can be much bigger (session 1 = 1MB, session 3 = 375K)
    # Maybe meta[1:3] is extended size info? Or file_size is the AVI header size?
    
    # Let me check: does fsize match the LAST chunk's data?
    # The commit window (ws=0, noff=0) sends the file header (RIFF/AVI)
    # Let me look at the first few data chunks to understand
    
    # Group chunks by WIN_ACK windows
    print(f"\n  --- Window analysis ---")
    wa_idx = 0
    chunk_idx = 0
    window_data = []
    
    for wa in win_acks[:3]:  # Just first 3 windows
        if len(wa) >= 8:
            aseq = wa[0]
            st = wa[1]
            ws = (wa[2] << 8) | wa[3]
            noff = (wa[4] << 24) | (wa[5] << 16) | (wa[6] << 8) | wa[7]
            n_chunks = ws // 490 if ws > 0 else 0
            print(f"  WIN_ACK: aseq={aseq} ws={ws} noff={noff} chunks={n_chunks}")
    
    # Last 2 WIN_ACKs
    for wa in win_acks[-2:]:
        if len(wa) >= 8:
            aseq = wa[0]
            ws = (wa[2] << 8) | wa[3]
            noff = (wa[4] << 24) | (wa[5] << 16) | (wa[6] << 8) | wa[7]
            n_chunks = ws // 490 if ws > 0 else 0
            print(f"  WIN_ACK (tail): aseq={aseq} ws={ws} noff={noff} chunks={n_chunks}")
    
    # Reassemble file: use WIN_ACKs to place data at correct offsets
    # But the total_payload >> fsize... 
    # Wait: maybe fsize needs to be computed differently from meta bytes
    # Let's look at meta[1:3] more carefully
    # Session 1: meta[1:3]=0010, size=5098 → 0x0010_13EA? = 0x001013EA = 1,053,674! That matches!
    # Session 2: meta[1:3]=0000, size=38072 → 0x0000_94B8 = 38,072. Matches total payload.
    # Session 3: meta[1:3]=0005, size=47382 → 0x0005_B916 = 374,038. Hmm, total payload = 375,062
    
    extended_size = (file_meta_tx[1] << 24) | (file_meta_tx[2] << 16) | (file_meta_tx[3] << 8) | file_meta_tx[4]
    print(f"\n  Extended file size (4 bytes [1:5]): {extended_size} (0x{extended_size:08x})")
    print(f"  Matches total payload? {extended_size == total_size}")
    
    # Reassemble the file
    file_buf = bytearray(total_size + 10000)  # extra room
    max_written = 0
    
    # Track which offsets each window writes to
    wa_iter = iter(win_acks)
    chunk_iter = iter(data_chunks)
    
    # Simpler approach: each WIN_ACK says "write next N bytes at offset noff"
    # The chunks following a WIN_ACK contain the data
    for wa in win_acks:
        if len(wa) < 8:
            continue
        ws = (wa[2] << 8) | wa[3]
        noff = (wa[4] << 24) | (wa[5] << 16) | (wa[6] << 8) | wa[7]
        # ws=0, noff=0 means commit - the next batch of chunks goes to offset 0
        # But how many chunks per window?
    
    # Actually let's just dump all chunk payloads sequentially and see if it forms an AVI
    # The WIN_ACK-based reassembly needs more careful mapping
    # For now, just concatenate in order
    sequential = bytearray()
    for dc in data_chunks:
        b = dc['body']
        if len(b) >= 5:
            sequential.extend(b[5:])
    
    # Check first 4 bytes
    print(f"\n  Sequential first 32 bytes: {sequential[:32].hex()}")
    print(f"  Sequential last 32 bytes: {sequential[-32:].hex()}")
    
    # The RIFF header should appear somewhere - last chunk had it
    # Let's find RIFF markers
    riff_positions = []
    for i in range(len(sequential) - 4):
        if sequential[i:i+4] == b'RIFF':
            riff_positions.append(i)
    print(f"  RIFF marker positions: {riff_positions}")
    
    # Save sequential dump for inspection
    outf = f'/Users/herbst/git/bluetooth-tag/session{s_idx+1}_sequential.bin'
    with open(outf, 'wb') as f:
        f.write(sequential)
    print(f"  Saved to {outf}")
