#!/usr/bin/env python3
"""Figure out the pklg timestamp format by looking at raw bytes."""
import struct, datetime

raw = open('/Users/herbst/git/bluetooth-tag/cap.pklg', 'rb').read()

# Parse first 20 records
off = 0
for i in range(20):
    if off + 13 > len(raw): break
    rec_len = struct.unpack_from('<I', raw, off)[0]
    ts_bytes = raw[off+4:off+12]
    ptype = raw[off + 12]
    
    # Try various interpretations
    # 1. Two 32-bit values (LE)
    lo = struct.unpack_from('<I', raw, off+4)[0]
    hi = struct.unpack_from('<I', raw, off+8)[0]
    
    # 2. Two 32-bit values (BE)
    hi_be = struct.unpack_from('>I', raw, off+4)[0]
    lo_be = struct.unpack_from('>I', raw, off+8)[0]
    
    # 3. Full 64-bit
    full_le = struct.unpack_from('<Q', raw, off+4)[0]
    full_be = struct.unpack_from('>Q', raw, off+4)[0]
    
    # Apple's reference date is 2001-01-01
    apple_epoch = datetime.datetime(2001, 1, 1).timestamp()
    
    # Try lo as seconds since apple epoch
    try:
        d1 = datetime.datetime.fromtimestamp(lo + apple_epoch)
    except:
        d1 = None
    
    # Try hi_be as seconds since apple epoch  
    try:
        d2 = datetime.datetime.fromtimestamp(hi_be + apple_epoch)
    except:
        d2 = None
    
    # Try lo as seconds since unix epoch
    try:
        d3 = datetime.datetime.fromtimestamp(lo)
    except:
        d3 = None
    
    # Try hi_be as seconds since unix epoch
    try:
        d4 = datetime.datetime.fromtimestamp(hi_be)
    except:
        d4 = None
    
    # PacketLogger actually uses timestamp in seconds as float64 (double)
    ts_double = struct.unpack_from('<d', raw, off+4)[0]
    try:
        d5 = datetime.datetime.fromtimestamp(ts_double + apple_epoch)
    except:
        d5 = None
    
    ts_double_be = struct.unpack_from('>d', raw, off+4)[0]
    try:
        d6 = datetime.datetime.fromtimestamp(ts_double_be + apple_epoch)
    except:
        d6 = None
    
    print(f"rec {i}: type={ptype} bytes={ts_bytes.hex()}")
    print(f"  lo_le={lo} hi_le={hi}  |  hi_be={hi_be} lo_be={lo_be}")
    if d1: print(f"  lo as apple secs:    {d1}")
    if d2: print(f"  hi_be as apple secs: {d2}")
    if d3: print(f"  lo as unix secs:     {d3}")
    if d4: print(f"  hi_be as unix secs:  {d4}")
    if d5: print(f"  double_le as apple:  {d5}")
    if d6: print(f"  double_be as apple:  {d6}")
    print()
    
    off += 4 + rec_len
