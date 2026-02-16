#!/usr/bin/env python3
"""
Complete protocol analysis — every ATT operation, with focus on
FD02 control writes and their timing relative to data transfer.
Uses same PKLG parser as show_full_timeline.py.
"""
import struct, re

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
    records.append({'idx': rec_idx, 'type': ptype, 'payload': payload, 'ts': ts_secs + ts_usecs/1e6})
    rec_idx += 1
    off += 4 + rec_len
    if off > len(raw):
        break

handle_names = {0x0006: 'AE01', 0x0008: 'AE02', 0x000C: 'FD02',
                0x000E: 'FD03'}

# Parse ALL ATT operations
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
    
    if att_op not in (0x52, 0x12, 0x1b, 0x1d):  # write, write_req, notification, indication
        continue
    
    char_name = handle_names.get(att_handle, f'h{att_handle:04x}')
    
    e87_info = ''
    is_data_chunk = False
    fd02_info = ''
    
    # Check for FE DC BA E87 frame
    if att_handle in (0x0006, 0x0008) and len(att_value) >= 7:
        if att_value[0:3] == b'\xFE\xDC\xBA' and att_value[-1] == 0xEF:
            flag = att_value[3]
            cmd = att_value[4]
            body_len = (att_value[5] << 8) | att_value[6]
            body = att_value[7:-1]
            
            cmd_names = {0x01:'DATA', 0x03:'Q03', 0x06:'AUTH', 0x07:'Q07',
                         0x1b:'FILE_META', 0x1c:'SESS_CLOSE', 0x1d:'WIN_ACK',
                         0x20:'FILE_COMP', 0x21:'SESS_OPEN', 0x27:'XFER_PAR'}
            cname = cmd_names.get(cmd, f'cmd_0x{cmd:02x}')
            e87_info = f'{cname} fl=0x{flag:02x}'
            
            if cmd == 0x01 and flag == 0x80 and direction == 'TX':
                is_data_chunk = True
                if len(body) >= 5:
                    seq = body[0]
                    slot = body[2]
                    crc = (body[3] << 8) | body[4]
                    plen = body_len - 5
                    first4 = body[5:9].hex() if len(body) > 8 else ''
                    jfif = ' [JFIF!]' if first4.startswith('ffd8') else ''
                    e87_info += f' seq={seq} slot={slot} crc=0x{crc:04x} pLen={plen}{jfif}'
            
            elif cmd == 0x1d and len(body) >= 8:
                ack_seq = body[0]
                status = body[1]
                win_size = (body[2] << 8) | body[3]
                next_off = (body[4] << 24) | (body[5] << 16) | (body[6] << 8) | body[7]
                e87_info += f' ackSeq={ack_seq} st={status} wSz={win_size} nOff={next_off}'
            
            elif cmd == 0x1b:
                if len(body) >= 5:
                    fsize = (body[3] << 8) | body[4] if direction == 'TX' else None
                    e87_info += f' body={body.hex()}'
                    if fsize:
                        e87_info += f' fileSize={fsize}'
                else:
                    e87_info += f' body={body.hex()}'
            
            elif cmd in (0x20, 0x1c, 0x21, 0x27, 0x06, 0x03, 0x07):
                e87_info += f' body={body.hex()}'
    
    if att_handle == 0x000C:
        fd02_info = f'FD02 val={att_value.hex()}'
    
    if att_handle in (0x000E,):
        fd02_info = f'FD03 val={att_value.hex()}'
    
    if not e87_info and not fd02_info:
        if att_handle not in (0x0006, 0x0008, 0x000C, 0x000E):
            continue
        fd02_info = f'{char_name} raw={att_value[:20].hex()}'
    
    events.append({
        'dir': direction, 'char': char_name, 'ts': r['ts'],
        'e87': e87_info, 'fd02': fd02_info, 'is_data': is_data_chunk,
        'handle': att_handle,
    })

events.sort(key=lambda e: e['ts'])

