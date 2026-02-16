#!/usr/bin/env python3
"""
Jieli RCSP Auth crypto - clean reimplementation from ARM64 disassembly of libjl_auth.so

Auth protocol flow:
1. App generates 17 random bytes (byte[0]=0x00) via getRandomAuthData()
2. App sends these 17 bytes to device on AE01 (raw, no FE frame)
3. Device replies on AE02 with 17 bytes (byte[0]=0x00 or 0x01, bytes[1:17]=challenge)
4. App encrypts challenge via getEncryptedAuthData() -> 17 bytes (byte[0]=0x01)
5. App sends encrypted response on AE01
6. Device may send another challenge (back to step 3) or send [0x02, 'p','a','s','s'] = success
7. Only AFTER "pass" can FE-framed commands be sent
"""
import os

# ============================================================
# Tables extracted from libjl_auth.so
# ============================================================

# Key schedule table: 256 bytes at virtual address 0x1b4c
# (read from the .so file directly)
KS_TABLE = None

# S-box at virtual address 0x1c4c (256 bytes)
SBOX = None

# Inverse S-box at virtual address 0x1d4c (256 bytes) 
ISBOX = None

def _load_tables():
    global KS_TABLE, SBOX, ISBOX
    so_path = os.path.join(os.path.dirname(__file__), 'native-libs/lib/arm64-v8a/libjl_auth.so')
    with open(so_path, 'rb') as f:
        f.seek(0x1b4c)
        KS_TABLE = list(f.read(256))
        f.seek(0x1c4c)
        SBOX = list(f.read(256))
        f.seek(0x1d4c)
        ISBOX = list(f.read(256))

_load_tables()

# Static key at .data 0x4060 (16 bytes)
STATIC_KEY = [0x06, 0x77, 0x5f, 0x87, 0x91, 0x8d, 0xd4, 0x23,
              0x00, 0x5d, 0xf1, 0xd8, 0xcf, 0x0c, 0x14, 0x2b]

# Magic key at .data 0x4070 (6 bytes) 
MAGIC = [0x11, 0x22, 0x33, 0x33, 0x22, 0x11]


# ============================================================
# sub_1038: Key Schedule Generator
# ============================================================
def key_schedule(data16):
    """
    Generate 272-byte key schedule from 16-byte input.
    
    Output layout (17 blocks of 16 bytes):
      out[0..15]   = original data16
      out[16..31]  = round 0
      out[32..47]  = round 1
      ...
      out[256..271] = round 15
    """
    out = [0] * 272
    
    # Copy input to block 0
    for i in range(16):
        out[i] = data16[i]
    
    # Build 17-byte circular buffer: bytes 0-15 = data, byte 16 = XOR checksum
    buf = list(data16[:16])
    checksum = 0
    for b in data16:
        checksum ^= b
    checksum &= 0xFF
    buf.append(checksum)  # buf[16] = checksum
    
    # 16 rounds of key expansion
    for rnd in range(16):
        # Rotate each byte in the 17-byte buffer left by 3 bits
        for i in range(17):
            b = buf[i]
            buf[i] = ((b << 3) | (b >> 5)) & 0xFF
        
        # Circular read starting at position (rnd + 1) % 17, for 16 bytes
        read_pos = (rnd + 1) % 17
        
        # Table read: backwards from KS_TABLE[0xF + rnd*16]
        for j in range(16):
            src = buf[read_pos]
            tbl_idx = 0xF + rnd * 16 - j
            tbl = KS_TABLE[tbl_idx]
            out[16 + rnd * 16 + j] = (tbl + src) & 0xFF
            
            read_pos += 1
            if read_pos > 16:  # wrap at 17 (buffer is 0..16)
                read_pos = 0
    
    return out


