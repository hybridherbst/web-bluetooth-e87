#!/usr/bin/env python3
"""
Compare FD02 control writes between sessions and also with the single-image capture.
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

# Parse both captures
for capname in ['cap.pklg', 'cap-extended.pklg']:
    print(f"\n{'='*80}")
    print(f"CAPTURE: {capname}")
    print(f"{'='*80}")
    
    records = parse_pklg(f'/Users/herbst/git/bluetooth-tag/{capname}')
    att_packets = reassemble_att(records)
    
    # Print ALL FD02 writes (handle 0x000C)
    print("\nFD02 (handle 0x000C) writes:")
    for ap in att_packets:
        d = ap['data']
        if len(d) < 4:
            continue
        op = d[0]
        handle = d[1] | (d[2] << 8)
        value = d[3:]
        if handle == 0x000C and ap['dir'] == 'TX':
            print(f"  ts={ap['ts']:.3f} {value.hex()}")
    
    # Print ALL FD03 notifications (handle 0x000E)
    print("\nFD03 (handle 0x000E) notifications:")
    for ap in att_packets:
        d = ap['data']
        if len(d) < 4:
            continue
        handle = d[1] | (d[2] << 8)
        value = d[3:]
        if handle == 0x000E and ap['dir'] == 'RX':
            print(f"  ts={ap['ts']:.3f} {value.hex()}")
    
    # Also check: any unknown command types on AE01/AE02?
    cmd_types = set()
    for ap in att_packets:
        d = ap['data']
        if len(d) < 4:
            continue
        handle = d[1] | (d[2] << 8)
        value = d[3:]
        if handle in (0x0006, 0x0008) and len(value) >= 8 and value[0:3] == b'\xfe\xdc\xba' and value[-1] == 0xef:
            cmd = value[4]
            cmd_types.add(cmd)
    known = {0x01, 0x03, 0x06, 0x07, 0x1b, 0x1c, 0x1d, 0x20, 0x21, 0x27}
    unknown = cmd_types - known
    print(f"\nAll cmd types: {sorted(hex(c) for c in cmd_types)}")
    if unknown:
        print(f"Unknown cmds: {sorted(hex(c) for c in unknown)}")
