/**
 * Image/video → 368×368 JPEG frame conversion for E87/L8 badge.
 *
 * Handles single images (with quality bracketing to hit size targets),
 * multi-image sequences → AVI, and video → AVI with trim/zoom support.
 */

import { buildMjpgAvi } from '../avi-builder'
import { formatBytes } from './utils'

export const E87_IMAGE_WIDTH = 368
export const E87_IMAGE_HEIGHT = 368
export const E87_TARGET_IMAGE_BYTES = 16000
export const MAX_UPLOAD_BYTES = 2_000_000

/**
 * Convert a single image file to 368×368 JPEG, bracketing quality
 * to stay under E87_TARGET_IMAGE_BYTES.
 */
export async function imageFileTo368JpegBytes(file: File): Promise<Uint8Array> {
  const bitmap = await createImageBitmap(file)
  const srcRatio = bitmap.width / bitmap.height
  const targetRatio = E87_IMAGE_WIDTH / E87_IMAGE_HEIGHT
  let sx = 0, sy = 0, sw = bitmap.width, sh = bitmap.height
  if (srcRatio > targetRatio) {
    sw = Math.round(bitmap.height * targetRatio)
    sx = Math.floor((bitmap.width - sw) / 2)
  } else {
    sh = Math.round(bitmap.width / targetRatio)
    sy = Math.floor((bitmap.height - sh) / 2)
  }

  async function toJpegBlob(quality: number): Promise<Blob | null> {
    if ('OffscreenCanvas' in window) {
      const canvas = new OffscreenCanvas(E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('Could not create 2D canvas context.')
      ctx.fillStyle = 'black'
      ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
      ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
      return canvas.convertToBlob({ type: 'image/jpeg', quality })
    }
    const canvas = document.createElement('canvas')
    canvas.width = E87_IMAGE_WIDTH
    canvas.height = E87_IMAGE_HEIGHT
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Could not create fallback 2D canvas context.')
    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    return new Promise<Blob | null>((resolve) => {
      canvas.toBlob((result) => resolve(result), 'image/jpeg', quality)
    })
  }

  const qualitySteps = [0.88, 0.8, 0.72, 0.64, 0.56, 0.48, 0.4, 0.34]
  let blob: Blob | null = null
  for (const q of qualitySteps) {
    const candidate = await toJpegBlob(q)
    if (!candidate) continue
    blob = candidate
    if (candidate.size <= E87_TARGET_IMAGE_BYTES) break
  }
  bitmap.close()
  if (!blob) throw new Error('Image conversion failed (no JPEG blob).')
  return new Uint8Array(await blob.arrayBuffer())
}

/**
 * Convert a single image file to a 368×368 JPEG frame at fixed quality.
 * Used for multi-frame AVI building.
 */
export async function imageFileTo368JpegFrame(file: File, quality = 0.88): Promise<Uint8Array> {
  const bitmap = await createImageBitmap(file)
  const srcRatio = bitmap.width / bitmap.height
  const targetRatio = E87_IMAGE_WIDTH / E87_IMAGE_HEIGHT
  let sx = 0, sy = 0, sw = bitmap.width, sh = bitmap.height
  if (srcRatio > targetRatio) {
    sw = Math.round(bitmap.height * targetRatio)
    sx = Math.floor((bitmap.width - sw) / 2)
  } else {
    sh = Math.round(bitmap.width / targetRatio)
    sy = Math.floor((bitmap.height - sh) / 2)
  }
  const canvas = new OffscreenCanvas(E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'black'
  ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
  ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
  bitmap.close()
  const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality })
  return new Uint8Array(await blob.arrayBuffer())
}

/**
 * Convert multiple image files to an AVI sequence.
 */