# ============================================================
# sub_11b8: Block Cipher
# ============================================================
def block_cipher(state, expanded_key, mode):
    """
    8-round block cipher operating on 16-byte state.
    
    state: 16-byte mutable list (modified in place)
    expanded_key: 272-byte key schedule
    mode: 0 or 1
    
    The cipher uses a bit mask 0x9999 to determine per-byte operations.
    Bit positions 0,3,4,7,8,11,12,15 are SET in 0x9999.
    """
    MASK = 0x9999
    
    # Save initial state for mode=1 mixing
    initial_state = list(state)
    
    # key pointer starts at expanded_key, advances by 0x20 per round
    # (actually, the asm has x15 starting at expanded_key and incrementing by 0x20
    #  after mixing phase but before the conditional/SBOX phases)
    
    for rnd in range(8):
        # ========================================
        # Phase 1: Fibonacci-like pair mixing
        # ========================================
        # 3 stages of butterfly pair mixing
        s = list(state)
        
        # Stage 1: adjacent pairs
        pairs = []
        for p in range(0, 16, 2):
            a, b = s[p], s[p+1]
            hi = (b + a * 2) & 0xFF
            lo = (a + b) & 0xFF
            pairs.append((hi, lo))
        # pairs[0]=(w28,w16), pairs[1]=(w17,w3), pairs[2]=(w4,w5),
        # pairs[3]=(w6,w7), pairs[4]=(w19,w20), pairs[5]=(w21,w22),
        # pairs[6]=(w23,w24), pairs[7]=(w25,w26)
        w28, w16 = pairs[0]
        w17, w3 = pairs[1]
        w4, w5 = pairs[2]
        w6, w7 = pairs[3]
        w19, w20 = pairs[4]
        w21, w22 = pairs[5]
        w23, w24 = pairs[6]
        w25, w26 = pairs[7]
        
        # Stage 2: cross-pair mixing
        w27 = (w22 + w19 * 2) & 0xFF; w19 = (w22 + w19) & 0xFF
        w22 = (w26 + w23 * 2) & 0xFF; w23 = (w26 + w23) & 0xFF
        w26 = (w16 + w17 * 2) & 0xFF; w16 = (w17 + w16) & 0xFF
        w17_t = (w5 + w6 * 2) & 0xFF; w5 = (w6 + w5) & 0xFF
        w6 = (w20 + w21 * 2) & 0xFF; w20 = (w21 + w20) & 0xFF
        w21 = (w24 + w25 * 2) & 0xFF; w24 = (w25 + w24) & 0xFF
        w25 = (w7 + w28 * 2) & 0xFF; w7 = (w7 + w28) & 0xFF
        w28 = (w3 + w4 * 2) & 0xFF; w3 = (w4 + w3) & 0xFF
        w17 = w17_t
        
        # Stage 3a
        w4 = (w24 + w6 * 2) & 0xFF; w6 = (w24 + w6) & 0xFF
        w24 = (w3 + w25 * 2) & 0xFF; w3 = (w25 + w3) & 0xFF
        w25 = (w19 + w22 * 2) & 0xFF; w19 = (w22 + w19) & 0xFF
        w22_t = (w16 + w17 * 2) & 0xFF; w16 = (w17 + w16) & 0xFF
        w17_t = (w20 + w21 * 2) & 0xFF; w20 = (w21 + w20) & 0xFF
        w21 = (w7 + w28 * 2) & 0xFF; w7 = (w7 + w28) & 0xFF
        w28 = (w5 + w27 * 2) & 0xFF; w5 = (w27 + w5) & 0xFF
        w27 = (w23 + w26 * 2) & 0xFF; w23 = (w23 + w26) & 0xFF
        w22 = w22_t
        w17 = w17_t
        
        # Stage 3b
        w26 = (w7 + w17 * 2) & 0xFF; w17 = (w17 + w7) & 0xFF
        w7 = (w23 + w28 * 2) & 0xFF; w23 = (w23 + w28) & 0xFF
        w28 = (w6 + w24 * 2) & 0xFF; w6 = (w6 + w24) & 0xFF
        w24 = (w19 + w22 * 2) & 0xFF; w19 = (w19 + w22) & 0xFF
        w22 = (w20 + w21 * 2) & 0xFF; w20 = (w20 + w21) & 0xFF
        w21 = (w5 + w27 * 2) & 0xFF; w5 = (w27 + w5) & 0xFF
        w27 = (w16 + w4 * 2) & 0xFF; w16 = (w4 + w16) & 0xFF
        w4 = (w3 + w25 * 2) & 0xFF; w3 = (w25 + w3) & 0xFF
        
        # Store back
        state[0] = w26 & 0xFF
        state[1] = w17 & 0xFF
        state[2] = w7 & 0xFF
        state[3] = w23 & 0xFF
        state[4] = w28 & 0xFF
        state[5] = w6 & 0xFF
        state[6] = w24 & 0xFF
        state[7] = w19 & 0xFF
        state[8] = w22 & 0xFF
        state[9] = w20 & 0xFF
        state[10] = w21 & 0xFF
        state[11] = w5 & 0xFF
        state[12] = w27 & 0xFF
        state[13] = w16 & 0xFF
        state[14] = w4 & 0xFF
        state[15] = w3 & 0xFF
        
        # After 8th round (rnd==7), skip to final mixing
        if rnd == 7:
            break
        
        # x15 pointer is at expanded_key + (rnd+1) * 0x20
        ek_base = (rnd + 1) * 0x20
        
        # ========================================
        # Phase 2: Conditional add/xor with initial state (mode=1, rnd==1 only)
        # ========================================
        if mode != 0 and rnd == 1:
            for i in range(16):
                bit = (1 << i) & MASK
                if bit:
                    state[i] = state[i] ^ initial_state[i]
                else:
                    state[i] = (initial_state[i] + state[i]) & 0xFF
        
        # ========================================
        # Phase 3: Add/XOR with key schedule (from x15)
        # ========================================
        # x15 points to expanded_key + ek_base
        # This reads from x15[0..15] = expanded_key[ek_base..ek_base+15]
        for i in range(16):
            bit = (1 << i) & MASK
            if bit:
                state[i] = state[i] ^ expanded_key[ek_base + i]
            else:
                state[i] = (expanded_key[ek_base + i] + state[i]) & 0xFF
        
        # ========================================
        # Phase 4: S-box substitution
        # ========================================
        # Positions 0,3,4,7,8,11,12,15 use SBOX
        # Positions 1,2,5,6,9,10,13,14 use ISBOX
        for pos in [0, 3, 4, 7, 8, 11, 12, 15]:
            state[pos] = SBOX[state[pos]]
        for pos in [1, 2, 5, 6, 9, 10, 13, 14]:
            state[pos] = ISBOX[state[pos]]
        
        # ========================================
        # Phase 5: XOR/ADD with next key schedule block
        # ========================================
        # Reads from x15[16..31] = expanded_key[ek_base + 16 .. ek_base + 31]
        ek_off2 = ek_base + 16
        for i in range(16):
            bit = (1 << i) & MASK
            if bit:
                # Note: Phase 5 swaps XOR/ADD compared to Phase 3!
                # Phase 3: mask set -> XOR; Phase 5: mask set -> ADD
                state[i] = (expanded_key[ek_off2 + i] + state[i]) & 0xFF
            else:
                state[i] = state[i] ^ expanded_key[ek_off2 + i]
    
    # ========================================
    # Final mixing (after 8 rounds) at 0x1568
    # ========================================
    # Uses expanded_key at offset 0x100 (256) = last block
    ek_final = 0x100
    for i in range(16):
        bit = (1 << i) & MASK
        if bit:
            state[i] = state[i] ^ expanded_key[ek_final + i]
        else:
            state[i] = (expanded_key[ek_final + i] + state[i]) & 0xFF
    
    return state


