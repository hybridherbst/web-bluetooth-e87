#!/usr/bin/env python3
"""Decode the JNI method table and S-box tables from libjl_auth.so"""
import struct

# JNI method table at 0x4000, 4 methods
data = bytes.fromhex(
    'a01e000000000000' + 'ab1e000000000000' + 'd017000000000000' +
    'af1e000000000000' + 'c11e000000000000' + '7c18000000000000' +
    'c61e000000000000' + 'd11e000000000000' + '8819000000000000' +
    'd71e000000000000' + 'ec1e000000000000' + '2c1a000000000000'
)

print("=== JNI Method Table ===")
for i in range(4):
    off = i * 24
    name_ptr = struct.unpack_from('<Q', data, off)[0]
    sig_ptr = struct.unpack_from('<Q', data, off + 8)[0]
    fn_ptr = struct.unpack_from('<Q', data, off + 16)[0]
    print(f"Method {i}: name=0x{name_ptr:x}, sig=0x{sig_ptr:x}, fn=0x{fn_ptr:x}")

# String offsets from .rodata at end of file:
# 0x1e9f: "nativeInit"
# 0x1eab: "()Z"
# 0x1eaf: "getRandomAuthData" 
# 0x1ec1: "()[B"
# 0x1ec6: "setLinkKey"
# 0x1ed1: "([B)I"
# 0x1ed7: "getEncryptedAuthData"
# 0x1eec: "([B)[B"

# So:
# Method 0: nativeInit()Z -> 0x17d0
# Method 1: getRandomAuthData()[B -> 0x187c  
# Method 2: setLinkKey([B)I -> 0x1988
# Method 3: getEncryptedAuthData([B)[B -> 0x1a2c

# S-box tables from .rodata
# Table at 0x1b4c (used via x10 at offset 0xc4c from adrp 0x1000)
# 0x1000 + 0xc4c = 0x1c4c  -> SBOX (256 bytes)
# 0x1000 + 0xd4c = 0x1d4c  -> inverse SBOX (256 bytes)

rodata_hex = (
    # From 0x1b3c
    "77f15624 7e471b86 bd708e1e 3b731603"
    "64ac285a c9b337c5 0a10b7a3 bab19746"
    "3d05dc66 6ef69af8 0d589567 c6aaabec"
    "a0689b96 d4ebbf43 4936e96a 89d8c38a"
    "946399bc 7bbec122 bb5c71d5 1f92575d"
    "8f44411d 51e64017 fbfd1932 34b8612a"
    "ca236fda 39f7a201 7fd631e7 de8004dd"
    "2c5982af a8e00fcd a1123e30 d11cd03a"
    "33722e4f 90021306 75ce87c2 efb2ad7d"
    "3815e152 9f7a6c2f 27c4e281 a9cf8dc0"
    "d7dfff60 76148c5e 5509e408 c74220fc"
    "d25091d9 4c629ee8 b9a6f91a 00210bfa"
    "359c4e4b 6948cb0e c8a45bea 8407b418"
    "f4ae6bdb a7cc3f8b 4a0c3c25 e5544d45"
    "83ed11f0 b05393f2 7426b59d 6d7cf32d"
)

# Clean hex
rodata_hex = rodata_hex.replace(" ", "")
rodata_bytes = bytes.fromhex(rodata_hex)

print(f"\n=== Raw rodata from 0x1b3c ({len(rodata_bytes)} bytes) ===")

# The SBOX table starts at 0x1c4c relative to file
# 0x1c4c - 0x1b3c = 0x110 = 272 offset into our rodata dump
sbox_offset = 0x1c4c - 0x1b3c
print(f"\nSBOX offset in dump: {sbox_offset} (0x{sbox_offset:x})")

# But we only have data from 0x1b3c to ~0x1b3c + len(rodata_bytes)
# That's 0x1b3c to about 0x1c7b - not enough for the full SBOX