# ── 1. Full timeline from AUTH onwards ──
print("=" * 100)
print("FULL PROTOCOL TIMELINE (AUTH → END):")
print("=" * 100)
base_ts = None
data_phase = False
for e in events:
    if 'AUTH' in e['e87'] and base_ts is None:
        base_ts = e['ts']
    if base_ts is None:
        continue
    
    rel = (e['ts'] - base_ts) * 1000
    label = e['e87'] or e['fd02']
    marker = ' <<<' if e['is_data'] else ''
    if e['is_data']:
        data_phase = True
    
    # During data phase, only show non-data events in detail
    if data_phase and e['is_data']:
        # Summarize data chunks (don't print every one)
        pass
    
    if not data_phase or not e['is_data']:
        print(f"  +{rel:8.1f}ms {e['dir']:2s} {e['char']:5s} {label}{marker}")

# ── 2. FD02 control writes timeline ──
print("\n" + "=" * 100)
print("ALL FD02 CONTROL WRITES (with phase context):")
print("=" * 100)
first_data_ts = None
last_data_ts = None
for e in events:
    if e['is_data'] and first_data_ts is None:
        first_data_ts = e['ts']
    if e['is_data']:
        last_data_ts = e['ts']

for e in events:
    if e['handle'] != 0x000C or not e['fd02']:
        continue
    if base_ts is None:
        continue
    rel = (e['ts'] - base_ts) * 1000
    phase = 'pre-data'
    if first_data_ts and e['ts'] >= first_data_ts:
        if last_data_ts and e['ts'] <= last_data_ts:
            phase = 'DURING-DATA'
        else:
            phase = 'post-data'
    print(f"  +{rel:8.1f}ms {e['dir']:2s} {e['fd02']:50s} [{phase}]")

# ── 3. Window breakdown ──
print("\n" + "=" * 100)
print("WINDOW-BY-WINDOW BREAKDOWN:")
print("=" * 100)
chunks = []
windows = []
current_win_chunks = []
total_payload = 0

for e in events:
    if e['is_data']:
        current_win_chunks.append(e)
        m = re.search(r'pLen=(\d+)', e['e87'])
        if m:
            total_payload += int(m.group(1))
    
    if 'WIN_ACK' in e['e87'] and current_win_chunks:
        windows.append({'chunks': current_win_chunks[:], 'ack': e})
        current_win_chunks = []

# Remaining (commit) chunks
if current_win_chunks:
    windows.append({'chunks': current_win_chunks[:], 'ack': None})

for i, w in enumerate(windows):
    is_commit = w['ack'] is None or (w['ack'] and 'nOff=0' in w['ack']['e87'])
    label = f"Window {i+1}" + (" (COMMIT)" if is_commit and w['ack'] is None else "")
    
    psum = 0
    seqs = []
    for c in w['chunks']:
        m = re.search(r'pLen=(\d+)', c['e87'])
        if m: psum += int(m.group(1))
        m = re.search(r'seq=(\d+)', c['e87'])
        if m: seqs.append(int(m.group(1)))
    
    seq_range = f"seq {min(seqs)}-{max(seqs)}" if seqs else "?"
    print(f"\n  {label}: {len(w['chunks'])} chunks ({seq_range}), {psum} bytes")
    for c in w['chunks']:
        print(f"    {c['e87']}")
    if w['ack']:
        print(f"  → ACK: {w['ack']['e87']}")

print(f"\n  TOTAL payload bytes: {total_payload}")
print(f"  TOTAL data chunks: {sum(len(w['chunks']) for w in windows)}")

# ── 4. Sequence number analysis ──
print("\n" + "=" * 100)
print("SEQ NUMBER ANALYSIS (all TX E87 commands):")
print("=" * 100)
for e in events:
    if e['dir'] == 'TX' and e['e87'] and e['handle'] == 0x0006:
        m = re.search(r'body=([0-9a-f]+)', e['e87'])
        if m:
            body_hex = m.group(1)
            seq = int(body_hex[:2], 16)
            print(f"  {e['e87'][:60]:60s} → seq_byte={seq}")
        elif 'seq=' in e['e87']:
            m2 = re.search(r'seq=(\d+)', e['e87'])
            if m2:
                print(f"  {e['e87'][:60]:60s} → seq={m2.group(1)}")
