export function scrollLayout(textWidth: number, speed: number, fps = 15, frameSize = 368) {
  if (![textWidth, speed, fps, frameSize].every(Number.isFinite) || textWidth < 0 || speed <= 0 || fps <= 0 || frameSize <= 0) {
    throw new Error('Некорректные параметры бегущей строки.')
  }
  const distance = textWidth + frameSize + 32
  const count = Math.ceil(distance / speed * fps)
  if (count > 240) throw new Error('Для этой скорости текст слишком длинный. Ускорьте строку, уменьшите шрифт или сократите текст.')
  return { distance, count, duration: count / fps }
}
