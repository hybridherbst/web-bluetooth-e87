import { scrollLayout } from './text-layout'
import { canvasToBadgeJpeg } from '../lib/image-encoding'
import type { PatternDef, PatternOptions } from '../pattern-generators'

const TAU = Math.PI * 2
const SIZE = 368
const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)))
const mix = (a: number, b: number, t: number) => a + (b - a) * t

export const FASHION_IDS = ['chrome', 'pearl', 'silk', 'aurora', 'dichroic', 'eclipse', 'jewels', 'contour']

// A small software shader: evaluate a looping material, then sample it smoothly
// into the badge frame. Integer multiples of phase keep the loop seamless.
async function material(kind: string, opts: PatternOptions): Promise<Uint8Array[]> {
  const sample = 184
  const small = new OffscreenCanvas(sample, sample)
  const sc = small.getContext('2d')!
  const canvas = new OffscreenCanvas(SIZE, SIZE)
  const ctx = canvas.getContext('2d')!
  const pixels = sc.createImageData(sample, sample)
  const frames: Uint8Array[] = []
  for (let f = 0; f < opts.frames; f++) {
    const t = TAU * f / opts.frames
    for (let y = 0; y < sample; y++) for (let x = 0; x < sample; x++) {
      const u = (x + .5 - sample / 2) / (sample / 2)
      const v = (y + .5 - sample / 2) / (sample / 2)
      const r = Math.hypot(u, v)
      const a = Math.atan2(v, u)
      let red = 3, green = 4, blue = 5
      if (r < .96) {
        const z = Math.sqrt(Math.max(0, 1 - r * r))
        const edge = Math.min(1, (.96 - r) * 35)
        const wave = Math.sin(5 * u + 3 * v + 1.8 * Math.sin(3 * v - t) + t)
        if (kind === 'chrome') {
          const nx = u + .24 * Math.sin(4 * v + t) + .11 * Math.sin(8 * u - t)
          const ny = v + .22 * Math.cos(4 * u - t)
          const env = Math.sin(8 * nx + 5 * ny + 5 * z + .7 * Math.sin(t))
          const reflected = Math.pow(.5 + .5 * env, 9)
          const rim = Math.pow(r, 7) * 80
          const light = 14 + 175 * reflected + 43 * Math.pow(.5 + .5 * Math.sin(4 * nx - 2 * ny), 2) + rim
          red = light * .94; green = light * 1.03; blue = light * 1.12
        } else if (kind === 'pearl') {
          const ir = 5 * z + 3 * u + wave * .4 + t
          const shine = 35 * Math.pow(Math.max(0, z * .8 - u * .4 - v * .3), 12)
          const lum = .35 + .65 * z
          red = (190 + 53 * Math.sin(ir) + shine) * lum
          green = (194 + 41 * Math.sin(ir + 2.1) + shine) * lum
          blue = (207 + 44 * Math.sin(ir + 4.2) + shine) * lum
        } else if (kind === 'silk') {
          const fold = .5 + .5 * Math.sin(11 * u + 3 * Math.sin(3 * v + t) + 2 * Math.cos(2 * u - t))
          const highlight = Math.pow(fold, 7)
          const velvet = .65 + .35 * Math.cos(v * 2)
          red = (26 + 202 * highlight + 30 * fold) * velvet
          green = (4 + 35 * highlight) * velvet
          blue = (16 + 75 * highlight) * velvet
        } else if (kind === 'aurora') {
          const ribbon = Math.exp(-Math.pow(4 * (v + .24 * Math.sin(4 * u + t)), 2))
          const detail = .4 + .6 * Math.pow(.5 + .5 * Math.sin(20 * u + 2 * Math.sin(t)), 2)
          const glow = ribbon * detail * (1 - r * .45)
          const hue = .5 + .5 * Math.sin(2 * u + t)
          red = 5 + glow * mix(80, 189, hue)
          green = 8 + glow * mix(244, 91, hue)
          blue = 13 + glow * mix(166, 251, hue)
        } else if (kind === 'dichroic') {
          const glass = Math.sin(5 * z + 4 * u + 2 * Math.sin(3 * v + t) - t)
          const facet = Math.pow(.5 + .5 * Math.cos(3 * a + 3 * r + t), 6)
          red = 18 + (128 + 100 * Math.sin(glass * 2 + t)) * (.25 + .75 * facet)
          green = 18 + (128 + 100 * Math.sin(glass * 2 + t + 2.1)) * (.35 + .65 * z)
          blue = 24 + (128 + 100 * Math.sin(glass * 2 + t + 4.2)) * (.4 + .6 * facet)
        } else {
          const contour = Math.pow(.5 + .5 * Math.cos(24 * r + 3 * Math.sin(3 * a + t) - 2 * t), 14)
          const lit = .35 + .65 * Math.pow(.5 + .5 * Math.sin(a - t), 2)
          red = 4 + 154 * contour * lit; green = 8 + 199 * contour * lit; blue = 8 + 133 * contour * lit
        }
        red *= edge; green *= edge; blue *= edge
      }
      const i = (y * sample + x) * 4
      pixels.data[i] = clamp(red); pixels.data[i + 1] = clamp(green); pixels.data[i + 2] = clamp(blue); pixels.data[i + 3] = 255
    }
    sc.putImageData(pixels, 0, 0)
    ctx.drawImage(small, 0, 0, SIZE, SIZE)
    frames.push(await canvasToBadgeJpeg(canvas, .82))
  }
  return frames
}

