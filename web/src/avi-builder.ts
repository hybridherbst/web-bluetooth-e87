/**
 * MJPG AVI builder for E87/L8 LED badge.
 *
 * Builds a RIFF/AVI container with MJPG-compressed video frames
 * (and optional PCM audio). The structure matches what the official
 * iOS app sends to the device.
 *
 * Layout (video-only, no audio):
 *   RIFF 'AVI '
 *     LIST 'hdrl'
 *       avih          (56 bytes — main AVI header)
 *       LIST 'strl'
 *         strh        (56 bytes — stream header, type=vids, handler=MJPG)
 *         strf        (40 bytes — BITMAPINFOHEADER)
 *         JUNK        (4120 bytes — OpenDML super-index placeholder)
 *       vprp          (68 bytes — video properties)
 *       JUNK          (260 bytes — padding)
 *     LIST 'INFO'
 *       ISFT          (software tag)
 *     JUNK            (padding to align movi to ~5742)
 *     LIST 'movi'
 *       00dc frame0
 *       00dc frame1
 *       ...
 *     idx1            (16 bytes per frame — legacy index)
 */

const FOURCC = (s: string) => {
  const a = new Uint8Array(4)
  for (let i = 0; i < 4; i++) a[i] = s.charCodeAt(i) & 0xff
  return a
}

const u32le = (v: number): Uint8Array => {
  const a = new Uint8Array(4)
  a[0] = v & 0xff
  a[1] = (v >> 8) & 0xff
  a[2] = (v >> 16) & 0xff
  a[3] = (v >> 24) & 0xff
  return a
}

const u16le = (v: number): Uint8Array => {
  const a = new Uint8Array(2)
  a[0] = v & 0xff
  a[1] = (v >> 8) & 0xff
  return a
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((s, p) => s + p.length, 0)
  const out = new Uint8Array(total)
  let off = 0
  for (const p of parts) {
    out.set(p, off)
    off += p.length
  }
  return out
}

/** Pad to even length (RIFF requires word-aligned chunks) */
function padEven(data: Uint8Array): Uint8Array {
  if (data.length & 1) return concat(data, new Uint8Array(1))
  return data
}

function makeChunk(id: string, data: Uint8Array): Uint8Array {
  return concat(FOURCC(id), u32le(data.length), padEven(data))
}

function makeList(type: string, ...children: Uint8Array[]): Uint8Array {
  const inner = concat(FOURCC(type), ...children)
  return concat(FOURCC('LIST'), u32le(inner.length), inner)
}

export interface AviOptions {
  width?: number
  height?: number
  /** Frames per second (default 1 for image sequences, 12 for video) */
  fps?: number
}

/**
 * Build an AVI file from an array of JPEG frame buffers.
 *
 * @param frames  Array of raw JPEG bytes (each frame is FF D8 ... FF D9)
 * @param options Width/height/fps configuration
 * @returns       Complete AVI file as Uint8Array
 */
