#!/usr/bin/env python3
"""Verify crypto implementation against captured auth exchange."""
import sys
sys.path.insert(0, '.')
from jl_auth_v2 import get_encrypted_auth_data

# From the capture:
# Step 4: Device sends random challenge:
#   00 b6 e0 80 ec af f3 22 91 6d 88 fa d5 aa 34 c2 ac
# Step 5: App sends encrypted response:  
#   01 1d 88 97 ac 46 04 d3 32 e8 17 5e 81 bb 29 25 24

challenge = [0x00, 0xb6, 0xe0, 0x80, 0xec, 0xaf, 0xf3, 0x22,
             0x91, 0x6d, 0x88, 0xfa, 0xd5, 0xaa, 0x34, 0xc2, 0xac]

expected = [0x01, 0x1d, 0x88, 0x97, 0xac, 0x46, 0x04, 0xd3,
            0x32, 0xe8, 0x17, 0x5e, 0x81, 0xbb, 0x29, 0x25, 0x24]

result = get_encrypted_auth_data(challenge)

print(f"Challenge: {' '.join(f'{b:02x}' for b in challenge)}")
print(f"Expected:  {' '.join(f'{b:02x}' for b in expected)}")
print(f"Got:       {' '.join(f'{b:02x}' for b in result)}")
print(f"Match: {result == expected}")

if result != expected:
    print("\nDifferences:")
    for i in range(17):
        if result[i] != expected[i]:
            print(f"  byte[{i}]: got 0x{result[i]:02x}, expected 0x{expected[i]:02x}")

# Also test: step 1 -> step 2 
# App sends random: 00 67 c6 69 73 51 ff 4a ec 29 cd ba ab f2 fb e3 46
# Device responds:  01 02 3a 02 12 6f a2 84 87 92 36 e9 da 27 ba 0b 8d
# The device uses the same algorithm, so we should be able to verify:
# Given the app's random data, the device encrypts it using the same E1test function
# BUT: the device might use a DIFFERENT key or a different function (function_E21?)
# Let's check anyway:

app_random = [0x00, 0x67, 0xc6, 0x69, 0x73, 0x51, 0xff, 0x4a,
              0xec, 0x29, 0xcd, 0xba, 0xab, 0xf2, 0xfb, 0xe3, 0x46]
device_response = [0x01, 0x02, 0x3a, 0x02, 0x12, 0x6f, 0xa2, 0x84,
                   0x87, 0x92, 0x36, 0xe9, 0xda, 0x27, 0xba, 0x0b, 0x8d]

device_check = get_encrypted_auth_data(app_random)
print(f"\nVerify device-side (same algo):")
print(f"App random:   {' '.join(f'{b:02x}' for b in app_random)}")
print(f"Device sent:  {' '.join(f'{b:02x}' for b in device_response)}")
print(f"Our encrypt:  {' '.join(f'{b:02x}' for b in device_check)}")
print(f"Device match: {device_check == device_response}")
