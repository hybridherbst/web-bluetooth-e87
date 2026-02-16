#!/usr/bin/env python3
"""
Jieli RCSP Auth crypto - v3 with correct block cipher structure.
Verified against ARM64 disassembly of libjl_auth.so.
"""
import os

# Load tables from .so file
so_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'native-libs/lib/arm64-v8a/libjl_auth.so')
with open(so_path, 'rb') as f:
    f.seek(0x1b4c); KS_TABLE = list(f.read(256))
    f.seek(0x1c4c); SBOX = list(f.read(256))
    f.seek(0x1d4c); ISBOX = list(f.read(256))

STATIC_KEY = [0x06, 0x77, 0x5f, 0x87, 0x91, 0x8d, 0xd4, 0x23,
              0x00, 0x5d, 0xf1, 0xd8, 0xcf, 0x0c, 0x14, 0x2b]
MAGIC = [0x11, 0x22, 0x33, 0x33, 0x22, 0x11]
MASK = 0x9999


def key_schedule(data16):
    """272-byte key schedule from 16-byte input."""
    out = [0] * 272
    for i in range(16):
        out[i] = data16[i]

    buf = list(data16[:16])
    checksum = 0
    for b in data16:
        checksum ^= b
    buf.append(checksum & 0xFF)

    for rnd in range(16):
        for i in range(17):
            b = buf[i]
            buf[i] = ((b << 3) | (b >> 5)) & 0xFF

        read_pos = (rnd + 1) % 17
        for j in range(16):
            src = buf[read_pos]
            tbl_idx = 0xF + rnd * 16 - j
            out[16 + rnd * 16 + j] = (KS_TABLE[tbl_idx] + src) & 0xFF
            read_pos += 1
            if read_pos > 16:
                read_pos = 0
    return out


def fibonacci_mix(s):
    """
    Direct ARM64 register emulation of Fibonacci butterfly mixing (0x121c-0x1364).
    Each pair of instructions: add wD, wA, wB, lsl #1 = D = A + B*2
                               add wD, wA, wB         = D = A + B
    """
    r = {}
    r[16]=s[0]; r[17]=s[1]; r[3]=s[2]; r[4]=s[3]
    r[5]=s[4]; r[6]=s[5]; r[7]=s[6]; r[19]=s[7]
    r[20]=s[8]; r[21]=s[9]; r[22]=s[10]; r[23]=s[11]
    r[24]=s[12]; r[25]=s[13]; r[26]=s[14]; r[27]=s[15]

    M = 0xFFFFFFFF
    # Stage 1 (0x125c-0x1298)
    r[28]=(r[17]+r[16]*2)&M; r[16]=(r[17]+r[16])&M
    r[17]=(r[4]+r[3]*2)&M;   r[3]=(r[4]+r[3])&M
    r[4]=(r[6]+r[5]*2)&M;    r[5]=(r[6]+r[5])&M
    r[6]=(r[19]+r[7]*2)&M;   r[7]=(r[19]+r[7])&M
    r[19]=(r[21]+r[20]*2)&M;  r[20]=(r[21]+r[20])&M
    r[21]=(r[23]+r[22]*2)&M;  r[22]=(r[23]+r[22])&M
    r[23]=(r[25]+r[24]*2)&M;  r[24]=(r[25]+r[24])&M
    r[25]=(r[27]+r[26]*2)&M;  r[26]=(r[27]+r[26])&M

    # Stage 2 (0x129c-0x12d8)
    r[27]=(r[22]+r[19]*2)&M;  r[19]=(r[22]+r[19])&M
    r[22]=(r[26]+r[23]*2)&M;  r[23]=(r[26]+r[23])&M
    r[26]=(r[16]+r[17]*2)&M;  r[16]=(r[17]+r[16])&M
    r[17]=(r[5]+r[6]*2)&M;    r[5]=(r[6]+r[5])&M
    r[6]=(r[20]+r[21]*2)&M;   r[20]=(r[21]+r[20])&M
    r[21]=(r[24]+r[25]*2)&M;  r[24]=(r[25]+r[24])&M
    r[25]=(r[7]+r[28]*2)&M;   r[7]=(r[7]+r[28])&M
    r[28]=(r[3]+r[4]*2)&M;    r[3]=(r[4]+r[3])&M

    # Stage 3 (0x12e0-0x131c)
    r[4]=(r[24]+r[6]*2)&M;    r[6]=(r[24]+r[6])&M
    r[24]=(r[3]+r[25]*2)&M;   r[3]=(r[25]+r[3])&M
    r[25]=(r[19]+r[22]*2)&M;  r[19]=(r[22]+r[19])&M
    r[22]=(r[16]+r[17]*2)&M;  r[16]=(r[17]+r[16])&M
    r[17]=(r[20]+r[21]*2)&M;  r[20]=(r[21]+r[20])&M
    r[21]=(r[7]+r[28]*2)&M;   r[7]=(r[7]+r[28])&M
    r[28]=(r[5]+r[27]*2)&M;   r[5]=(r[27]+r[5])&M
    r[27]=(r[23]+r[26]*2)&M;  r[23]=(r[23]+r[26])&M

    # Stage 4 (0x1324-0x1360)
    r[26]=(r[7]+r[17]*2)&M;   r[17]=(r[17]+r[7])&M
    r[7]=(r[23]+r[28]*2)&M;   r[23]=(r[23]+r[28])&M
    r[28]=(r[6]+r[24]*2)&M;   r[6]=(r[6]+r[24])&M
    r[24]=(r[19]+r[22]*2)&M;  r[19]=(r[19]+r[22])&M
    r[22]=(r[20]+r[21]*2)&M;  r[20]=(r[20]+r[21])&M
    r[21]=(r[5]+r[27]*2)&M;   r[5]=(r[27]+r[5])&M
    r[27]=(r[16]+r[4]*2)&M;   r[16]=(r[4]+r[16])&M
    r[4]=(r[3]+r[25]*2)&M;    r[3]=(r[25]+r[3])&M

    return [
        r[26]&0xFF, r[17]&0xFF, r[7]&0xFF, r[23]&0xFF,
        r[28]&0xFF, r[6]&0xFF, r[24]&0xFF, r[19]&0xFF,
        r[22]&0xFF, r[20]&0xFF, r[21]&0xFF, r[5]&0xFF,
        r[27]&0xFF, r[16]&0xFF, r[4]&0xFF, r[3]&0xFF,
    ]


