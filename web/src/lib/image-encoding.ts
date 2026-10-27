/** Encode every badge frame through the same desktop encoder, including AVI frames. */
export async function canvasToBadgeJpeg(
  canvas: OffscreenCanvas | HTMLCanvasElement,
  quality = 0.88,
): Promise<Uint8Array> {
  if (typeof window !== 'undefined' && window.e87Desktop?.encodeJpeg) {
    const ctx = canvas.getContext('2d') as OffscreenCanvasRenderingContext2D | CanvasRenderingContext2D | null
    if (!ctx) throw new Error('Could not read badge pixels.')
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
    return window.e87Desktop.encodeJpeg(data, canvas.width, canvas.height, quality)
  }
  // Preserve the original browser implementation when no desktop bridge exists.
  const blob = 'convertToBlob' in canvas
    ? await canvas.convertToBlob({ type: 'image/jpeg', quality })
    : await new Promise<Blob>((resolve, reject) => canvas.toBlob(
      value => value ? resolve(value) : reject(new Error('JPEG encoding failed.')),
      'image/jpeg', quality,
    ))
  return new Uint8Array(await blob.arrayBuffer())
}