export async function imagesToAvi(
  files: File[],
  fps: number,
  log?: (msg: string) => void,
): Promise<Uint8Array> {
  log?.(`Converting ${files.length} images to AVI sequence at ${fps} fps...`)
  const frames: Uint8Array[] = []
  for (let i = 0; i < files.length; i++) {
    log?.(`  Processing image ${i + 1}/${files.length}: ${files[i].name}`)
    frames.push(await imageFileTo368JpegFrame(files[i], 0.88))
  }
  const avi = buildMjpgAvi(frames, { fps })
  log?.(`AVI built: ${frames.length} frames, ${formatBytes(avi.length)}`)
  return avi
}

export interface VideoToAviOptions {
  fps: number
  trimStart: number
  trimEnd: number
  zoom: number
  zoomCx: number
  zoomCy: number
}

/**
 * Extract frames from a video file and build an AVI.
 * Supports trim (start/end), zoom, and pan.
 */
export async function videoToAvi(
  file: File,
  opts: VideoToAviOptions,
  log?: (msg: string) => void,
): Promise<Uint8Array> {
  const { fps, trimStart, trimEnd, zoom, zoomCx, zoomCy } = opts
  log?.(`Extracting frames from video at ${fps} fps (trim ${trimStart.toFixed(1)}s–${trimEnd.toFixed(1)}s, zoom ${zoom.toFixed(1)}x)...`)
  const url = URL.createObjectURL(file)
  const video = document.createElement('video')
  video.muted = true
  video.playsInline = true
  video.preload = 'auto'

  await new Promise<void>((resolve, reject) => {
    video.onloadedmetadata = () => resolve()
    video.onerror = () => reject(new Error('Failed to load video'))
    video.src = url
  })

  video.currentTime = trimStart
  await new Promise<void>((r) => { video.onseeked = () => r() })

  const duration = trimEnd - trimStart
  const frameInterval = 1 / fps
  const canvas = new OffscreenCanvas(E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
  const ctx = canvas.getContext('2d')!
  const frames: Uint8Array[] = []

  const srcFullW = video.videoWidth
  const srcFullH = video.videoHeight
  const minDim = Math.min(srcFullW, srcFullH)
  const cropX = (srcFullW - minDim) / 2
  const cropY = (srcFullH - minDim) / 2
  const zoomedSize = minDim / zoom
  const sx = Math.max(0, Math.min(cropX + zoomCx * minDim - zoomedSize / 2, srcFullW - zoomedSize))
  const sy = Math.max(0, Math.min(cropY + zoomCy * minDim - zoomedSize / 2, srcFullH - zoomedSize))

  const expectedFrames = Math.ceil(duration * fps)
  log?.(`Video: ${srcFullW}x${srcFullH}, clip ${duration.toFixed(2)}s, extracting ~${expectedFrames} frames`)

  const estFrameSize = 8000
  const maxFrames = Math.floor((MAX_UPLOAD_BYTES - 6000) / (estFrameSize + 16))
  if (expectedFrames > maxFrames) {
    log?.(`⚠️ ${expectedFrames} frames would exceed ~${formatBytes(MAX_UPLOAD_BYTES)} limit. Capping at ${maxFrames} frames.`)
  }

  for (let t = trimStart; t < trimEnd && frames.length < maxFrames; t += frameInterval) {
    video.currentTime = t
    await new Promise<void>((r) => { video.onseeked = () => r() })

    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    ctx.drawImage(video, sx, sy, zoomedSize, zoomedSize, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)

    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.88 })
    frames.push(new Uint8Array(await blob.arrayBuffer()))

    if (frames.length % 10 === 0) log?.(`  Extracted ${frames.length} frames...`)
  }

  URL.revokeObjectURL(url)

  if (frames.length === 0) throw new Error('No frames extracted from video.')

  const avi = buildMjpgAvi(frames, { fps })
  log?.(`AVI built: ${frames.length} frames @ ${fps}fps, ${formatBytes(avi.length)}`)

  if (avi.length > MAX_UPLOAD_BYTES) {
    log?.(`⚠️ AVI is ${formatBytes(avi.length)}, exceeds ${formatBytes(MAX_UPLOAD_BYTES)} limit. Try shorter clip, lower fps, or more zoom.`)
  }
  return avi
}
