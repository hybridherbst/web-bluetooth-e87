#!/usr/bin/env python3
"""
Emulate function_E1test from libjl_auth.so using Unicorn CPU emulator.
This gives us ground-truth output to compare against our Python reimplementation.
"""
import os
from unicorn import *
from unicorn.arm64_const import *

# Load the .so binary
so_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'native-libs/lib/arm64-v8a/libjl_auth.so')
with open(so_path, 'rb') as f:
    so_data = f.read()

print(f"SO size: {len(so_data)} bytes")

# Memory layout
CODE_BASE  = 0x10000       # Map the .so here
CODE_SIZE  = 0x10000       # 64KB for code + rodata
STACK_BASE = 0x80000000    # Stack
STACK_SIZE = 0x10000       # 64KB stack
DATA_BASE  = 0x90000000    # For our input/output buffers
DATA_SIZE  = 0x10000

# The .so has:
#   function_E1test at offset 0xacc
#   sub_1038 (key_schedule) at offset 0x1038
#   sub_11b8 (block_cipher) at offset 0x11b8
#   SBOX at 0x1c4c, ISBOX at 0x1d4c, KS_TABLE at 0x1b4c
#   .bss at 0x4060 (STATIC_KEY), 0x4070 (MAGIC)

# Initialize emulator
mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)

# Map memory
mu.mem_map(CODE_BASE, CODE_SIZE)
mu.mem_map(STACK_BASE, STACK_SIZE)
mu.mem_map(DATA_BASE, DATA_SIZE)

# Write the .so binary into code memory
mu.mem_write(CODE_BASE, so_data)

# Set up .bss data (STATIC_KEY at offset 0x4060, MAGIC at 0x4070)
STATIC_KEY = bytes([0x06, 0x77, 0x5f, 0x87, 0x91, 0x8d, 0xd4, 0x23,
                    0x00, 0x5d, 0xf1, 0xd8, 0xcf, 0x0c, 0x14, 0x2b])
MAGIC = bytes([0x11, 0x22, 0x33, 0x33, 0x22, 0x11])

# Write to their actual offsets in the .so mapping
mu.mem_write(CODE_BASE + 0x4060, STATIC_KEY)
mu.mem_write(CODE_BASE + 0x4070, MAGIC)

# Our test data
# Device challenge (input to getEncryptedAuthData)
challenge_17 = bytes([0x00, 0xb6, 0xe0, 0x80, 0xec, 0xaf, 0xf3, 0x22,
                      0x91, 0x6d, 0x88, 0xfa, 0xd5, 0xaa, 0x34, 0xc2, 0xac])

# Expected response
expected_17  = bytes([0x01, 0x1d, 0x88, 0x97, 0xac, 0x46, 0x04, 0xd3,
                      0x32, 0xe8, 0x17, 0x5e, 0x81, 0xbb, 0x29, 0x25, 0x24])

# Set up data buffers
INPUT_ADDR = DATA_BASE + 0x100   # input16 = challenge[1:]
OUTPUT_ADDR = DATA_BASE + 0x200  # output16
KEY6_ADDR = DATA_BASE + 0x300    # MAGIC key (6 bytes)
SEED_ADDR = DATA_BASE + 0x400   # STATIC_KEY (16 bytes)

# Write input data (the 16 bytes after the type byte)
mu.mem_write(INPUT_ADDR, challenge_17[1:17])
# Write key6 (MAGIC)
mu.mem_write(KEY6_ADDR, MAGIC)
# Write seed16 (STATIC_KEY)
mu.mem_write(SEED_ADDR, STATIC_KEY)
# Clear output
mu.mem_write(OUTPUT_ADDR, bytes(16))

# Set up stack pointer
SP = STACK_BASE + STACK_SIZE - 0x1000  # Leave room

# function_E1test signature: (x0=key6, x1=input16, x2=seed16, x3=output16)
# At offset 0xacc in the .so
FUNC_ADDR = CODE_BASE + 0xacc

# We need a return address - write a `ret` instruction somewhere
RET_ADDR = CODE_BASE + 0x3FFC  # Unused area
mu.mem_write(RET_ADDR, bytes([0xc0, 0x03, 0x5f, 0xd6]))  # ret

