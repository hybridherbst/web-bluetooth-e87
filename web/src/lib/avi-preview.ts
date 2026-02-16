/**
 * AVI container parsing for preview playback.
 *
 * Extracts MJPG frames from a RIFF/AVI container as ImageBitmaps,
 * and reads the FPS from the avih header.
 */

/** Parse an AVI container and return its MJPG frames as ImageBitmaps. */
export async function parseAviFrames(avi: Uint8Array): Promise<ImageBitmap[]> {
  const bitmaps: ImageBitmap[] = []
  const moviStr = [0x6d, 0x6f, 0x76, 0x69] // "movi"
  let moviIdx = -1
  for (let i = 0; i < avi.length - 4; i++) {
    if (avi[i] === moviStr[0] && avi[i + 1] === moviStr[1] && avi[i + 2] === moviStr[2] && avi[i + 3] === moviStr[3]) {
      moviIdx = i + 4
      break
    }
  }
  if (moviIdx < 0) throw new Error('No movi chunk found in AVI')

  let pos = moviIdx
  const dc = [0x30, 0x30, 0x64, 0x63] // "00dc"
  while (pos < avi.length - 8) {
    if (avi[pos] === dc[0] && avi[pos + 1] === dc[1] && avi[pos + 2] === dc[2] && avi[pos + 3] === dc[3]) {
      const size = avi[pos + 4] | (avi[pos + 5] << 8) | (avi[pos + 6] << 16) | (avi[pos + 7] << 24)
      const frameData = avi.slice(pos + 8, pos + 8 + size)
      try {
        const blob = new Blob([frameData], { type: 'image/jpeg' })
        const bmp = await createImageBitmap(blob)
        bitmaps.push(bmp)
      } catch {
        /* skip corrupt frame */
      }
      pos += 8 + size + (size & 1)
    } else {
      if (pos + 7 < avi.length) {
        const size = avi[pos + 4] | (avi[pos + 5] << 8) | (avi[pos + 6] << 16) | (avi[pos + 7] << 24)
        pos += 8 + size + (size & 1)
      } else {
        break
      }
    }
  }
  return bitmaps
}

/** Read the FPS from an AVI container's avih header. Falls back to 12. */
export function readAviFps(avi: Uint8Array): number {
  const avihStr = [0x61, 0x76, 0x69, 0x68] // "avih"
  for (let i = 0; i < avi.length - 12; i++) {
    if (avi[i] === avihStr[0] && avi[i + 1] === avihStr[1] && avi[i + 2] === avihStr[2] && avi[i + 3] === avihStr[3]) {
      const dataStart = i + 8
      const usec = avi[dataStart] | (avi[dataStart + 1] << 8) | (avi[dataStart + 2] << 16) | (avi[dataStart + 3] << 24)
      if (usec > 0) return Math.round(1_000_000 / usec)
      break
    }
  }
  return 12
}