# ============================================================
# function_E1test: Main encryption
# ============================================================
def function_E1test(key6, input16, seed16):
    """
    Main encryption function.
    
    key6: 6-byte key (MAGIC)
    input16: 16-byte input (from device challenge)
    seed16: 16-byte seed (STATIC_KEY)
    
    Returns: 16-byte encrypted output
    """
    # Expand 6-byte key to 16 bytes by repeating
    expanded_key = [key6[i % 6] for i in range(16)]
    
    # Copy input to output
    output = list(input16[:16])
    
    # Generate key schedule from output
    ks = key_schedule(output)
    
    # Apply block cipher with mode=0
    block_cipher(output, ks, 0)
    
    # XOR+ADD mixing: output[i] = expanded_key[i] + (output[i] ^ input[i])
    for i in range(16):
        output[i] = (expanded_key[i] + (output[i] ^ input16[i])) & 0xFF
    
    # Obfuscate seed16
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
    
    # Generate key schedule from obfuscated seed
    ks2 = key_schedule(obf)
    
    # Apply block cipher to output with mode=1
    block_cipher(output, ks2, 1)
    
    return output


# ============================================================
# function_E21: Second encryption function  
# ============================================================
def function_E21(key6, input16, output16):
    """
    Second encryption function at offset 0xea8.
    Similar to function_E1test but:
    - Key expansion is different: repeats 6-byte key then wraps with modulo 6
      specifically: out[0..5]=key[0..5], out[6..11]=key[0..5], out[12..15]=key[0..3]
      This is the same as E1test.
    - Copies key6 to output (with repeat to 16 bytes, but only first 6 then pattern)
    - Actually the code shows: copies input16 to a local buffer (sp[0x8..0x17])
      and copies key6 to output (repeating the 6-byte pattern to fill 16)
    - Then applies key_schedule on the local buffer (obfuscated with XOR 6 on last byte)
    - Then block_cipher with mode=1
    
    Actually looking at the disasm again more carefully...
    E21 takes (x0=key6, x1=input, x2=output):
    - Mallocs 272 bytes (temp)
    - Copies key6[0..5] to output[0..5], then repeats to fill 16 bytes  
    - Copies input[0..15] to sp[0x8..0x17] (local buffer)
    - sp[0x17] ^= 6 (last byte of local = input[15] ^ 6)
    - key_schedule(sp[0x8]) -> temp
    - block_cipher(output, temp, 1)
    - Free temp
    """
    # Copy key6 repeated to fill output
    output = [0] * 16
    for i in range(16):
        output[i] = key6[i % 6]
    
    # Local = input copy with last byte XORed with 6
    local = list(input16[:16])
    local[15] ^= 0x06  # At 0xfe8: eor w8, w8, #0x6
    
    # Key schedule from local
    ks = key_schedule(local)
    
    # Block cipher with mode=1
    block_cipher(output, ks, 1)
    
    return output


