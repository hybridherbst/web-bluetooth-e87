/**
 * Image/video → JPEG frame conversion for E87/L8 badge.
 *
 * All canvas draw operations disable smoothing so pixel art / hard-edged
 * content is resampled with nearest-neighbor instead of bilinear.
 */

import { buildMjpgAvi } from '../avi-builder'
import { formatBytes } from './utils'

export const E87_IMAGE_WIDTH = 368
export const E87_IMAGE_HEIGHT = 368
export const E87_TARGET_IMAGE_BYTES = 16000
export const MAX_UPLOAD_BYTES = 2_000_000
export const LIVE_PREVIEW_SIZE = 512

type Ctx2D = OffscreenCanvasRenderingContext2D | CanvasRenderingContext2D

function disableSmoothing(ctx: Ctx2D): void {
  ctx.imageSmoothingEnabled = false
}

export interface TransformSettings {
  scale: number
  panX: number
  panY: number
  backdropColor?: string
}

export interface OutputFrameSize {
  width: number
  height: number
}

const DEFAULT_TRANSFORM: TransformSettings = {
  scale: 1,
  panX: 0,
  panY: 0,
}

function cropToSquare(bitmap: ImageBitmap): { sx: number, sy: number, sw: number, sh: number } {
  const srcRatio = bitmap.width / bitmap.height
  const targetRatio = 1
  let sx = 0
  let sy = 0
  let sw = bitmap.width
  let sh = bitmap.height
  if (srcRatio > targetRatio) {
    sw = Math.round(bitmap.height * targetRatio)
    sx = Math.floor((bitmap.width - sw) / 2)
  } else {
    sh = Math.round(bitmap.width / targetRatio)
    sy = Math.floor((bitmap.height - sh) / 2)
  }
  return { sx, sy, sw, sh }
}

function renderTransformedFrame(
  ctx: OffscreenCanvasRenderingContext2D,
  source: CanvasImageSource,
  width: number,
  height: number,
  transform: TransformSettings,
): void {
  const { scale, panX, panY } = transform
  const drawW = width * scale
  const drawH = height * scale
  const dx = (width - drawW) / 2 + panX * (width / 2)
  const dy = (height - drawH) / 2 + panY * (height / 2)

  disableSmoothing(ctx)
  ctx.fillStyle = transform.backdropColor ?? 'black'
  ctx.fillRect(0, 0, width, height)
  ctx.drawImage(source, dx, dy, drawW, drawH)
}

async function squareBitmapToJpeg(
  bitmap: ImageBitmap,
  transform: TransformSettings,
  quality = 0.95,
  outputSize: OutputFrameSize = { width: E87_IMAGE_WIDTH, height: E87_IMAGE_HEIGHT },
): Promise<Uint8Array> {
  const width = Math.max(1, Math.round(outputSize.width))
  const height = Math.max(1, Math.round(outputSize.height))
  const canvas = new OffscreenCanvas(width, height)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not create 2D canvas context.')

  renderTransformedFrame(ctx, bitmap, width, height, transform)
  const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality })
  return new Uint8Array(await blob.arrayBuffer())
}

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
      disableSmoothing(ctx)
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
    disableSmoothing(ctx)
    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, E87_IMAGE_WIDTH, E87_IMAGE_HEIGHT)
    return new Promise<Blob | null>((resolve) => {
      canvas.toBlob((result) => resolve(result), 'image/jpeg', quality)
    })
  }

  const qualitySteps = [0.98, 0.95, 0.88, 0.8, 0.72, 0.64, 0.56, 0.48, 0.4, 0.34]
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

export async function imageFileToPreviewBitmap(file: File, size = LIVE_PREVIEW_SIZE): Promise<ImageBitmap> {
  const bitmap = await createImageBitmap(file)
  const { sx, sy, sw, sh } = cropToSquare(bitmap)
  const canvas = new OffscreenCanvas(size, size)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not create 2D canvas context.')
  disableSmoothing(ctx)
  ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, size, size)
  bitmap.close()
  return createImageBitmap(canvas)
}

