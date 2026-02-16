#!/usr/bin/env python3
"""Extract static key and magic from the ELF .data section"""
import struct

with open('native-libs/lib/arm64-v8a/libjl_auth.so', 'rb') as f:
    # ELF64 header
    f.seek(0x20)
    phoff = struct.unpack('<Q', f.read(8))[0]
    f.seek(0x36)
    phentsize = struct.unpack('<H', f.read(2))[0]
    phnum = struct.unpack('<H', f.read(2))[0]
    
    for i in range(phnum):
        f.seek(phoff + i * phentsize)
        p_type = struct.unpack('<I', f.read(4))[0]
        f.read(4)
        p_offset = struct.unpack('<Q', f.read(8))[0]
        p_vaddr = struct.unpack('<Q', f.read(8))[0]
        f.read(8)
        p_filesz = struct.unpack('<Q', f.read(8))[0]
        p_memsz = struct.unpack('<Q', f.read(8))[0]
        
        if p_type == 1:  # PT_LOAD
            print(f'LOAD: vaddr=0x{p_vaddr:x}, offset=0x{p_offset:x}, filesz=0x{p_filesz:x}')
            if p_vaddr <= 0x4060 < p_vaddr + p_filesz:
                file_off = p_offset + (0x4060 - p_vaddr)
                print(f'  0x4060 at file offset 0x{file_off:x}')
                f.seek(file_off)
                data = f.read(32)
                print(f'  Static key (0x4060): {[hex(b) for b in data[:16]]}')
                print(f'  Magic (0x4070):      {[hex(b) for b in data[16:22]]}')

    # Also dump the objdump .data content directly from the file
    # .data section: VMA=0x4000, look at the raw objdump output we already have
    # From objdump -s: 
    # 4060 06775f87 918dd423 005df1d8 cf0c142b
    # 4070 11223333 2211
    # These are the values!
    print()
    print("From objdump -s output:")
    print("Static key = [0x06, 0x77, 0x5f, 0x87, 0x91, 0x8d, 0xd4, 0x23, 0x00, 0x5d, 0xf1, 0xd8, 0xcf, 0x0c, 0x14, 0x2b]")
    print("Magic      = [0x11, 0x22, 0x33, 0x33, 0x22, 0x11]")