def cond_mix(state, key_block, mask, phase):
    """
    Conditional XOR/ADD mixing.
    phase=3: mask set → XOR, mask clear → ADD
    phase=5: mask set → ADD, mask clear → XOR
    """
    result = list(state)
    for i in range(16):
        bit_set = ((1 << i) & mask) != 0
        if phase == 3:
            if bit_set:
                result[i] = result[i] ^ key_block[i]
            else:
                result[i] = (key_block[i] + result[i]) & 0xFF
        else:  # phase 5
            if bit_set:
                result[i] = (key_block[i] + result[i]) & 0xFF
            else:
                result[i] = result[i] ^ key_block[i]
    return result


def sbox_sub(state):
    """S-box substitution."""
    result = list(state)
    for pos in [0, 3, 4, 7, 8, 11, 12, 15]:
        result[pos] = SBOX[result[pos]]
    for pos in [1, 2, 5, 6, 9, 10, 13, 14]:
        result[pos] = ISBOX[result[pos]]
    return result


def block_cipher(state, ek, mode):
    """
    Block cipher from sub_11b8.
    
    Structure (from disassembly control flow):
    1. Save initial state
    2. Phase3(ek[0..15]) + Sbox + Phase5(ek[16..31])      [x9=0, x15=ek]
    3. Fibonacci + Phase3(ek[32..47]) + Sbox + Phase5(ek[48..63])  [x9=1, x15=ek+0x20]
    4. Fibonacci + Phase2(initial,mode) + Phase3(ek[64..79]) + Sbox + Phase5(ek[80..95])  [x9=2, x15=ek+0x40]
    5-8. Fibonacci + Phase3 + Sbox + Phase5  [x9=3..6]
    9. Fibonacci + Phase3(ek[224..239]) + Sbox + Phase5(ek[240..255])  [x9=7, x15=ek+0xe0]
    10. Fibonacci + FinalMix(ek[256..271])  [x9=8, x15=ek+0x100]
    """
    s = list(state)
    initial = list(state)  # saved at sp[0..15]

    # x9=0, x15 = ek+0 (not yet advanced)
    # Phase 3 with ek[0..15]
    s = cond_mix(s, ek[0:16], MASK, 3)
    s = sbox_sub(s)
    s = cond_mix(s, ek[16:32], MASK, 5)

    for x9 in range(1, 9):  # x9 = 1..8
        # Fibonacci mixing
        s = fibonacci_mix(s)

        # x15 has advanced to ek + x9 * 0x20
        ek_off = x9 * 0x20

        if x9 == 8:
            # Final mixing with ek[0x100..0x10f]
            s = cond_mix(s, ek[0x100:0x110], MASK, 3)
            break

        # Phase 2: mode check (x9 == 2 and mode != 0)
        if mode != 0 and x9 == 2:
            for i in range(16):
                bit_set = ((1 << i) & MASK) != 0
                if i > 15:
                    # Actually from the asm: 0x13e0: and w17, w16, #0x7f; cmp w17, #0xf; b.hi
                    # So positions > 15 use ADD. But we only go 0..15, so this never triggers.
                    s[i] = (initial[i] + s[i]) & 0xFF
                elif bit_set:
                    s[i] = s[i] ^ initial[i]
                else:
                    s[i] = (initial[i] + s[i]) & 0xFF

        # Phase 3 with ek[ek_off..ek_off+15]
        s = cond_mix(s, ek[ek_off:ek_off+16], MASK, 3)
        s = sbox_sub(s)
        # Phase 5 with ek[ek_off+16..ek_off+31]
        s = cond_mix(s, ek[ek_off+16:ek_off+32], MASK, 5)

    for i in range(16):
        state[i] = s[i]
    return state