export function buildMjpgAvi(
  frames: Uint8Array[],
  options: AviOptions = {}
): Uint8Array {
  const width = options.width ?? 368
  const height = options.height ?? 368
  const fps = options.fps ?? (frames.length <= 6 ? 1 : 12)

  const usecPerFrame = Math.round(1_000_000 / fps)
  const maxFrameSize = frames.reduce((m, f) => Math.max(m, f.length), 0)
  const totalFrames = frames.length

  // ── avih ──
  const avihData = concat(
    u32le(usecPerFrame),          // dwMicroSecPerFrame
    u32le(25000),                 // dwMaxBytesPerSec
    u32le(0),                     // dwPaddingGranularity
    u32le(0x0910),                // dwFlags: HASINDEX | ISINTERLEAVED
    u32le(totalFrames),           // dwTotalFrames
    u32le(0),                     // dwInitialFrames
    u32le(1),                     // dwStreams
    u32le(0x00100000),            // dwSuggestedBufferSize (1MB)
    u32le(width),                 // dwWidth
    u32le(height),                // dwHeight
    new Uint8Array(16),           // dwReserved[4]
  )
  const avih = makeChunk('avih', avihData)

  // ── strh (stream header — video) ──
  const strhData = concat(
    FOURCC('vids'),               // fccType
    FOURCC('MJPG'),               // fccHandler
    u32le(0),                     // dwFlags
    u16le(0),                     // wPriority
    u16le(0),                     // wLanguage
    u32le(0),                     // dwInitialFrames
    u32le(1),                     // dwScale
    u32le(fps),                   // dwRate
    u32le(0),                     // dwStart
    u32le(totalFrames),           // dwLength
    u32le(maxFrameSize),          // dwSuggestedBufferSize
    u32le(0xffffffff),            // dwQuality (-1 = default)
    u32le(0),                     // dwSampleSize
    u16le(0),                     // rcFrame.left
    u16le(0),                     // rcFrame.top
    u16le(width),                 // rcFrame.right
    u16le(height),                // rcFrame.bottom
  )
  const strh = makeChunk('strh', strhData)

  // ── strf (BITMAPINFOHEADER) ──
  const imgSize = width * height * 3
  const strfData = concat(
    u32le(40),                    // biSize
    u32le(width),                 // biWidth
    u32le(height),                // biHeight
    u16le(1),                     // biPlanes
    u16le(24),                    // biBitCount
    FOURCC('MJPG'),               // biCompression
    u32le(imgSize),               // biSizeImage
    u32le(0),                     // biXPelsPerMeter
    u32le(0),                     // biYPelsPerMeter
    u32le(0),                     // biClrUsed
    u32le(0),                     // biClrImportant
  )
  const strf = makeChunk('strf', strfData)

  // ── JUNK (OpenDML super-index placeholder) ──
  // The iOS app writes a 4120-byte JUNK here containing a partial
  // super-index structure. We fill it with the same pattern.
  const junkSuper = new Uint8Array(4120)
  // First 8 bytes: [0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
  // Then '00dc' + zeros
  junkSuper[0] = 0x04
  const dc = FOURCC('00dc')
  junkSuper.set(dc, 8)
  const junkSuperChunk = makeChunk('JUNK', junkSuper)

  // ── strl LIST ──
  const strl = makeList('strl', strh, strf, junkSuperChunk)

  // ── vprp (video properties) ──
  const vprpData = concat(
    u32le(0),                     // VideoFormatToken
    u32le(0),                     // VideoStandard
    u32le(fps),                   // dwVerticalRefreshRate
    u32le(width),                 // dwHTotalInT
    u32le(height),                // dwVTotalInLines
    u32le(1 | (1 << 16)),         // dwFrameAspectRatio (1:1)
    u32le(width),                 // dwFrameWidthInPixels
    u32le(height),                // dwFrameHeightInLines
    u32le(1),                     // nFieldPerFrame
    // Field info (1 entry):
    u32le(width),                 // CompressedBMWidth
    u32le(height),                // CompressedBMHeight
    u32le(width),                 // ValidBMWidth
    u32le(height),                // ValidBMHeight
    u32le(0),                     // ValidBMXOffset
    u32le(0),                     // ValidBMYOffset
    u32le(0),                     // VideoXOffsetInT
    u32le(0),                     // VideoYValidStartLine
  )
  const vprp = makeChunk('vprp', vprpData)

  // ── JUNK padding (260 bytes) ──
  const junkPad = makeChunk('JUNK', new Uint8Array(260))

  // ── hdrl LIST ──
  const hdrl = makeList('hdrl', avih, strl, vprp, junkPad)

  // ── INFO LIST ──
  const isftStr = 'AviBuilder\0'
  const isftBytes = new Uint8Array(isftStr.length)
  for (let i = 0; i < isftStr.length; i++) isftBytes[i] = isftStr.charCodeAt(i)
  const isft = makeChunk('ISFT', isftBytes)
  const info = makeList('INFO', isft)

  // ── JUNK padding to align movi ──
  // The iOS app pads to bring movi to offset ~5742.
  // Calculate how much padding we need.
  const headerSoFar = 12 + hdrl.length + info.length + 8 // RIFF header + hdrl + info + JUNK chunk overhead
  const targetMoviOffset = 5742
  const junkPadSize = Math.max(0, targetMoviOffset - headerSoFar - 8) // -8 for JUNK chunk header
  const junkAlign = makeChunk('JUNK', new Uint8Array(junkPadSize))

  // ── movi LIST ──
  const moviChildren: Uint8Array[] = []
  for (const frame of frames) {
    moviChildren.push(makeChunk('00dc', frame))
  }
  const movi = makeList('movi', ...moviChildren)

  // ── idx1 (legacy index) ──
  const idx1Entries: Uint8Array[] = []
  let moviDataOffset = 4 // offset within movi data (after LIST type FOURCC)
  for (const frame of frames) {
    idx1Entries.push(concat(
      FOURCC('00dc'),
      u32le(0x10),                // AVIIF_KEYFRAME
      u32le(moviDataOffset),      // offset from movi data start
      u32le(frame.length),
    ))
    moviDataOffset += 8 + frame.length + (frame.length & 1) // chunk header + data + padding
  }
  const idx1 = makeChunk('idx1', concat(...idx1Entries))

  // ── RIFF container ──
  const riffContent = concat(FOURCC('AVI '), hdrl, info, junkAlign, movi, idx1)
  return concat(FOURCC('RIFF'), u32le(riffContent.length), riffContent)
}
