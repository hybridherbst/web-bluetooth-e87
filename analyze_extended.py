#!/usr/bin/env python3
"""
Analyze cap-extended.pklg — find ALL upload sessions,
extract metadata, and compare protocol differences.
"""
import struct, re, sys

def crc16x(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc

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

def extract_e87_events(records):
    events = []
    for r in records:
        if r['type'] not in (2, 3):
            continue
        p = r['payload']
        direction = 'TX' if r['type'] == 2 else 'RX'

        if len(p) < 12:
            continue
        att_op = p[8]
        att_handle = (p[9] | (p[10] << 8)) if len(p) > 10 else 0
        att_value = p[11:]

        # FD02 control writes
        if att_handle == 0x000C and att_op in (0x52, 0x12):
            events.append({
                'ts': r['ts'], 'dir': direction, 'type': 'FD02',
                'value': att_value, 'cmd': None, 'flag': None, 'body': att_value
            })
            continue

        # FD03 notifications
        if att_handle == 0x000E and att_op == 0x1b:
            events.append({
                'ts': r['ts'], 'dir': direction, 'type': 'FD03',
                'value': att_value, 'cmd': None, 'flag': None, 'body': att_value
            })
            continue

        # E87 frames on AE01/AE02
        if att_handle not in (0x0006, 0x0008):
            continue
        if att_op not in (0x52, 0x12, 0x1b, 0x1d):
            continue
        if len(att_value) < 7:
            continue
        if att_value[0:3] != b'\xfe\xdc\xba' or att_value[-1] != 0xef:
            # Raw (non-FE) frame on AE01/AE02
            events.append({
                'ts': r['ts'], 'dir': direction, 'type': 'RAW_AE',
                'value': att_value, 'cmd': None, 'flag': None, 'body': att_value
            })
            continue

        flag = att_value[3]
        cmd = att_value[4]
        blen = (att_value[5] << 8) | att_value[6]
        body = att_value[7:-1]
        events.append({
            'ts': r['ts'], 'dir': direction, 'type': 'E87',
            'flag': flag, 'cmd': cmd, 'blen': blen, 'body': body,
            'value': att_value
        })
    events.sort(key=lambda e: e['ts'])
    return events

def cmd_name(cmd):
    names = {
        0x01: 'DATA', 0x03: 'Q03', 0x06: 'AUTH', 0x07: 'Q07',
        0x1b: 'FILE_META', 0x1c: 'SESS_CLOSE', 0x1d: 'WIN_ACK',
        0x20: 'FILE_COMP', 0x21: 'SESS_OPEN', 0x27: 'XFER_PAR',
    }
    return names.get(cmd, f'cmd_{cmd:#04x}')

# ── Parse ──
records = parse_pklg('/Users/herbst/git/bluetooth-tag/cap-extended.pklg')
events = extract_e87_events(records)
print(f"Total records: {len(records)}, E87/control events: {len(events)}")

# ── Find upload sessions by looking for SESS_OPEN (cmd 0x21) ──
sessions = []
for i, e in enumerate(events):
    if e['type'] == 'E87' and e['cmd'] == 0x21 and e['dir'] == 'TX':
        sessions.append({'open_idx': i, 'open_ts': e['ts'], 'events': []})

print(f"\nFound {len(sessions)} upload sessions (SESS_OPEN cmd 0x21)")

# Assign events to sessions
for i, e in enumerate(events):
    for s_idx in range(len(sessions)):
        start = sessions[s_idx]['open_ts']
        end = sessions[s_idx + 1]['open_ts'] if s_idx + 1 < len(sessions) else float('inf')
        if start <= e['ts'] < end:
            sessions[s_idx]['events'].append(e)
            break

# ── Analyze each session ──
for s_idx, session in enumerate(sessions):
    evts = session['events']
    print(f"\n{'=' * 90}")
    print(f"SESSION {s_idx + 1} (ts={session['open_ts']:.3f})")
    print(f"{'=' * 90}")

    # Find key protocol events
    sess_open = None
    xfer_par = None
    file_meta_tx = None
    file_meta_rx = None
    file_comp = None
    sess_close = None
    win_acks = []
    data_chunks = []

    for e in evts:
        if e['type'] != 'E87':
            continue
        if e['cmd'] == 0x21 and e['dir'] == 'TX':
            sess_open = e
        elif e['cmd'] == 0x27 and e['dir'] == 'TX':
            xfer_par = e
        elif e['cmd'] == 0x1b and e['dir'] == 'TX':
            file_meta_tx = e
        elif e['cmd'] == 0x1b and e['dir'] == 'RX':
            file_meta_rx = e
        elif e['cmd'] == 0x20:
            file_comp = e
        elif e['cmd'] == 0x1c:
            if sess_close is None:
                sess_close = e
        elif e['cmd'] == 0x1d and e['dir'] == 'RX':
            win_acks.append(e)
        elif e['cmd'] == 0x01 and e['dir'] == 'TX':
            data_chunks.append(e)

    # Print SESS_OPEN
    if sess_open:
        print(f"\n  SESS_OPEN body: {sess_open['body'].hex()}")
        print(f"    flag=0x{sess_open['flag']:02x} seq={sess_open['body'][0]} rest={sess_open['body'][1:].hex()}")

    # Print XFER_PAR
    if xfer_par:
        print(f"\n  XFER_PAR body: {xfer_par['body'].hex()}")
        print(f"    flag=0x{xfer_par['flag']:02x} seq={xfer_par['body'][0]}")
        if len(xfer_par['body']) >= 7:
            print(f"    params: {xfer_par['body'][1:].hex()}")

    # Print FILE_META TX
    if file_meta_tx:
        b = file_meta_tx['body']
        print(f"\n  FILE_META TX body ({len(b)} bytes): {b.hex()}")
        print(f"    seq={b[0]}")
        print(f"    [1:3]={b[1:3].hex()}")
        fsize = (b[3] << 8) | b[4]
        print(f"    file_size={fsize} (0x{fsize:04x})")
        if len(b) >= 7:
            fcrc = (b[5] << 8) | b[6]
            print(f"    file_crc=0x{fcrc:04x}")
        if len(b) >= 9:
            print(f"    [7:9]={b[7:9].hex()}")
        # Name
        name_start = 9
        if len(b) > name_start:
            name_end = len(b)
            for j in range(name_start, len(b)):
                if b[j] == 0:
                    name_end = j
                    break
            name = b[name_start:name_end].decode('ascii', errors='replace')
            print(f"    name='{name}'")

    # Print FILE_META RX (ack)
    if file_meta_rx:
        b = file_meta_rx['body']
        print(f"\n  FILE_META RX body ({len(b)} bytes): {b.hex()}")
        if len(b) >= 4:
            chunk_size = (b[2] << 8) | b[3]
            print(f"    status={b[0]} seq={b[1]} chunk_size={chunk_size}")

    # WIN_ACK analysis
    if win_acks:
        print(f"\n  WIN_ACKs ({len(win_acks)} total):")
        for wa in win_acks[:5]:
            b = wa['body']
            if len(b) >= 8:
                ack_seq = b[0]
                status = b[1]
                ws = (b[2] << 8) | b[3]
                noff = (b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]
                print(f"    ackSeq={ack_seq} st={status} wSz={ws} nOff={noff}")
        if len(win_acks) > 5:
            print(f"    ... ({len(win_acks) - 5} more)")
        # Show last WIN_ACK
        if len(win_acks) > 5:
            wa = win_acks[-1]
            b = wa['body']
            if len(b) >= 8:
                ack_seq = b[0]
                ws = (b[2] << 8) | b[3]
                noff = (b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]
                print(f"    LAST: ackSeq={ack_seq} wSz={ws} nOff={noff}")

    # Data chunks summary
    if data_chunks:
        total_payload = 0
        seqs = []
        for dc in data_chunks:
            b = dc['body']
            if len(b) >= 5:
                seqs.append(b[0])
                total_payload += dc['blen'] - 5
        print(f"\n  DATA CHUNKS: {len(data_chunks)} chunks")
        print(f"    seq range: {min(seqs)}-{max(seqs)}")
        print(f"    total payload bytes: {total_payload}")
        # First chunk details
        b = data_chunks[0]['body']
        if len(b) > 8:
            print(f"    first chunk: seq={b[0]} slot={b[2]} crc=0x{(b[3]<<8)|b[4]:04x} first4={b[5:9].hex()}")
        # Last chunk details
        b = data_chunks[-1]['body']
        if len(b) > 8:
            print(f"    last chunk:  seq={b[0]} slot={b[2]} crc=0x{(b[3]<<8)|b[4]:04x} first4={b[5:9].hex()}")

    # FILE_COMPLETE
    if file_comp:
        print(f"\n  FILE_COMP: dir={file_comp['dir']} flag=0x{file_comp['flag']:02x} body={file_comp['body'].hex()}")

    # SESSION_CLOSE
    if sess_close:
        print(f"\n  SESS_CLOSE: dir={sess_close['dir']} flag=0x{sess_close['flag']:02x} body={sess_close['body'].hex()}")
        if len(sess_close['body']) >= 2:
            status = sess_close['body'][1]
            status_names = {0: 'SUCCESS', 3: 'FILE_ERR'}
            print(f"    status={status_names.get(status, f'0x{status:02x}')} seq={sess_close['body'][0]}")

    # Timing
    if data_chunks:
        t_start = data_chunks[0]['ts']
        t_end = data_chunks[-1]['ts']
        print(f"\n  Transfer time: {(t_end - t_start)*1000:.0f}ms")

    # FD02 control writes in this session
    fd02_writes = [e for e in evts if e['type'] == 'FD02']
    if fd02_writes:
        print(f"\n  FD02 control writes: {len(fd02_writes)}")
        for f in fd02_writes[:3]:
            print(f"    {f['dir']}: {f['value'].hex()}")
        if len(fd02_writes) > 3:
            print(f"    ... ({len(fd02_writes) - 3} more)")

    # Check for multiple FILE_META sends (multiple files in one session?)
    all_meta_tx = [e for e in evts if e['type'] == 'E87' and e['cmd'] == 0x1b and e['dir'] == 'TX']
    if len(all_meta_tx) > 1:
        print(f"\n  *** MULTIPLE FILE_META TX: {len(all_meta_tx)} ***")
        for m_idx, m in enumerate(all_meta_tx):
            b = m['body']
            fsize = (b[3] << 8) | b[4] if len(b) >= 5 else 0
            fcrc = (b[5] << 8) | b[6] if len(b) >= 7 else 0
            name_start = 9
            name = ''
            if len(b) > name_start:
                name_end = len(b)
                for j in range(name_start, len(b)):
                    if b[j] == 0:
                        name_end = j
                        break
                name = b[name_start:name_end].decode('ascii', errors='replace')
            print(f"    [{m_idx}] seq={b[0]} size={fsize} crc=0x{fcrc:04x} name='{name}'")

    # Count all SESS_CLOSE events (to detect multiple transfers)
    all_close = [e for e in evts if e['type'] == 'E87' and e['cmd'] == 0x1c]
    if len(all_close) > 2:  # RX + TX for each close
        print(f"\n  *** MULTIPLE SESS_CLOSE: {len(all_close)} ***")

print(f"\n{'=' * 90}")
print("DONE")