# ============================================================
# Public API functions
# ============================================================
def get_random_auth_data():
    """Generate 17 random bytes for auth initiation. Byte 0 = 0x00."""
    result = bytearray(17)
    result[0] = 0x00
    rand_bytes = os.urandom(16)
    for i in range(16):
        result[1 + i] = rand_bytes[i]
    return list(result)


def get_encrypted_auth_data(device_data_17):
    """
    Encrypt device challenge data.
    
    device_data_17: 17 bytes from device (byte[0]=type, bytes[1:17]=challenge)
    Returns: 17 bytes (byte[0]=0x01, bytes[1:17]=encrypted)
    """
    input_data = list(device_data_17[1:17])
    encrypted = function_E1test(MAGIC, input_data, list(STATIC_KEY))
    return [0x01] + encrypted


def is_valid_auth_data(data):
    """Check if received auth data is valid (from Java isValidAuthData)."""
    if not data or len(data) == 0:
        return False
    if len(data) == 5 and data[0] == 2:
        return True  # Auth success: [0x02, 'p', 'a', 's', 's']
    if len(data) == 17 and (data[0] == 0 or data[0] == 1):
        return True  # Challenge data
    return False


def is_auth_success(data):
    """Check if auth response indicates success."""
    return (len(data) == 5 and data[0] == 2 and 
            data[1] == 0x70 and data[2] == 0x61 and 
            data[3] == 0x73 and data[4] == 0x73)  # "pass"


# ============================================================
# Test
# ============================================================
if __name__ == '__main__':
    print("S-box verification:", "PASS" if all(SBOX[ISBOX[x]] == x for x in range(256)) else "FAIL")
    
    # Test random data generation
    rand = get_random_auth_data()
    print(f"Random auth ({len(rand)} bytes): {' '.join(f'{b:02x}' for b in rand)}")
    assert rand[0] == 0x00
    assert len(rand) == 17
    
    # Test encryption with a fake challenge
    challenge = [0x01] + [0x3A, 0x02, 0x12, 0x6F, 0x00, 0x00, 0x00, 0x00,
                          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    result = get_encrypted_auth_data(challenge)
    print(f"Encrypted ({len(result)} bytes): {' '.join(f'{b:02x}' for b in result)}")
    assert result[0] == 0x01
    assert len(result) == 17
    
    # Test key schedule
    ks = key_schedule([0] * 16)
    print(f"Key schedule block 0: {' '.join(f'{b:02x}' for b in ks[0:16])}")
    print(f"Key schedule block 1: {' '.join(f'{b:02x}' for b in ks[16:32])}")
    
    # Another test with all-FF input
    challenge2 = [0x00] + [0xFF] * 16
    result2 = get_encrypted_auth_data(challenge2)
    print(f"Encrypted2 ({len(result2)} bytes): {' '.join(f'{b:02x}' for b in result2)}")
    
    print("\nAll basic tests passed!")