async function jewelry(kind: string, opts: PatternOptions): Promise<Uint8Array[]> {
  const canvas = new OffscreenCanvas(SIZE, SIZE)
  const ctx = canvas.getContext('2d')!
  const frames: Uint8Array[] = []
  for (let f = 0; f < opts.frames; f++) {
    const t = TAU * f / opts.frames
    ctx.fillStyle = '#030504'; ctx.fillRect(0, 0, SIZE, SIZE)
    ctx.save(); ctx.translate(SIZE / 2, SIZE / 2)
    if (kind === 'eclipse') {
      const gradient = ctx.createRadialGradient(-20 * Math.cos(t), -20 * Math.sin(t), 118, 0, 0, 170)
      gradient.addColorStop(0, '#030504'); gradient.addColorStop(.6, '#342815'); gradient.addColorStop(.76, '#e7c27a'); gradient.addColorStop(.82, '#fff0cb'); gradient.addColorStop(.92, '#5f431b'); gradient.addColorStop(1, '#030504')
      ctx.fillStyle = gradient; ctx.beginPath(); ctx.arc(0, 0, 170, 0, TAU); ctx.fill()
      ctx.fillStyle = '#030504'; ctx.beginPath(); ctx.arc(12 * Math.cos(t), 12 * Math.sin(t), 138, 0, TAU); ctx.fill()
      ctx.rotate(t); ctx.strokeStyle = '#ffedb7'; ctx.lineWidth = 1
      ctx.beginPath(); ctx.arc(0, 0, 168, -.25, .18); ctx.stroke()
    } else {
      for (let ring = 0; ring < 3; ring++) {
        const radius = 90 + ring * 31
        const count = 32 + ring * 16
        ctx.strokeStyle = '#25312e'; ctx.lineWidth = .7; ctx.beginPath(); ctx.arc(0, 0, radius, 0, TAU); ctx.stroke()
        for (let n = 0; n < count; n++) {
          const a = n * TAU / count + (ring % 2 ? -t : t)
          const x = radius * Math.cos(a), y = radius * Math.sin(a)
          const glow = Math.pow(.5 + .5 * Math.cos(a * 3 + t * 2 + ring), 9)
          const light = 28 + 70 * glow
          ctx.fillStyle = `hsl(${157 + ring * 12} 22% ${light}%)`
          ctx.save(); ctx.translate(x, y); ctx.rotate(a + Math.PI / 4); ctx.fillRect(-2, -2, 4, 4); ctx.restore()
          if (glow > .85) {
            ctx.strokeStyle = `rgba(220,255,240,${glow * .6})`; ctx.lineWidth = .8
            ctx.beginPath(); ctx.moveTo(x - 6 * glow, y); ctx.lineTo(x + 6 * glow, y); ctx.moveTo(x, y - 6 * glow); ctx.lineTo(x, y + 6 * glow); ctx.stroke()
          }
        }
      }
    }
    ctx.restore()
    frames.push(await canvasToBadgeJpeg(canvas, .86))
  }
  return frames
}

export const FASHION_PATTERNS: PatternDef[] = [
  { id: 'chrome', name: 'Liquid chrome', icon: '◒', description: 'Жидкий металл', generate: o => material('chrome', o) },
  { id: 'pearl', name: 'Pearl', icon: '◉', description: 'Перламутровый свет', generate: o => material('pearl', o) },
  { id: 'silk', name: 'Crimson silk', icon: '≋', description: 'Бордовый шёлк', generate: o => material('silk', o) },
  { id: 'aurora', name: 'Aurora', icon: '⌁', description: 'Северное сияние', generate: o => material('aurora', o) },
  { id: 'dichroic', name: 'Dichroic', icon: '◇', description: 'Иридисцентное стекло', generate: o => material('dichroic', o) },
  { id: 'eclipse', name: 'Gold eclipse', icon: '◔', description: 'Золотое затмение', generate: o => jewelry('eclipse', o) },
  { id: 'jewels', name: 'After dark', icon: '✧', description: 'Сияние украшений', generate: o => jewelry('jewels', o) },
  { id: 'contour', name: 'Contour', icon: '◎', description: 'Живые линии', generate: o => material('contour', o) },
]

export type TextSettings = { text: string; size: number; speed: number; color: string; background: string; font: 'sans' | 'serif' | 'mono'; direction: 'left' | 'right'; glow: boolean }
export async function generateTextFrames(settings: TextSettings, fps = 15): Promise<Uint8Array[]> {
  const text = settings.text.replace(/\s+/g, ' ').trim()
  if (!text) throw new Error('Введите текст для бегущей строки.')
  const canvas = new OffscreenCanvas(SIZE, SIZE)
  const ctx = canvas.getContext('2d')!
  const fonts = { sans: '600 1px Arial, sans-serif', serif: '500 1px Georgia, serif', mono: '600 1px Menlo, Consolas, monospace' }
  ctx.font = fonts[settings.font].replace('1px', `${settings.size}px`)
  const width = ctx.measureText(text).width
  const { distance, count } = scrollLayout(width, settings.speed, fps, SIZE)
  const frames: Uint8Array[] = []
  for (let f = 0; f < count; f++) {
    ctx.shadowBlur = 0; ctx.fillStyle = settings.background; ctx.fillRect(0, 0, SIZE, SIZE)
    ctx.fillStyle = settings.color; ctx.textBaseline = 'middle'
    ctx.shadowColor = settings.color; ctx.shadowBlur = settings.glow ? 12 : 0
    const offset = f / count * distance
    const x = settings.direction === 'left' ? SIZE - offset : -width + offset
    ctx.fillText(text, x, SIZE / 2 + settings.size * .03)
    frames.push(await canvasToBadgeJpeg(canvas, .82))
  }
  return frames
}