async function bitmapToPreviewBitmap(source: ImageBitmap, size = LIVE_PREVIEW_SIZE): Promise<ImageBitmap> {
  const { sx, sy, sw, sh } = cropToSquare(source)
  const canvas = new OffscreenCanvas(size, size)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not create 2D canvas context.')
  disableSmoothing(ctx)
  ctx.drawImage(source, sx, sy, sw, sh, 0, 0, size, size)
  return createImageBitmap(canvas)
}

/**
 * Decode all frames from an animated image (GIF, animated WebP, etc.) using
 * the browser-native WebCodecs `ImageDecoder` API. Returns each frame as an
 * ImageBitmap plus its intrinsic display duration in microseconds.
 */
export interface DecodedAnimationFrame {
  bitmap: ImageBitmap
  /** Intrinsic frame duration in microseconds (1 / FPS × 1e6). */
  duration: number
}

export async function decodeAnimatedImageFrames(file: File): Promise<DecodedAnimationFrame[]> {
  const ImageDecoderCtor = (globalThis as unknown as { ImageDecoder?: typeof ImageDecoder }).ImageDecoder
  if (!ImageDecoderCtor) {
    throw new Error('ImageDecoder API not supported. Requires Chrome/Edge 94+.')
  }
  const buffer = await file.arrayBuffer()
  const decoder = new ImageDecoderCtor({ data: buffer, type: file.type })
  try {
    await decoder.tracks.ready
    const track = decoder.tracks.selectedTrack
    if (!track) throw new Error('No decodable track in animation.')
    const frameCount = track.frameCount
    const out: DecodedAnimationFrame[] = []
    for (let i = 0; i < frameCount; i++) {
      const result = await decoder.decode({ frameIndex: i })
      const bitmap = await createImageBitmap(result.image)
      const duration = result.image.duration ?? 100_000
      out.push({ bitmap, duration })
      result.image.close()
    }
    return out
  } finally {
    decoder.close?.()
  }
}

/** Returns true for file types WebCodecs ImageDecoder can unpack into multiple frames. */
export function isAnimatedImageMime(type: string): boolean {
  return type === 'image/gif' || type === 'image/webp' || type === 'image/apng' || type === 'image/avif'
}

export interface ExpandedFileFrames {
  /** Source file index in the original File[] (for metadata). */
  fileIndex: number
  /** True if this came from an animated source (GIF / WebP anim / APNG / AVIF anim). */
  fromAnimation: boolean
  /** Preview-sized bitmaps, one per visual frame. */
  bitmaps: ImageBitmap[]
  /** Per-frame durations in microseconds; empty for stills. */
  durations: number[]
}

/**
 * Convert a list of files into preview bitmaps, expanding animated images
 * (GIF, animated WebP) into all their frames while still returning one
 * ExpandedFileFrames entry per source file.
 */
export async function filesToExpandedPreviewFrames(
  files: File[],
  size = LIVE_PREVIEW_SIZE,
): Promise<ExpandedFileFrames[]> {
  const out: ExpandedFileFrames[] = []
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (isAnimatedImageMime(file.type)) {
      try {
        const decoded = await decodeAnimatedImageFrames(file)
        const bitmaps: ImageBitmap[] = []
        const durations: number[] = []
        for (const frame of decoded) {
          const preview = await bitmapToPreviewBitmap(frame.bitmap, size)
          bitmaps.push(preview)
          durations.push(frame.duration)
          frame.bitmap.close()
        }
        out.push({ fileIndex: i, fromAnimation: true, bitmaps, durations })
        continue
      } catch (err) {
        // Fall through to static handling if decode fails (e.g. a static GIF)
        console.warn(`Animation decode failed for ${file.name}: ${(err as Error).message}. Falling back to first frame.`)
      }
    }
    out.push({
      fileIndex: i,
      fromAnimation: false,
      bitmaps: [await imageFileToPreviewBitmap(file, size)],
      durations: [],
    })
  }
  return out
}

/** Flatten ExpandedFileFrames into a plain ImageBitmap[]. */
export function flattenExpandedFrames(expanded: ExpandedFileFrames[]): ImageBitmap[] {
  const out: ImageBitmap[] = []
  for (const e of expanded) out.push(...e.bitmaps)
  return out
}

export async function imagesToPreviewBitmaps(files: File[], size = LIVE_PREVIEW_SIZE): Promise<ImageBitmap[]> {
  const expanded = await filesToExpandedPreviewFrames(files, size)
  return flattenExpandedFrames(expanded)
}

