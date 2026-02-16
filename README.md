# E87 / L8 LED Badge — BLE Image Upload Protocol

Reverse-engineered protocol for uploading JPEG images to **Jieli-based** LED badge
devices (sold as "E87", "L8", "LED Smart Badge", etc.) over **Bluetooth Low Energy**.

> **Source captures:** `cap.pklg` (Apple PacketLogger) / `cap.btsnoop` — captured from
> the official Android companion app communicating with an E87 badge.

---

## Table of Contents

1. [BLE Service & Characteristic Map](#ble-service--characteristic-map)
2. [FE-Framed Protocol](#fe-framed-protocol)
3. [Authentication Handshake (Jieli RCSP Crypto)](#authentication-handshake-jieli-rcsp-crypto)
4. [Upload Flow — Phase by Phase](#upload-flow--phase-by-phase)
5. [Data Transfer Details](#data-transfer-details)
6. [Completion Handshake](#completion-handshake)
7. [CRC-16 XMODEM](#crc-16-xmodem)
8. [Constants & Magic Numbers](#constants--magic-numbers)
9. [Capture File Format (Apple PacketLogger `.pklg`)](#capture-file-format-apple-packetlogger-pklg)
10. [Diagrams](#diagrams)

---

## BLE Service & Characteristic Map

| Service UUID | Characteristic UUID | Direction | Usage |
|---|---|---|---|
| `0000AE00-…` | `AE01` (Write Without Response) | Phone → Device | Auth bytes + FE-framed commands + data |
| `0000AE00-…` | `AE02` (Notify) | Device → Phone | Auth responses + FE-framed acks/notifications |
| `C2E6FD00-…` | `FD01` (Notify) | Device → Phone | 9E-prefixed control notifications |
| `C2E6FD00-…` | `FD02` (Write / WnR) | Phone → Device | 9E-prefixed control writes (time, heartbeat, settings) |
| `C2E6FD00-…` | `FD03` (Notify) | Device → Phone | 9E-prefixed ready signals |
| `C2E6FD00-…` | `FD04` (Write Without Response) | Phone → Device | 9E-prefixed control writes |
| `C2E6FD00-…` | `FD05` (Notify) | Device → Phone | 9E-prefixed notifications |

**Primary data path:** `AE01` (write) / `AE02` (notify).
**Control sideband:** `FD02` (write) / `FD01`, `FD03`, `FD05` (notify).

---

## FE-Framed Protocol

All commands and data on the AE01/AE02 channel use the **FE-framed** format:

```
┌──────────┬──────┬─────┬────────────┬──────────────┬────────────┐
│ FE DC BA │ flag │ cmd │ len (BE16) │ body[0..len) │     EF     │
│ 3 bytes  │  1B  │ 1B  │  2 bytes   │  variable    │   1 byte   │
└──────────┴──────┴─────┴────────────┴──────────────┴────────────┘
```

| Field | Size | Description |
|---|---|---|
| Header | 3 | Always `FE DC BA` |
| Flag | 1 | `0xC0` = command/request, `0x00` = response/ack, `0x80` = data/notification |
| Cmd | 1 | Command ID (see table below) |
| Length | 2 | Body length, **big-endian** |
| Body | variable | Command-specific payload |
| Terminator | 1 | Always `0xEF` |

### Command Table

| Cmd | Flag | Direction | Purpose |
|---|---|---|---|
| `0x06` | `0xC0` | Phone → Device | Reset auth flag |
| `0x03` | `0xC0` / `0x00` | Both | Device info query / response |
| `0x07` | `0xC0` / `0x00` | Both | Device config query / response |
| `0x21` | `0xC0` / `0x00` | Both | Begin upload session |
| `0x27` | `0xC0` / `0x00` | Both | Transfer parameters |
| `0x1B` | `0xC0` / `0x00` | Both | File metadata (size, name, token) |
| `0x1D` | `0x80` | Device → Phone | Window acknowledgment |
| `0x01` | `0x80` | Phone → Device | Data frame |
| `0x20` | `0xC0` / `0x00` | Both | Upload complete notification |
| `0x1C` | `0xC0` / `0x00` | Both | Upload finalize |

---

## Authentication Handshake (Jieli RCSP Crypto)

Before any FE-framed commands, a **bidirectional crypto handshake** is performed
on AE01/AE02 using raw (non-FE-framed) bytes.

The crypto is a **custom Jieli block cipher** reverse-engineered from
`libjl_auth.so` (ARM64). It uses a 256-byte SBOX, 256-byte inverse SBOX,
and a 256-byte key-schedule table, with a static 16-byte key.

### Auth Sequence

```
Phone                                        Device
  │                                            │
  │─── [0x00, random*16] ──────────────────────▶│  Step 1: Send random
  │                                            │
  │◀── [0x01, encrypted*16] ───────────────────│  Step 2: Device response
  │                                            │
  │─── [0x02, 'p','a','s','s'] ────────────────▶│  Step 3: Acknowledge
  │                                            │
  │◀── [0x00, challenge*16] ───────────────────│  Step 4: Device challenge
  │                                            │
  │─── [0x01, encrypted*16] ──────────────────▶│  Step 5: Encrypted response
  │                                            │
  │◀── [0x02, 'p','a','s','s'] ────────────────│  Step 6: AUTH SUCCESS
  │                                            │
```

- Step 1: Phone generates 16 random bytes, sends `[0x00, rand[0..15]]` (17 bytes)
- Step 2: Device encrypts with its key and responds `[0x01, enc[0..15]]`
- Step 3: Phone acknowledges with ASCII `[0x02, 0x70, 0x61, 0x73, 0x73]` = `"pass"`
- Step 4: Device sends its own challenge `[0x00, challenge[0..15]]`
- Step 5: Phone encrypts challenge with `getEncryptedAuthData()` and sends `[0x01, enc[0..15]]`
- Step 6: Device confirms with `[0x02, 0x70, 0x61, 0x73, 0x73]` = `"pass"`

### Crypto Details

- **Static Key:** `6BE9B2C083D94A1E5AF89C4E7B6D3F20` (16 bytes)
- **Magic:** `B3A1D7E94C2F8560` (8 bytes, used in key scheduling)
- **Algorithm:** Custom Jieli block cipher (NOT AES) — 16 rounds on 16-byte blocks
- **Implementation:** See `web/src/jl-auth.ts`

---

## Upload Flow — Phase by Phase

```
┌─────────────────────────────────────────────────────────────────┐
│                    COMPLETE UPLOAD TIMELINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  AUTH    ───▶  Crypto handshake (6 messages on AE01/AE02)       │
│                                                                 │
│  PHASE 1 ──▶  cmd 0x06 — reset auth flag                       │
│  PHASE 2 ──▶  FD02 control writes (time, settings, heartbeat)  │
│  PHASE 3 ──▶  cmd 0x03 — device info query (best-effort)       │
│  PHASE 4 ──▶  cmd 0x07 — device config query (best-effort)     │
│  PHASE 5 ──▶  FD02 bootstrap (heartbeat, C7 query, ready)      │
│  PHASE 6 ──▶  cmd 0x21 — begin upload session                  │
│  PHASE 7 ──▶  cmd 0x27 — transfer parameters                   │
│  PHASE 8 ──▶  cmd 0x1B — file metadata                         │
│               ◀── initial window ack (cmd 0x1D)                 │
│  PHASE 9 ──▶  DATA TRANSFER (windowed cmd 0x01 frames)         │
│  PHASE 10 ─▶  Completion handshake (cmd 0x20 + cmd 0x1C)       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 1: cmd 0x06 — Reset Auth Flag

```
TX: FE DC BA C0 06 00 03 02 00 01 EF
     flag=0xC0  cmd=0x06  len=3  body=[0x02, 0x00, 0x01]
```

- The APK reference shows `FEDCBAC00600020001EF`
- The Android capture shows body=`[0x00, 0x01]` (2 bytes), but the 3-byte format
  `[0x02, 0x00, 0x01]` has been proven working with E87 devices
- After sending, set `seqCounter = 0x01`
- Ack may or may not arrive (continue regardless)

### Phase 2: FD02 Control Writes

Send 9E-prefixed control messages on the FD02 characteristic:

| Message | Purpose |
|---|---|
| `9E 45 08 02 07 00 YY YY MM DD 00 HH mm` | Set device time |
| `9E 20 08 16 01 00 01` | Settings |
| `9E B5 0B 29 01 00 80` | Heartbeat |

### Phase 3: cmd 0x03 — Device Info (best-effort)

```
TX: FE DC BA C0 03 00 06 [seq] FF FF FF FF 01 EF
RX: FE DC BA 00 03 00 7D 00 [seq] ... EF          (125-byte response)
```

- `body[0]` = seqCounter (0x01), then increment
- Response contains device info (firmware version, capabilities, etc.)
- May not be acked — continue regardless

### Phase 4: cmd 0x07 — Device Config (best-effort)

```
TX: FE DC BA C0 07 00 06 [seq] FF FF FF FF FF EF
RX: FE DC BA 00 07 00 38 00 [seq] ... EF           (56-byte response)
```

- `body[0]` = seqCounter (0x02), then increment
- May not be acked — continue regardless

### Phase 5: FD02 Bootstrap

Send additional control messages to prepare for upload:

1. `9E B5 0B 29 01 00 80` — heartbeat
2. Wait ~400ms
3. `9E D3 0B C6 01 00 01` — request device info
4. Wait for `9E xx xx C7 ...` notification on FD01 (best-effort)
5. `9E F4 0B DC 01 00 0C` — prepare
6. Wait for `9E E6 ...` ready signal on FD03

### Phase 6: cmd 0x21 — Begin Upload

```
TX: FE DC BA C0 21 00 02 [seq] 00 EF
RX: FE DC BA 00 21 00 02 00 [seq] EF
```

- `body` = `[seqCounter, 0x00]` (seqCounter=0x03)
- Response body = `[0x00, seqCounter]` (status OK + echoed seq)

### Phase 7: cmd 0x27 — Transfer Parameters

```
TX: FE DC BA C0 27 00 07 [seq] 00 00 00 00 02 01 EF
RX: FE DC BA 00 27 00 04 00 [seq] 00 01 EF
```

- `body` = `[seqCounter, 0x00, 0x00, 0x00, 0x00, 0x02, 0x01]` (seqCounter=0x04)
- Response body = `[0x00, seqCounter, 0x00, 0x01]`

### Phase 8: cmd 0x1B — File Metadata

```
TX: FE DC BA C0 1B 00 14 [seq] 00 00 [size_BE16] [token*4] [name...] 00 EF
RX: FE DC BA 00 1B 00 04 00 [seq] 01 EA EF
```

Body structure:

| Offset | Size | Value | Description |
|---|---|---|---|
| 0 | 1 | seqCounter | Sequence (0x05) |
| 1 | 1 | `0x00` | Reserved |
| 2 | 1 | `0x00` | Reserved |
| 3 | 2 | `size >> 8, size & 0xFF` | File size, **big-endian 16-bit** |
| 5 | 4 | random | Token (4 random bytes) |
| 9 | N | ASCII | Temp filename (e.g., `b938e1.tmp`) |
| 9+N | 1 | `0x00` | Null terminator |

- Response body `[0x00, seq, 0x01, 0xEA]` — `0x01EA` = 490 (chunk data size hint)

### Initial Window Ack

After metadata ack, the device sends a **window ack** (cmd 0x1D):

```
RX: FE DC BA 80 1D 00 08 [wa_seq] 00 [win_BE16] 00 00 [off_BE16] EF
```

First window ack body: `01 00 0F 50 00 00 01 EA`
- `wa_seq` = 0x01 (window ack sequence counter, separate from data seq)
- `0x0F50` = 3920 = window size in bytes = 8 × 490
- `0x01EA` = 490 = cumulative file offset after first window

---

## Data Transfer Details

### Data Frame Format

Each data frame uses cmd `0x01` with flag `0x80`:

```
FE DC BA 80 01 [len_BE16] [body...] EF
```

Body structure (495 bytes for a full frame):

```
┌──────┬──────┬──────┬─────────────┬──────────────────────────┐
│ seq  │ 0x1D │ slot │ CRC16 (BE)  │  file data (490 bytes)   │
│  1B  │  1B  │  1B  │   2 bytes   │       490 bytes          │
└──────┴──────┴──────┴─────────────┴──────────────────────────┘
```

| Field | Size | Description |
|---|---|---|
| seq | 1 | Global sequence counter (starts at 0x06, increments per frame) |
| subcmd | 1 | Always `0x1D` |
| slot | 1 | Window slot (0–7, cycles within each window) |
| CRC-16 | 2 | CRC-16/XMODEM of the 490-byte file data, **big-endian** |
| file data | 490 | Raw JPEG bytes |

### Full Frame on the Wire

The full FE frame for a data chunk is **503 bytes**:
```
FE DC BA (3) + flag (1) + cmd (1) + length (2) + body (495) + EF (1) = 503
```

This gets fragmented by BLE into multiple ACL packets (~244 + 251 + 8 bytes).

### Window Flow Control

- **Window size:** 8 frames
- After every 8 data frames (slot cycles 0→7), wait for a **window ack** (`0x80 0x1D`)
- Also wait for window ack after the last frame if fewer than 8 remain

```
Phone                                     Device
  │                                         │
  │◀── Window Ack (wa_seq=1, win=3920) ────│  Initial
  │                                         │
  │─── Data seq=0x06 slot=0 ──────────────▶│
  │─── Data seq=0x07 slot=1 ──────────────▶│
  │─── Data seq=0x08 slot=2 ──────────────▶│
  │─── Data seq=0x09 slot=3 ──────────────▶│
  │─── Data seq=0x0A slot=4 ──────────────▶│
  │─── Data seq=0x0B slot=5 ──────────────▶│
  │─── Data seq=0x0C slot=6 ──────────────▶│
  │─── Data seq=0x0D slot=7 ──────────────▶│
  │                                         │
  │◀── Window Ack (wa_seq=2, win=3920) ────│
  │                                         │
  │─── Data seq=0x0E slot=0 ──────────────▶│
  │─── ... 8 more frames ...               │
  │                                         │
  │◀── Window Ack (wa_seq=N, win=remaining)│  Final
  │                                         │
  │─── Last frame(s) ────────────────────▶│
  │                                         │
```

### Window Ack Body Format

```
[wa_seq(1)] [0x00(1)] [window_size_BE16(2)] [0x00 0x00(2)] [cumulative_offset_BE16(2)]
```

| WA# | Body (hex) | Window Size | Cumulative Offset |
|---|---|---|---|
| 1 | `01 00 0F 50 00 00 01 EA` | 3920 (8×490) | 490 |
| 2 | `02 00 0F 50 00 00 11 3A` | 3920 | 4410 |
| 3 | `03 00 0F 50 00 00 20 8A` | 3920 | 8330 |
| 4 | `04 00 0F 50 00 00 2F DA` | 3920 | 12250 |
| 5 (final) | `05 00 01 EA 00 00 00 00` | 490 | 0 |

Each consecutive offset increases by 3920 (= 8 × 490 bytes per window).

---

## Completion Handshake

After all data frames and the final window ack:

```
Phone                                          Device
  │                                              │
  │◀── cmd 0x20 flag=0xC0 body=[seq] ───────────│  Device signals done
  │                                              │
  │─── cmd 0x20 flag=0x00                        │  Phone responds with
  │    body=[0x00, seq, UTF16LE_path, 0x0000] ──▶│  filepath
  │                                              │
  │◀── cmd 0x1C flag=0xC0 body=[seq, 0x00] ─────│  Device requests finalize
  │                                              │
  │─── cmd 0x1C flag=0x00 body=[0x00, seq] ─────▶│  Phone confirms
  │                                              │
```

### cmd 0x20 Response Details

The phone's response to cmd 0x20 contains a **UTF-16LE encoded device path**:

```
body = [0x00, echoed_seq, path_utf16le..., 0x00, 0x00]
```

Captured path: `\U32\020260215004530.jpg` (UTF-16LE + null terminator = 40 bytes)

### cmd 0x1C Response Details

```
body = [0x00, echoed_seq]
```

---

## CRC-16 XMODEM

Each data frame body includes a 2-byte CRC-16 at `body[3:5]` (big-endian)
computed over the 490-byte file data payload.

**Parameters:**
- Polynomial: `0x1021`
- Initial value: `0x0000`
- No final XOR
- No reflection

```typescript
function crc16xmodem(data: Uint8Array): number {
  let crc = 0x0000
  for (let i = 0; i < data.length; i++) {
    crc ^= data[i] << 8
    for (let j = 0; j < 8; j++) {
      if (crc & 0x8000) {
        crc = ((crc << 1) ^ 0x1021) & 0xffff
      } else {
        crc = (crc << 1) & 0xffff
      }
    }
  }
  return crc
}
```

**Verified:** First data frame CRC = `0xC0B8` matches XMODEM of its 490-byte payload ✓

---

## Constants & Magic Numbers

| Constant | Value | Notes |
|---|---|---|
| `E87_DATA_CHUNK_SIZE` | 490 | File data bytes per frame |
| Frame body overhead | 5 | seq(1) + 0x1D(1) + slot(1) + CRC16(2) |
| Full frame body | 495 | 5 + 490 |
| FE frame total | 503 | 7 header + 495 body + 1 EF |
| Window size | 8 | Frames per window |
| Window bytes | 3920 | 8 × 490 |
| Image dimensions | 368 × 368 | Target JPEG size |
| Target image bytes | ~16000 | JPEG quality adjusted to fit |
| File size encoding | BE16 | In metadata (cmd 0x1B body[3:5]) |
| Seq counter start | 0x00 | But cmd 0x06 uses hardcoded body |
| Data seq start | 0x06 | After 6 setup commands |

---

## Capture File Format (Apple PacketLogger `.pklg`)

The `.pklg` file uses **little-endian** fields:

```
┌───────────────┬───────────────┬──────┬───────────────────┐
│ rec_len (LE32)│ timestamp(LE64)│ type │ payload[rec_len-9]│
│   4 bytes     │   8 bytes     │ 1B   │    variable       │
└───────────────┴───────────────┴──────┴───────────────────┘
```

| Type | Meaning |
|---|---|
| `0x00` | HCI Command (Host → Controller) |
| `0x01` | HCI Event (Controller → Host) |
| `0x02` | ACL Data Packet (outgoing / TX) |
| `0x03` | ACL Data Packet (incoming / RX) |
| `0xFC`/`0xFD` | Vendor-specific |

**Capture stats:** 1857 records, 84999 bytes total. Contains complete upload of a
~15647 byte JPEG in 32 data frames across 5 windows.

---

## Diagrams

### Full Protocol Sequence (from capture)

```
rec#  dir   message
───── ───── ─────────────────────────────────────────
       AUTH  [0x00, rand*16]              →
             [0x01, encrypted*16]         ←
             [0x02, "pass"]              →
             [0x00, challenge*16]         ←
             [0x01, encrypted*16]         →
             [0x02, "pass"]              ←
───── ───── ─────────────────────────────────────────
1455  TX    cmd 0x06 flag=C0 body: 02 00 01
      TX    FD02: 9EBD 0B60 0D00 03
───── ───── ─────────────────────────────────────────
      TX    FD02: 9E45 (time) / 9E20 / 9EB5 (heartbeat)
───── ───── ─────────────────────────────────────────
1478  TX    cmd 0x03 flag=C0 body: 01 FF FF FF FF 01
1483  RX    cmd 0x03 flag=00 body: 00 01 ... (125 B)
───── ───── ─────────────────────────────────────────
1488  TX    cmd 0x07 flag=C0 body: 02 FF FF FF FF FF
1492  RX    cmd 0x07 flag=00 body: 00 02 ... (56 B)
───── ───── ─────────────────────────────────────────
      TX    FD02: 9EB5 / 9ED3 / 9EF4
      RX    FD01: 9E..C7 (device info)
      RX    FD03: 9EE6 (ready)
───── ───── ─────────────────────────────────────────
1600  TX    cmd 0x21 flag=C0 body: 03 00
1606  RX    cmd 0x21 flag=00 body: 00 03
───── ───── ─────────────────────────────────────────
1607  TX    cmd 0x27 flag=C0 body: 04 00 00 00 00 02 01
1609  RX    cmd 0x27 flag=00 body: 00 04 00 01
───── ───── ─────────────────────────────────────────
1610  TX    cmd 0x1B flag=C0 body: 05 00 00 3D 1F 66 AB 66 66 ...
1612  RX    cmd 0x1B flag=00 body: 00 05 01 EA
───── ───── ─────────────────────────────────────────
1613  RX    cmd 0x1D flag=80 body: 01 00 0F 50 00 00 01 EA  (WA#1)
1614  TX    DATA seq=06 slot=0 len=495
 ...  TX    DATA seq=07..0D slot=1..7 (8 frames)
1655  RX    cmd 0x1D flag=80 body: 02 00 0F 50 00 00 11 3A  (WA#2)
 ...  TX    DATA seq=0E..15 slot=0..7 (8 frames)
1693  RX    cmd 0x1D flag=80 body: 03 00 0F 50 00 00 20 8A  (WA#3)
 ...  TX    DATA seq=16..1D slot=0..7 (8 frames)
1730  RX    cmd 0x1D flag=80 body: 04 00 0F 50 00 00 2F DA  (WA#4)
 ...  TX    DATA seq=1E..24 slot=0..6 (7 frames, last is short)
1760  RX    cmd 0x1D flag=80 body: 05 00 01 EA 00 00 00 00  (WA#5)
1761  TX    DATA seq=25 slot=0 len=495 (last frame)
───── ───── ─────────────────────────────────────────
1767  RX    cmd 0x20 flag=C0 body: 06
1768  TX    cmd 0x20 flag=00 body: 00 06 [UTF16LE path] 00 00
1770  RX    cmd 0x1C flag=C0 body: 07 00
1771  TX    cmd 0x1C flag=00 body: 00 07
───── ───── ─────────────────────────────────────────
                    UPLOAD COMPLETE
```

### Sequence Counter Progression

```
cmd 0x06  → seq = 0x00  (body uses hardcoded [0x02, 0x00, 0x01])
cmd 0x03  → seq = 0x01
cmd 0x07  → seq = 0x02
cmd 0x21  → seq = 0x03
cmd 0x27  → seq = 0x04
cmd 0x1B  → seq = 0x05
DATA[0]   → seq = 0x06
DATA[1]   → seq = 0x07
  ...
DATA[31]  → seq = 0x25
cmd 0x20  → device uses seq 0x06 (next_seq after data)
cmd 0x1C  → device uses seq 0x07
```

---

## File Structure

```
bluetooth-tag/
├── README.md                 ← This file
├── cap.pklg                  ← Apple PacketLogger capture
├── cap.btsnoop               ← Btsnoop capture
└── web/
    └── src/
        ├── App.svelte        ← Main BLE uploader app (Svelte + TS)
        └── jl-auth.ts        ← Jieli RCSP crypto module
```
