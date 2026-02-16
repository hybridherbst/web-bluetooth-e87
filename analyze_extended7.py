#!/usr/bin/env python3
"""
Properly reassemble AVI files using WIN_ACK offsets and extract/analyze them.
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

def crc16x(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc

records = parse_pklg('/Users/herbst/git/bluetooth-tag/cap-extended.pklg')
att_packets = reassemble_att(records)

# Find sessions
sess_starts = []
for ap in att_packets:
    d = ap['data']
    if len(d) < 4:
        continue
    handle = d[1] | (d[2] << 8)
    value = d[3:]
    if handle == 0x0006 and len(value) >= 8 and value[0:3] == b'\xfe\xdc\xba' and value[-1] == 0xef:
        if value[4] == 0x21 and ap['dir'] == 'TX':
            sess_starts.append(ap['ts'])

for s_idx, start_ts in enumerate(sess_starts):
    end_ts = sess_starts[s_idx + 1] if s_idx + 1 < len(sess_starts) else float('inf')
    
    # Collect E87 events in time order
    events = []
    for ap in att_packets:
        if not (start_ts <= ap['ts'] < end_ts):
            continue
        d = ap['data']
        if len(d) < 4:
            continue
        handle = d[1] | (d[2] << 8)
        value = d[3:]
        if handle not in (0x0006, 0x0008):
            continue
        if len(value) < 8 or value[0:3] != b'\xfe\xdc\xba' or value[-1] != 0xef:
            continue
        cmd = value[4]
        body = value[7:-1]
        events.append({'ts': ap['ts'], 'dir': ap['dir'], 'cmd': cmd, 'body': body, 'handle': handle})
    
    # Get file meta
    file_meta = None
    for e in events:
        if e['cmd'] == 0x1b and e['dir'] == 'TX':
            file_meta = e['body']
            break
    
    if not file_meta:
        continue
    
    file_size = (file_meta[1] << 24) | (file_meta[2] << 16) | (file_meta[3] << 8) | file_meta[4]
    file_crc = (file_meta[5] << 8) | file_meta[6]
    
    print(f"\n{'='*80}")
    print(f"SESSION {s_idx+1}: size={file_size} crc=0x{file_crc:04x}")
    
    # Reassemble using WIN_ACK offsets
    # After each WIN_ACK(ws, noff), the phone sends ws/490 chunks at offset noff
    # For ws=0, noff=0 → commit, which writes the header at offset 0
    
    file_buf = bytearray(file_size)
    write_offset = 0
    chunk_queue = []
    
    # Iterate events in order, alternating WIN_ACK → data chunks
    pending_wa = None
    chunks_written = 0
    window_info = []
    
    for e in events:
        if e['cmd'] == 0x1d and e['dir'] == 'RX':
            # WIN_ACK
            b = e['body']
            if len(b) >= 8:
                ws = (b[2] << 8) | b[3]
                noff = (b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]
                pending_wa = {'ws': ws, 'noff': noff, 'written': 0}
                window_info.append(pending_wa)
        
        elif e['cmd'] == 0x01 and e['dir'] == 'TX':
            # Data chunk
            b = e['body']
            if len(b) < 5:
                continue
            payload = b[5:]
            
            if pending_wa:
                offset = pending_wa['noff'] + pending_wa['written']
                end = min(offset + len(payload), file_size)
                copy_len = end - offset
                if copy_len > 0 and offset >= 0:
                    file_buf[offset:offset + copy_len] = payload[:copy_len]
                pending_wa['written'] += len(payload)
                chunks_written += 1
    
    print(f"  Chunks written: {chunks_written}")
    print(f"  Windows: {len(window_info)}")
    
    # Verify CRC
    actual_crc = crc16x(file_buf)
    print(f"  CRC: expected=0x{file_crc:04x} actual=0x{actual_crc:04x} match={actual_crc == file_crc}")
    
    # Check RIFF header
    print(f"  First 12 bytes: {file_buf[:12].hex()}")
    if file_buf[:4] == b'RIFF':
        riff_size = struct.unpack_from('<I', file_buf, 4)[0]
        riff_type = file_buf[8:12].decode('ascii', errors='replace')
        print(f"  RIFF size={riff_size} type='{riff_type}'")
        
        # Parse AVI structure
        off = 12
        while off + 8 <= len(file_buf):
            chunk_id = file_buf[off:off+4].decode('ascii', errors='replace')
            chunk_size = struct.unpack_from('<I', file_buf, off+4)[0]
            
            if chunk_id == 'LIST':
                list_type = file_buf[off+8:off+12].decode('ascii', errors='replace')
                print(f"  @{off}: LIST '{list_type}' size={chunk_size}")
                
                if list_type == 'hdrl':
                    # Parse main AVI header
                    avih_off = off + 12
                    if file_buf[avih_off:avih_off+4] == b'avih':
                        avih_size = struct.unpack_from('<I', file_buf, avih_off+4)[0]
                        usec_per_frame = struct.unpack_from('<I', file_buf, avih_off+8)[0]
                        total_frames = struct.unpack_from('<I', file_buf, avih_off+24)[0]
                        width = struct.unpack_from('<I', file_buf, avih_off+40)[0]
                        height = struct.unpack_from('<I', file_buf, avih_off+44)[0]
                        fps = 1000000 / usec_per_frame if usec_per_frame > 0 else 0
                        print(f"    avih: usec/frame={usec_per_frame} fps={fps:.1f} frames={total_frames} {width}x{height}")
                    
                    # Find stream headers
                    inner_off = avih_off + 8 + avih_size
                    while inner_off + 8 <= off + 8 + chunk_size:
                        iid = file_buf[inner_off:inner_off+4].decode('ascii', errors='replace')
                        isz = struct.unpack_from('<I', file_buf, inner_off+4)[0]
                        if iid == 'LIST':
                            lt = file_buf[inner_off+8:inner_off+12].decode('ascii', errors='replace')
                            print(f"    @{inner_off}: LIST '{lt}' size={isz}")
                            if lt == 'strl':
                                # Stream header
                                strh_off = inner_off + 12
                                if file_buf[strh_off:strh_off+4] == b'strh':
                                    strh_size = struct.unpack_from('<I', file_buf, strh_off+4)[0]
                                    fcc_type = file_buf[strh_off+8:strh_off+12].decode('ascii', errors='replace')
                                    fcc_handler = file_buf[strh_off+12:strh_off+16].decode('ascii', errors='replace')
                                    rate = struct.unpack_from('<I', file_buf, strh_off+28)[0]
                                    scale = struct.unpack_from('<I', file_buf, strh_off+24)[0]
                                    length = struct.unpack_from('<I', file_buf, strh_off+32)[0]
                                    fps2 = rate/scale if scale > 0 else 0
                                    print(f"      strh: type='{fcc_type}' handler='{fcc_handler}' rate={rate} scale={scale} length={length} fps={fps2:.1f}")
                                # Find strf
                                strf_off = strh_off + 8 + strh_size
                                if file_buf[strf_off:strf_off+4] == b'strf':
                                    strf_size = struct.unpack_from('<I', file_buf, strf_off+4)[0]
                                    if fcc_type == 'vids':
                                        bi_w = struct.unpack_from('<I', file_buf, strf_off+12)[0]
                                        bi_h = struct.unpack_from('<I', file_buf, strf_off+16)[0]
                                        bi_comp = file_buf[strf_off+24:strf_off+28].decode('ascii', errors='replace')
                                        print(f"      strf: {bi_w}x{bi_h} compression='{bi_comp}'")
                            inner_off += 8 + isz + (isz & 1)
                        else:
                            inner_off += 8 + isz + (isz & 1)
                
                elif list_type == 'movi':
                    # Count frame types
                    frame_count = 0
                    frame_types = {}
                    movi_end = off + 8 + chunk_size
                    foff = off + 12
                    while foff + 8 <= movi_end:
                        fid = file_buf[foff:foff+4].decode('ascii', errors='replace')
                        fsz = struct.unpack_from('<I', file_buf, foff+4)[0]
                        frame_types[fid] = frame_types.get(fid, 0) + 1
                        frame_count += 1
                        foff += 8 + fsz + (fsz & 1)
                    print(f"    movi: {frame_count} entries, types: {frame_types}")
                    
                    # Show first few frame sizes
                    foff = off + 12
                    shown = 0
                    for _ in range(min(8, frame_count)):
                        fid = file_buf[foff:foff+4].decode('ascii', errors='replace')
                        fsz = struct.unpack_from('<I', file_buf, foff+4)[0]
                        # Check for JPEG signature
                        is_jpeg = file_buf[foff+8:foff+10] == b'\xff\xd8' if fsz > 2 else False
                        print(f"      [{shown}] {fid} size={fsz} {'(JPEG)' if is_jpeg else ''}")
                        shown += 1
                        foff += 8 + fsz + (fsz & 1)
                    
                off += 12  # Enter LIST
            else:
                print(f"  @{off}: '{chunk_id}' size={chunk_size}")
                off += 8 + chunk_size + (chunk_size & 1)
                if chunk_size == 0:
                    break
    
    # Save file
    outf = f'/Users/herbst/git/bluetooth-tag/session{s_idx+1}.avi'
    with open(outf, 'wb') as f:
        f.write(file_buf)
    print(f"  Saved to {outf}")