# Let me use the full rodata dump instead
full_rodata_hex = (
    # 0x1b3c
    "77f156247e471b86bd708e1e3b731603"
    "64ac285ac9b337c50a10b7a3bab19746"
    "3d05dc666ef69af80d589567c6aaabec"
    "a0689b96d4ebbf434936e96a89d8c38a"
    "946399bc7bbec122bb5c71d51f92575d"
    "8f44411d51e64017fbfd193234b8612a"
    "ca236fda39f7a2017fd631e7de8004dd"
    "2c5982afa8e00fcda1123e30d11cd03a"
    "33722e4f9002130675ce87c2efb2ad7d"
    "3815e1529f7a6c2f27c4e281a9cf8dc0"
    "d7dfff60 76148c5e 5509e408 c74220fc"
    "d25091d9 4c629ee8 b9a6f91a 00210bfa"
    "359c4e4b 6948cb0e c8a45bea 8407b418"
    "f4ae6bdb a7cc3f8b 4a0c3c25 e5544d45"
    "83ed11f0 b05393f2 7426b59d 6d7cf32d"
    # 0x1c2c (continuation from second block in objdump)
    "f156247e 471b86bd 708e1e3b 731603b6"
    "ac285ac9 b337c50a 10b7a3ba b1974688"
    # 0x1c4c - this IS the SBOX start
    "012de293 be4515ae 780387a4 b838cf3f"
    "08670994 eb26a86b bd18341b bbbf72f7"
    "4035489c 512f3b55 e3c09fd8 d3f38db1"
    "ffa73edc 8677d7a6 11fbf4ba 92916483"
    "f133efda 2cb5b22b 88d199cb 8c841d14"
    "819771ca 5fa38b57 3c82c452 5c1ce8a0"
    "04b4854a f61354b6 df0c1a8e dee039fc"
    "209b244e a9989eab f260d06c eafac7d9"
    "00d41f6e 43bcec53 89fe7a5d 49c932c2"
    "f99af86d 16db5996 44e9cde6 46428f0a"
    "c1ccb965 b0d2c6ac 1e416229 2e0e7450"
    "025ac325 7b8a2a5b f0060d47 6f709d7e"
    "10ce1227 d54c4fd6 79306836 757de4ed"
    "806a9037 a25e76aa c57f3daf a5e51961"
    "fd4d7cb7 0beead4b 22f5e773 2321c805"
    "e166ddb3 58696356 0fa13195 17073a28"
    # 0x1d4c - this IS the inverse SBOX start
    "8000b009 60efb9fd 10129fe4 69baadf8"
    "c038c265 4f0694fc 19de6a1b 5d4ea882"
    "70ede8ec 72b315c3 ffabb647 4401ac25"
    "c9fa8e41 1a21cbd3 0d6efe26 58da320f"
    "20a99d84 98059cbb 228c63e7 c5e173c6"
    "af245b87 6627f757 f496b1b7 5c8bd554"
    "79dfaaf6 3ea3f111 caf5d117 7b9383bc"
    "bd521eeb aeccd635 08c88ab4 e2cdbfd9"
    "d050593f 4d62340a 4888b556 4c2e6b9e"
    "d23d3c03 13fb9751 754a9171 23be762a"
    "5ff9d455 0bdc3731 1674d777 a7e607db"
    "a42f46f3 614567e3 0ca23b1c 8518041d"
    "29a08fb2 5ad8a67e ee8d534b a19ac10e"
    "7a49a52c 81c4c736 2bf74395 33f26c68"  # Note: corrected 7f->f7 if needed
    "6df00228 cedd9bea 5e997c14 86cfe542"
    "b840782d 3ae9641f 92907d39 6fe08930"
)

full_rodata_hex = full_rodata_hex.replace(" ", "")
full_rodata = bytes.fromhex(full_rodata_hex)

# SBOX at offset 0x1c4c - 0x1b3c = 0x110 = 272
sbox_start = 0x1c4c - 0x1b3c
sbox = full_rodata[sbox_start:sbox_start+256]
print(f"\n=== SBOX (at 0x1c4c, {len(sbox)} bytes) ===")
print("[" + ", ".join(f"0x{b:02x}" for b in sbox) + "]")

# Inverse SBOX at offset 0x1d4c - 0x1b3c = 0x210 = 528
isbox_start = 0x1d4c - 0x1b3c
isbox = full_rodata[isbox_start:isbox_start+256]
print(f"\n=== Inverse SBOX (at 0x1d4c, {len(isbox)} bytes) ===")
print("[" + ", ".join(f"0x{b:02x}" for b in isbox) + "]")

# Verify: SBOX[ISBOX[x]] should equal x for all x
print("\n=== Verifying SBOX/ISBOX inverse relationship ===")
ok = True
for x in range(256):
    if sbox[isbox[x]] != x:
        print(f"MISMATCH at {x}: SBOX[ISBOX[{x}]] = SBOX[{isbox[x]}] = {sbox[isbox[x]]}")
        ok = False
if ok:
    print("✓ SBOX and ISBOX are perfect inverses!")
else:
    print("✗ SBOX/ISBOX mismatch detected")

# Also extract the static key from .data at offset 0x4060
static_key_hex = "06775f87918dd42300 5df1d8cf0c142b"
print(f"\n=== Static key at 0x4060 ===")
key_bytes = bytes.fromhex("06775f87918dd423005df1d8cf0c142b")
print("[" + ", ".join(f"0x{b:02x}" for b in key_bytes) + "]")

# And the magic bytes at 0x4070
magic_hex = "1122333322110000"
magic_bytes = bytes.fromhex("11223333221100")
print(f"\n=== Magic at 0x4070 ===")
print("[" + ", ".join(f"0x{b:02x}" for b in magic_bytes) + "]")
