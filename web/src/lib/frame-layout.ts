export function previewDimensions(width: number, height: number, maxEdge: number) {
  const ratio = Math.min(1, maxEdge / Math.max(width, height))
  return { width: Math.max(1, Math.round(width * ratio)), height: Math.max(1, Math.round(height * ratio)) }
}

/** Keep the full source aspect ratio; preview and exported pixels use the same crop. */
export function frameRect(
  sourceWidth: number, sourceHeight: number, width: number, height: number,
  transform: { scale: number; panX: number; panY: number },
) {
  const cover = Math.max(width / sourceWidth, height / sourceHeight) * transform.scale
  const drawWidth = sourceWidth * cover
  const drawHeight = sourceHeight * cover
  return {
    x: (width - drawWidth) / 2 + transform.panX * width / 2,
    y: (height - drawHeight) / 2 + transform.panY * height / 2,
    width: drawWidth,
    height: drawHeight,
  }
}