# Set registers
mu.reg_write(UC_ARM64_REG_X0, KEY6_ADDR)    # key6
mu.reg_write(UC_ARM64_REG_X1, INPUT_ADDR)   # input16
mu.reg_write(UC_ARM64_REG_X2, SEED_ADDR)    # seed16
mu.reg_write(UC_ARM64_REG_X3, OUTPUT_ADDR)  # output16
mu.reg_write(UC_ARM64_REG_SP, SP)
mu.reg_write(UC_ARM64_REG_LR, RET_ADDR)

# The function uses ADRP to compute addresses relative to PC.
# ADRP instructions at 0xacc need to compute:
#   adrp x8, <page of .bss> -> page containing 0x4060
# Since ADRP calculates from the PC's page, we need the code at the
# right virtual address. Let's check what ADRP targets exist.

# Actually, ADRP uses PC-relative page addressing. Since we loaded the .so
# at CODE_BASE=0x10000, and the original .so is position-independent,
# ADRP instructions will compute based on the current PC.
# 
# The .so's ADRP instructions target pages relative to their PC.
# At offset 0xacc: adrp targets need to reach offset 0x4000 (page of 0x4060/0x4070)
# PC at CODE_BASE + 0xacc = 0x10acc, page = 0x10000
# Target page for 0x4060 = CODE_BASE + 0x4000 = 0x14000
# ADRP immediate = (0x14000 - 0x10000) / 0x1000 = 4 pages -> immhi=0, immlo=4
#
# Let me check the actual ADRP encoding in the binary.

# Let's first try to run it and see what happens
print("Starting emulation of function_E1test...")
print(f"  key6 @ 0x{KEY6_ADDR:x} = {MAGIC.hex()}")
print(f"  input @ 0x{INPUT_ADDR:x} = {challenge_17[1:].hex()}")
print(f"  seed @ 0x{SEED_ADDR:x} = {STATIC_KEY.hex()}")
print(f"  output @ 0x{OUTPUT_ADDR:x}")
print(f"  func @ 0x{FUNC_ADDR:x}")
print(f"  SP = 0x{SP:x}")
print(f"  LR = 0x{RET_ADDR:x}")

# Add a hook to trace BL (branch-and-link) calls for debugging
call_count = [0]
def hook_code(uc, address, size, user_data):
    call_count[0] += 1
    if call_count[0] > 50000000:
        print(f"Too many instructions, stopping at 0x{address:x}")
        uc.emu_stop()

# Hook for memory errors
def hook_mem_invalid(uc, access, address, size, value, user_data):
    print(f"Memory error: access={access} addr=0x{address:x} size={size} value=0x{value:x}")
    # Try to map the memory and continue
    page = address & ~0xFFF
    try:
        uc.mem_map(page, 0x1000)
        uc.mem_write(page, bytes(0x1000))
        print(f"  Mapped page 0x{page:x}")
        return True
    except:
        return False

mu.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED, hook_mem_invalid)

try:
    mu.emu_start(FUNC_ADDR, RET_ADDR, timeout=10*UC_SECOND_SCALE)
    print(f"\nEmulation completed! ({call_count[0]} instructions)")
    
    # Read output
    output = mu.mem_read(OUTPUT_ADDR, 16)
    result = [0x01] + list(output)
    
    print(f"Output:   {' '.join(f'{b:02x}' for b in result)}")
    print(f"Expected: {' '.join(f'{b:02x}' for b in expected_17)}")
    print(f"Match: {result == list(expected_17)}")
    
except UcError as e:
    pc = mu.reg_read(UC_ARM64_REG_PC)
    print(f"Emulation error: {e} at PC=0x{pc:x} (offset 0x{pc - CODE_BASE:x})")
    
    # Read some registers for debugging
    for i in range(10):
        val = mu.reg_read(UC_ARM64_REG_X0 + i)
        print(f"  x{i} = 0x{val:x}")
    sp = mu.reg_read(UC_ARM64_REG_SP)
    print(f"  SP = 0x{sp:x}")