def function_E1test(key6, input16, seed16):
    """Main encryption."""
    expanded_key = [key6[i % 6] for i in range(16)]
    output = list(input16[:16])
    ks = key_schedule(list(seed16[:16]))  # key_schedule uses SEED, not input!
    block_cipher(output, ks, 0)

    for i in range(16):
        output[i] = (expanded_key[i] + (output[i] ^ input16[i])) & 0xFF

    obf = [0] * 16
    obf[0]  = (seed16[0]  - 0x17) & 0xFF
    obf[1]  = (seed16[1]  ^ 0xE5) & 0xFF
    obf[2]  = (seed16[2]  - 0x21) & 0xFF
    obf[3]  = (seed16[3]  ^ 0xC1) & 0xFF
    obf[4]  = (seed16[4]  - 0x4D) & 0xFF
    obf[5]  = (seed16[5]  ^ 0xA7) & 0xFF
    obf[6]  = (seed16[6]  - 0x6B) & 0xFF
    obf[7]  = (seed16[7]  ^ 0x83) & 0xFF
    obf[8]  = (seed16[8]  ^ 0xE9) & 0xFF
    obf[9]  = (seed16[9]  - 0x1B) & 0xFF
    obf[10] = (seed16[10] ^ 0xDF) & 0xFF
    obf[11] = (seed16[11] - 0x3F) & 0xFF
    obf[12] = (seed16[12] ^ 0xB3) & 0xFF
    obf[13] = (seed16[13] - 0x59) & 0xFF
    obf[14] = (seed16[14] ^ 0x95) & 0xFF
    obf[15] = (seed16[15] - 0x7D) & 0xFF

    ks2 = key_schedule(obf)
    block_cipher(output, ks2, 1)
    return output


def get_random_auth_data():
    result = bytearray(17)
    result[0] = 0x00
    for i in range(16):
        result[1 + i] = os.urandom(1)[0]
    return list(result)


def get_encrypted_auth_data(device_data_17):
    input_data = list(device_data_17[1:17])
    encrypted = function_E1test(MAGIC, input_data, list(STATIC_KEY))
    return [0x01] + encrypted


if __name__ == '__main__':
    print("S-box verification:", "PASS" if all(SBOX[ISBOX[x]] == x for x in range(256)) else "FAIL")

    # Test against captured auth exchange:
    # Device challenge: 00 b6 e0 80 ec af f3 22 91 6d 88 fa d5 aa 34 c2 ac
    # Expected response: 01 1d 88 97 ac 46 04 d3 32 e8 17 5e 81 bb 29 25 24
    challenge = [0x00, 0xb6, 0xe0, 0x80, 0xec, 0xaf, 0xf3, 0x22,
                 0x91, 0x6d, 0x88, 0xfa, 0xd5, 0xaa, 0x34, 0xc2, 0xac]
    expected  = [0x01, 0x1d, 0x88, 0x97, 0xac, 0x46, 0x04, 0xd3,
                 0x32, 0xe8, 0x17, 0x5e, 0x81, 0xbb, 0x29, 0x25, 0x24]

    result = get_encrypted_auth_data(challenge)
    print(f"Challenge: {' '.join(f'{b:02x}' for b in challenge)}")
    print(f"Expected:  {' '.join(f'{b:02x}' for b in expected)}")
    print(f"Got:       {' '.join(f'{b:02x}' for b in result)}")
    print(f"Match: {result == expected}")

    if result != expected:
        print("\nMismatched bytes:")
        for i in range(17):
            if result[i] != expected[i]:
                print(f"  [{i}] got 0x{result[i]:02x}, expected 0x{expected[i]:02x}")