export async function previewBitmapToJpeg(
  bitmap: ImageBitmap,
  transform: TransformSettings = DEFAULT_TRANSFORM,
  outputSize: OutputFrameSize = { width: E87_IMAGE_WIDTH, height: E87_IMAGE_HEIGHT },
): Promise<Uint8Array> {
  return squareBitmapToJpeg(bitmap, transform, 0.95, outputSize)
}

export async function previewBitmapsToAvi(
  bitmaps: ImageBitmap[],
  fps: number,
  transform: TransformSettings = DEFAULT_TRANSFORM,
  log?: (msg: string) => void,
  outputSize: OutputFrameSize = { width: E87_IMAGE_WIDTH, height: E87_IMAGE_HEIGHT },
): Promise<Uint8Array> {
  if (bitmaps.length === 0) throw new Error('No frames to encode.')
  log?.(`Encoding ${bitmaps.length} cached frames to AVI...`)
  const frames: Uint8Array[] = []
  for (let i = 0; i < bitmaps.length; i++) {
    frames.push(await squareBitmapToJpeg(bitmaps[i], transform, 0.95, outputSize))
    if ((i + 1) % 25 === 0) log?.(`  Encoded ${i + 1}/${bitmaps.length} frames...`)
  }
  const avi = buildMjpgAvi(frames, { fps })
  log?.(`AVI built from cache: ${formatBytes(avi.length)}`)
  return avi
}

/**
 * Convert a single image file to a 368×368 JPEG frame at fixed quality.
 * Used for multi-frame AVI building.
 */
export async function imageFileTo368JpegFrame(file: File, quality = 0.95): Promise<Uint8Array> {
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
  disableSmoothing(ctx)
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
    frames.push(await imageFileTo368JpegFrame(files[i], 0.95))
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

export interface VideoToPreviewFramesOptions {
  fps: number
  trimStart: number
  trimEnd: number
  maxFrames?: number
  previewSize?: number
}

export async function videoToPreviewBitmaps(
  file: File,
  opts: VideoToPreviewFramesOptions,
  log?: (msg: string) => void,
): Promise<ImageBitmap[]> {
  const {
    fps,
    trimStart,
    trimEnd,
    maxFrames,
    previewSize = LIVE_PREVIEW_SIZE,
  } = opts

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

  const start = Math.max(0, trimStart)
  const end = Math.max(start, trimEnd)
  const duration = Math.max(0, end - start)
  const requestedFps = Math.max(1, fps)
  const expectedFrames = Math.ceil(duration * requestedFps)
  const targetFrames = Math.max(1, maxFrames ? Math.min(expectedFrames, maxFrames) : expectedFrames)
  const step = targetFrames <= 1 ? 0 : duration / (targetFrames - 1)
  log?.(`Extracting ${targetFrames} cached preview frames at ${requestedFps}fps...`)

  const canvas = new OffscreenCanvas(previewSize, previewSize)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not create 2D canvas context.')
  disableSmoothing(ctx)

  const srcFullW = video.videoWidth
  const srcFullH = video.videoHeight
  const minDim = Math.min(srcFullW, srcFullH)
  const cropX = (srcFullW - minDim) / 2
  const cropY = (srcFullH - minDim) / 2

  const frames: ImageBitmap[] = []
  const progressStep = Math.max(1, Math.floor(targetFrames / 20))
  for (let i = 0; i < targetFrames; i++) {
    const t = Math.min(end, start + i * step)
    video.currentTime = t
    await new Promise<void>((r) => { video.onseeked = () => r() })

    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, previewSize, previewSize)
    ctx.drawImage(video, cropX, cropY, minDim, minDim, 0, 0, previewSize, previewSize)
    frames.push(await createImageBitmap(canvas))

    if ((i + 1) % progressStep === 0 || i + 1 === targetFrames) {
      const percent = Math.round(((i + 1) / targetFrames) * 100)
      log?.(`  Cached ${i + 1}/${targetFrames} frames (${percent}%)...`)
    }
  }

  URL.revokeObjectURL(url)
  return frames
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
  disableSmoothing(ctx)
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

    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.95 })
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
