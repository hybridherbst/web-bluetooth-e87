#!/usr/bin/env python3
"""
Test the Fibonacci mixing by emulating ARM64 instructions exactly.
Each instruction is: add wD, wA, wB, lsl #1  =>  D = A + B*2
                  or: add wD, wA, wB          =>  D = A + B
"""

def fibonacci_mix(s):
    """Direct ARM64 register emulation of 0x125c-0x1364."""
    # Initial register assignment from loads at 0x121c-0x1258
    r = {}
    r[16] = s[0]   # w16 = ldrb [x0, #0x0]
    r[17] = s[1]   # w17 = ldrb [x0, #0x1]
    r[3]  = s[2]   # w3  = ldrb [x0, #0x2]
    r[4]  = s[3]   # w4  = ldrb [x0, #0x3]
    r[5]  = s[4]   # w5  = ldrb [x0, #0x4]
    r[6]  = s[5]   # w6  = ldrb [x0, #0x5]
    r[7]  = s[6]   # w7  = ldrb [x0, #0x6]
    r[19] = s[7]   # w19 = ldrb [x0, #0x7]
    r[20] = s[8]   # w20 = ldrb [x0, #0x8]
    r[21] = s[9]   # w21 = ldrb [x0, #0x9]
    r[22] = s[10]  # w22 = ldrb [x0, #0xa]
    r[23] = s[11]  # w23 = ldrb [x0, #0xb]
    r[24] = s[12]  # w24 = ldrb [x0, #0xc]
    r[25] = s[13]  # w25 = ldrb [x0, #0xd]
    r[26] = s[14]  # w26 = ldrb [x0, #0xe]
    r[27] = s[15]  # w27 = ldrb [x0, #0xf]

    def add2(d, a, b):
        """add wD, wA, wB, lsl #1  =>  D = A + B*2"""
        r[d] = (r[a] + r[b] * 2) & 0xFFFFFFFF
    def add1(d, a, b):
        """add wD, wA, wB  =>  D = A + B"""
        r[d] = (r[a] + r[b]) & 0xFFFFFFFF

    # Stage 1: 0x125c-0x1298
    # 125c: add w28, w17, w16, lsl #1
    add2(28, 17, 16)
    # 1260: add w16, w17, w16
    add1(16, 17, 16)
    # 1264: add w17, w4, w3, lsl #1
    add2(17, 4, 3)
    # 1268: add w3, w4, w3
    add1(3, 4, 3)
    # 126c: add w4, w6, w5, lsl #1
    add2(4, 6, 5)
    # 1270: add w5, w6, w5
    add1(5, 6, 5)
    # 1274: add w6, w19, w7, lsl #1
    add2(6, 19, 7)
    # 1278: add w7, w19, w7
    add1(7, 19, 7)
    # 127c: add w19, w21, w20, lsl #1
    add2(19, 21, 20)
    # 1280: add w20, w21, w20
    add1(20, 21, 20)
    # 1284: add w21, w23, w22, lsl #1
    add2(21, 23, 22)
    # 1288: add w22, w23, w22
    add1(22, 23, 22)
    # 128c: add w23, w25, w24, lsl #1
    add2(23, 25, 24)
    # 1290: add w24, w25, w24
    add1(24, 25, 24)
    # 1294: add w25, w27, w26, lsl #1
    add2(25, 27, 26)
    # 1298: add w26, w27, w26
    add1(26, 27, 26)

    # Stage 2: 0x129c-0x12d8
    # 129c: add w27, w22, w19, lsl #1
    add2(27, 22, 19)
    # 12a0: add w19, w22, w19
    add1(19, 22, 19)
    # 12a4: add w22, w26, w23, lsl #1
    add2(22, 26, 23)
    # 12a8: add w23, w26, w23
    add1(23, 26, 23)
    # 12ac: add w26, w16, w17, lsl #1
    add2(26, 16, 17)
    # 12b0: add w16, w17, w16
    add1(16, 17, 16)
    # 12b4: add w17, w5, w6, lsl #1
    add2(17, 5, 6)
    # 12b8: add w5, w6, w5
    add1(5, 6, 5)
    # 12bc: add w6, w20, w21, lsl #1
    add2(6, 20, 21)
    # 12c0: add w20, w21, w20
    add1(20, 21, 20)
    # 12c4: add w21, w24, w25, lsl #1
    add2(21, 24, 25)
    # 12c8: add w24, w25, w24
    add1(24, 25, 24)
    # 12cc: add w25, w7, w28, lsl #1
    add2(25, 7, 28)
    # 12d0: add w7, w7, w28
    add1(7, 7, 28)
    # 12d4: add w28, w3, w4, lsl #1
    add2(28, 3, 4)
    # 12d8: add w3, w4, w3
    add1(3, 4, 3)

    # x9 increment at 12dc (not relevant for mixing)

    # Stage 3: 0x12e0-0x131c
    # 12e0: add w4, w24, w6, lsl #1
    add2(4, 24, 6)
    # 12e4: add w6, w24, w6
    add1(6, 24, 6)
    # 12e8: add w24, w3, w25, lsl #1
    add2(24, 3, 25)
    # 12ec: add w3, w25, w3
    add1(3, 25, 3)
    # 12f0: add w25, w19, w22, lsl #1
    add2(25, 19, 22)
    # 12f4: add w19, w22, w19
    add1(19, 22, 19)
    # 12f8: add w22, w16, w17, lsl #1
    add2(22, 16, 17)
    # 12fc: add w16, w17, w16
    add1(16, 17, 16)
    # 1300: add w17, w20, w21, lsl #1
    add2(17, 20, 21)
    # 1304: add w20, w21, w20
    add1(20, 21, 20)
    # 1308: add w21, w7, w28, lsl #1
    add2(21, 7, 28)
    # 130c: add w7, w7, w28
    add1(7, 7, 28)
    # 1310: add w28, w5, w27, lsl #1
    add2(28, 5, 27)
    # 1314: add w5, w27, w5
    add1(5, 27, 5)
    # 1318: add w27, w23, w26, lsl #1
    add2(27, 23, 26)
    # 131c: add w23, w23, w26
    add1(23, 23, 26)

    # cmp x9, #0x8 at 1320 (not relevant for mixing)

    # Stage 4: 0x1324-0x1360
    # 1324: add w26, w7, w17, lsl #1
    add2(26, 7, 17)
    # 1328: add w17, w17, w7
    add1(17, 17, 7)
    # 132c: add w7, w23, w28, lsl #1
    add2(7, 23, 28)
    # 1330: add w23, w23, w28
    add1(23, 23, 28)
    # 1334: add w28, w6, w24, lsl #1
    add2(28, 6, 24)
    # 1338: add w6, w6, w24
    add1(6, 6, 24)
    # 133c: add w24, w19, w22, lsl #1
    add2(24, 19, 22)
    # 1340: add w19, w19, w22
    add1(19, 19, 22)
    # 1344: add w22, w20, w21, lsl #1
    add2(22, 20, 21)
    # 1348: add w20, w20, w21
    add1(20, 20, 21)
    # 134c: add w21, w5, w27, lsl #1
    add2(21, 5, 27)
    # 1350: add w5, w27, w5
    add1(5, 27, 5)
    # 1354: add w27, w16, w4, lsl #1
    add2(27, 16, 4)
    # 1358: add w16, w4, w16
    add1(16, 4, 16)
    # 135c: add w4, w3, w25, lsl #1
    add2(4, 3, 25)
    # 1360: add w3, w25, w3
    add1(3, 25, 3)

    # Store-back from 0x1368-0x13a4
    # Note: strb truncates to 8 bits
    return [
        r[26] & 0xFF,  # strb w26, [x0]        out[0]
        r[17] & 0xFF,  # strb w17, [x0, #0x1]  out[1]
        r[7]  & 0xFF,  # strb w7, [x0, #0x2]   out[2]
        r[23] & 0xFF,  # strb w23, [x0, #0x3]  out[3]
        r[28] & 0xFF,  # strb w28, [x0, #0x4]  out[4]
        r[6]  & 0xFF,  # strb w6, [x0, #0x5]   out[5]
        r[24] & 0xFF,  # strb w24, [x0, #0x6]  out[6]
        r[19] & 0xFF,  # strb w19, [x0, #0x7]  out[7]
        r[22] & 0xFF,  # strb w22, [x0, #0x8]  out[8]
        r[20] & 0xFF,  # strb w20, [x0, #0x9]  out[9]
        r[21] & 0xFF,  # strb w21, [x0, #0xa]  out[10]
        r[5]  & 0xFF,  # strb w5, [x0, #0xb]   out[11]
        r[27] & 0xFF,  # strb w27, [x0, #0xc]  out[12]
        r[16] & 0xFF,  # strb w16, [x0, #0xd]  out[13]
        r[4]  & 0xFF,  # strb w4, [x0, #0xe]   out[14]
        r[3]  & 0xFF,  # strb w3, [x0, #0xf]   out[15]
    ]


# Quick test
test_input = [0xb6, 0xe0, 0x80, 0xec, 0xaf, 0xf3, 0x22, 0x91,
              0x6d, 0x88, 0xfa, 0xd5, 0xaa, 0x34, 0xc2, 0xac]
result = fibonacci_mix(test_input)
print(f"Input:  {' '.join(f'{b:02x}' for b in test_input)}")
print(f"Output: {' '.join(f'{b:02x}' for b in result)}")

# Test with sequential input
test2 = list(range(16))
r2 = fibonacci_mix(test2)
print(f"\nInput:  {' '.join(f'{b:02x}' for b in test2)}")
print(f"Output: {' '.join(f'{b:02x}' for b in r2)}")
