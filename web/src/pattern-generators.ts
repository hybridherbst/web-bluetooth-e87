/**
 * Procedural pattern generators for E87/L8 circular LED badge (368×368).
 *
 * LOOPING CONTRACT: Every pattern uses `phase = f / frames` as a 0→1
 * normalized cycle.  Frame 0 and the (hypothetical) frame N must look
 * identical so the device plays a seamless loop at any frame-count/fps.
 */

const SIZE = 368
const HALF = SIZE / 2
const RADIUS = HALF - 2
const TAU = Math.PI * 2

export interface PatternOptions {
  frames: number
  fps: number
  colors?: string[]
}

export interface PatternDef {
  id: string
  name: string
  icon: string
  description: string
  generate: (opts: PatternOptions) => Promise<Uint8Array[]>
}

// ─── Helpers ───

function createCanvas(): [OffscreenCanvas, OffscreenCanvasRenderingContext2D] {
  const canvas = new OffscreenCanvas(SIZE, SIZE)
  const ctx = canvas.getContext('2d')!
  return [canvas, ctx]
}

function clear(ctx: OffscreenCanvasRenderingContext2D, bg = '#000') {
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, SIZE, SIZE)
}

function circularMask(ctx: OffscreenCanvasRenderingContext2D) {
  ctx.globalCompositeOperation = 'destination-in'
  ctx.beginPath()
  ctx.arc(HALF, HALF, RADIUS, 0, TAU)
  ctx.fill()
  ctx.globalCompositeOperation = 'source-over'
}

async function toJpeg(canvas: OffscreenCanvas, quality = 0.9): Promise<Uint8Array> {
  const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality })
  return new Uint8Array(await blob.arrayBuffer())
}

/** Attempt to freeze a seeded PRNG state for reproducibility. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// ═══════════════════════════════════════════════════════
// 1. Matrix Rain  (seamless loop: columns wrap at cycle)
// ═══════════════════════════════════════════════════════

async function generateMatrixRain(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const cols = 24
  const cellW = SIZE / cols
  const cellH = 14
  const rows = Math.ceil(SIZE / cellH)
  const chars = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'.split('')
  const rng = mulberry32(42)
  const frames: Uint8Array[] = []

  // Per-column: fixed speed & phase offset so they wrap over 1 cycle
  const colSpeed = Array.from({ length: cols }, () => 0.8 + rng() * 1.2) // rows per phase-unit
  const colPhase = Array.from({ length: cols }, () => rng())
  // Pre-pick characters per (col,row) so they're stable between frames
  const charGrid = Array.from({ length: cols }, () =>
    Array.from({ length: rows + 20 }, () => chars[Math.floor(rng() * chars.length)])
  )

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames // 0→1
    clear(ctx, '#000')

    for (let c = 0; c < cols; c++) {
      const totalTravel = (rows + 20) // total rows a drop traverses
      const dropPos = ((phase + colPhase[c]) * totalTravel * colSpeed[c]) % totalTravel

      for (let r = 0; r < rows; r++) {
        const dist = dropPos - r
        const wrapped = ((dist % totalTravel) + totalTravel) % totalTravel
        if (wrapped > 18) continue
        const alpha = wrapped < 0.5 ? 1 : Math.max(0, 1 - wrapped / 18)
        const isHead = wrapped < 0.5
        const green = isHead ? 255 : Math.floor(200 * alpha)
        ctx.fillStyle = isHead ? '#fff' : `rgba(0,${green},0,${alpha})`
        ctx.font = `${cellH}px monospace`
        ctx.fillText(charGrid[c][r % charGrid[c].length], c * cellW, r * cellH)
      }
    }

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 2. Game of Life  (pre-warm, then capture exactly N frames, loop)
// ═══════════════════════════════════════════════════════

async function generateGameOfLife(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const cellSize = 6
  const gridW = Math.ceil(SIZE / cellSize)
  const gridH = Math.ceil(SIZE / cellSize)
  const colors = opts.colors ?? ['#00ffcc', '#00aaff', '#ff44cc']

  function makeGrid(rng: () => number): number[][] {
    return Array.from({ length: gridH }, (_, y) =>
      Array.from({ length: gridW }, (_, x) => {
        const dx = x - gridW / 2, dy = y - gridH / 2
        const dist = Math.sqrt(dx * dx + dy * dy) / (gridW / 2)
        return rng() < (dist < 0.8 ? 0.35 : 0.05) ? 1 : 0
      })
    )
  }

  function step(g: number[][]): number[][] {
    const next = g.map(r => [...r])
    for (let y = 0; y < gridH; y++) {
      for (let x = 0; x < gridW; x++) {
        let n = 0
        for (let dy = -1; dy <= 1; dy++)
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) continue
            n += g[(y + dy + gridH) % gridH][(x + dx + gridW) % gridW]
          }
        next[y][x] = g[y][x] ? (n === 2 || n === 3 ? 1 : 0) : (n === 3 ? 1 : 0)
      }
    }
    return next
  }

  function drawGrid(g: number[][]) {
    clear(ctx, '#0a0a12')
    for (let y = 0; y < gridH; y++) {
      for (let x = 0; x < gridW; x++) {
        if (!g[y][x]) continue
        let n = 0
        for (let dy = -1; dy <= 1; dy++)
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) continue
            n += g[(y + dy + gridH) % gridH][(x + dx + gridW) % gridW]
          }
        ctx.fillStyle = colors[Math.min(n, colors.length - 1) % colors.length]
        ctx.fillRect(x * cellSize, y * cellSize, cellSize - 1, cellSize - 1)
      }
    }
  }

  // Strategy: run N+warmup steps, keep the last N as the loop.
  // We pre-warm 200 steps so the chaotic start settles, then capture N.
  // To make it "loop" we crossfade the first and last few frames.
  const warmup = 200
  const rng = mulberry32(1337)
  let grid = makeGrid(rng)
  for (let i = 0; i < warmup; i++) grid = step(grid)

  // Capture N grids
  const grids: number[][][] = []
  for (let f = 0; f < opts.frames; f++) {
    grids.push(grid.map(r => [...r]))
    grid = step(grid)
  }

  // Crossfade first/last ~10% for seamless loop
  const fadeLen = Math.max(1, Math.floor(opts.frames * 0.1))
  const frames: Uint8Array[] = []

  for (let f = 0; f < opts.frames; f++) {
    if (f >= opts.frames - fadeLen) {
      // Blend toward frame 0
      const blendFactor = (f - (opts.frames - fadeLen)) / fadeLen
      const g0 = grids[f]
      const g1 = grids[f - (opts.frames - fadeLen)]
      clear(ctx, '#0a0a12')
      // Draw both with alpha blending
      ctx.globalAlpha = 1 - blendFactor
      drawGrid(g0)
      circularMask(ctx)
      // Overlay the start frame
      const [canvas2, ctx2] = createCanvas()
      ctx2.globalAlpha = 1
      // redraw on ctx directly with blend
      clear(ctx, '#0a0a12')
      // Draw base
      for (let y = 0; y < gridH; y++)
        for (let x = 0; x < gridW; x++) {
          const alive0 = g0[y][x], alive1 = g1[y][x]
          if (!alive0 && !alive1) continue
          const a = alive0 ? (1 - blendFactor) : 0
          const b = alive1 ? blendFactor : 0
          const total = Math.min(1, a + b)
          let n = 0
          const src = alive0 ? g0 : g1
          for (let dy = -1; dy <= 1; dy++)
            for (let dx = -1; dx <= 1; dx++) {
              if (dx === 0 && dy === 0) continue
              n += src[(y + dy + gridH) % gridH][(x + dx + gridW) % gridW]
            }
          ctx.globalAlpha = total
          ctx.fillStyle = colors[Math.min(n, colors.length - 1) % colors.length]
          ctx.fillRect(x * cellSize, y * cellSize, cellSize - 1, cellSize - 1)
        }
      ctx.globalAlpha = 1
      canvas2.width = 0 // release
    } else {
      drawGrid(grids[f])
    }
    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 3. Plasma Waves  (loop: phase = f/frames * TAU)
// ═══════════════════════════════════════════════════════

async function generatePlasmaWaves(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const imageData = ctx.createImageData(SIZE, SIZE)
  const frames: Uint8Array[] = []

  for (let f = 0; f < opts.frames; f++) {
    const t = (f / opts.frames) * TAU  // loops at TAU
    const data = imageData.data

    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        const nx = x / SIZE - 0.5, ny = y / SIZE - 0.5
        const v1 = Math.sin(x * 0.03 + t * 2.5)
        const v2 = Math.sin(y * 0.04 - t * 1.8)
        const v3 = Math.sin((x + y) * 0.02 + t * 3.0)
        const v4 = Math.sin(Math.sqrt(nx * nx + ny * ny) * 20 - t * 4)
        const v = (v1 + v2 + v3 + v4) / 4

        const i = (y * SIZE + x) * 4
        data[i]     = Math.floor((Math.sin(v * Math.PI) * 0.5 + 0.5) * 120)
        data[i + 1] = Math.floor((Math.sin(v * Math.PI + 2) * 0.5 + 0.5) * 255)
        data[i + 2] = Math.floor((Math.sin(v * Math.PI + 4) * 0.5 + 0.5) * 255)
        data[i + 3] = 255
      }
    }

    ctx.putImageData(imageData, 0, 0)
    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 4. Braille Matrix  (loop: phase-based wave)
// ═══════════════════════════════════════════════════════

async function generateBrailleMatrix(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const brailleBase = 0x2800
  const fontSize = 16
  const cols = Math.floor(SIZE / (fontSize * 0.6))
  const rows = Math.floor(SIZE / fontSize)
  const frames: Uint8Array[] = []

  const phaseGrid = Array.from({ length: rows }, (_, y) =>
    Array.from({ length: cols }, (_, x) =>
      Math.sqrt((x - cols / 2) ** 2 + (y - rows / 2) ** 2)
    )
  )

  for (let f = 0; f < opts.frames; f++) {
    const t = (f / opts.frames) * TAU
    clear(ctx, '#000')
    ctx.font = `${fontSize}px monospace`

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const wave = Math.sin(phaseGrid[r][c] * 0.3 - t * 3)
        const bits = Math.floor((wave * 0.5 + 0.5) * 255) & 0xff
        const char = String.fromCharCode(brailleBase + bits)
        const brightness = Math.floor((wave * 0.5 + 0.5) * 200) + 55
        ctx.fillStyle = `rgb(${brightness * 0.3},${brightness * 0.8},${brightness})`
        ctx.fillText(char, c * fontSize * 0.6, r * fontSize + fontSize)
      }
    }

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 5. Circular Progress  (loop: phase = f/frames)
// ═══════════════════════════════════════════════════════

async function generateCircularProgress(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []
  const ringCount = 5
  const ringWidth = 18
  const gap = 6
  const ringColors = ['#ff3366', '#ff9933', '#33ff99', '#3399ff', '#cc33ff']

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    clear(ctx, '#0a0a14')

    for (let i = 0; i < ringCount; i++) {
      const r = RADIUS - i * (ringWidth + gap) - gap
      if (r < 20) break
      // Each ring completes a different number of full rotations per loop
      const cycles = 1 + i * 0.5
      const progress = (phase * cycles + i * 0.2) % 1
      const angle = progress * TAU
      const direction = i % 2 === 0 ? 1 : -1

      ctx.beginPath()
      ctx.arc(HALF, HALF, r, -Math.PI / 2, -Math.PI / 2 + angle * direction, direction < 0)
      ctx.strokeStyle = ringColors[i % ringColors.length]
      ctx.lineWidth = ringWidth
      ctx.lineCap = 'round'
      ctx.stroke()

      const tipAngle = -Math.PI / 2 + angle * direction
      const tx = HALF + Math.cos(tipAngle) * r
      const ty = HALF + Math.sin(tipAngle) * r
      ctx.beginPath()
      ctx.arc(tx, ty, ringWidth / 2 + 2, 0, TAU)
      ctx.fillStyle = '#fff'
      ctx.globalAlpha = 0.4
      ctx.fill()
      ctx.globalAlpha = 1
    }

    // Pulsing center circle instead of non-looping percentage
    const pulse = Math.sin(phase * TAU * 3) * 0.3 + 0.7
    const grad = ctx.createRadialGradient(HALF, HALF, 0, HALF, HALF, 30 * pulse)
    grad.addColorStop(0, 'rgba(255,255,255,0.7)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(HALF, HALF, 30 * pulse, 0, TAU)
    ctx.fill()

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 6. Radar Sweep  (loop: sweep completes exact integer rotations)
// ═══════════════════════════════════════════════════════

async function generateRadarSweep(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []
  const rng = mulberry32(77)

  const blips = Array.from({ length: 12 }, () => ({
    angle: rng() * TAU,
    dist: 30 + rng() * (RADIUS - 50),
    size: 3 + rng() * 4,
  }))

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    const sweepAngle = phase * TAU * 2 // 2 full rotations per loop
    clear(ctx, '#001008')

    // Grid rings
    ctx.strokeStyle = 'rgba(0,255,80,0.15)'
    ctx.lineWidth = 1
    for (let r = 40; r < RADIUS; r += 40) {
      ctx.beginPath()
      ctx.arc(HALF, HALF, r, 0, TAU)
      ctx.stroke()
    }
    for (let a = 0; a < 4; a++) {
      const angle = (a * Math.PI) / 4
      ctx.beginPath()
      ctx.moveTo(HALF + Math.cos(angle) * 20, HALF + Math.sin(angle) * 20)
      ctx.lineTo(HALF + Math.cos(angle) * RADIUS, HALF + Math.sin(angle) * RADIUS)
      ctx.stroke()
    }

    // Sweep gradient
    const gradient = ctx.createConicGradient(sweepAngle - Math.PI / 3, HALF, HALF)
    gradient.addColorStop(0, 'rgba(0,255,80,0)')
    gradient.addColorStop(0.08, 'rgba(0,255,80,0.3)')
    gradient.addColorStop(0.1, 'rgba(0,255,80,0.0)')
    gradient.addColorStop(1, 'rgba(0,255,80,0)')
    ctx.fillStyle = gradient
    ctx.beginPath()
    ctx.arc(HALF, HALF, RADIUS, 0, TAU)
    ctx.fill()

    // Sweep line
    ctx.beginPath()
    ctx.moveTo(HALF, HALF)
    ctx.lineTo(HALF + Math.cos(sweepAngle) * RADIUS, HALF + Math.sin(sweepAngle) * RADIUS)
    ctx.strokeStyle = 'rgba(0,255,80,0.8)'
    ctx.lineWidth = 2
    ctx.stroke()

    // Blips
    for (const b of blips) {
      let angleDiff = sweepAngle - b.angle
      angleDiff = ((angleDiff % TAU) + TAU) % TAU
      const brightness = angleDiff < 1.5 ? Math.max(0, 1 - angleDiff / 1.5) : 0
      if (brightness < 0.05) continue
      ctx.beginPath()
      ctx.arc(HALF + Math.cos(b.angle) * b.dist, HALF + Math.sin(b.angle) * b.dist, b.size, 0, TAU)
      ctx.fillStyle = `rgba(0,255,80,${brightness})`
      ctx.fill()
    }

    ctx.beginPath()
    ctx.arc(HALF, HALF, 4, 0, TAU)
    ctx.fillStyle = '#0f6'
    ctx.fill()

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 7. Hypnotic Spirals  (loop: phase * TAU)
// ═══════════════════════════════════════════════════════

async function generateHypnoticSpirals(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []
  const arms = 6
  const spiralColors = ['#ff0066', '#0066ff', '#ffcc00', '#00ff99', '#cc33ff', '#ff6600']

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    const t = phase * TAU
    clear(ctx, '#000')

    for (let arm = 0; arm < arms; arm++) {
      const baseAngle = (arm / arms) * TAU + t * 0.8
      ctx.beginPath()
      for (let r = 0; r < RADIUS; r += 1) {
        const twist = r * 0.02 + Math.sin(r * 0.01 + t * 2) * 0.5
        const angle = baseAngle + twist
        const x = HALF + Math.cos(angle) * r
        const y = HALF + Math.sin(angle) * r
        if (r === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.strokeStyle = spiralColors[arm % spiralColors.length]
      ctx.lineWidth = 3
      ctx.globalAlpha = 0.7
      ctx.stroke()
      ctx.globalAlpha = 1
    }

    const pulse = Math.sin(t * 4) * 0.3 + 0.7
    const grad = ctx.createRadialGradient(HALF, HALF, 0, HALF, HALF, 40 * pulse)
    grad.addColorStop(0, 'rgba(255,255,255,0.8)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(HALF, HALF, 40 * pulse, 0, TAU)
    ctx.fill()

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 8. Digital Circuit  (loop: pulse wraps by phase)
// ═══════════════════════════════════════════════════════

async function generateDigitalCircuit(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []
  const rng = mulberry32(999)
  const circuitColors = ['#0ff', '#0af', '#f0f', '#0f6', '#fa0']

  const pathCount = 30
  const paths: { points: [number, number][]; color: string; totalLen: number }[] = []

  for (let i = 0; i < pathCount; i++) {
    const points: [number, number][] = []
    let x = rng() * SIZE, y = rng() * SIZE
    points.push([x, y])
    for (let s = 0; s < 8; s++) {
      const dir = Math.floor(rng() * 4)
      const len = 20 + rng() * 60
      if (dir === 0) x += len
      else if (dir === 1) y += len
      else if (dir === 2) x -= len
      else y -= len
      x = Math.max(0, Math.min(SIZE, x))
      y = Math.max(0, Math.min(SIZE, y))
      points.push([x, y])
    }
    let totalLen = 0
    for (let j = 1; j < points.length; j++) {
      const dx = points[j][0] - points[j - 1][0]
      const dy = points[j][1] - points[j - 1][1]
      totalLen += Math.sqrt(dx * dx + dy * dy)
    }
    paths.push({ points, color: circuitColors[i % circuitColors.length], totalLen })
  }

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    clear(ctx, '#050510')

    // Dim traces
    ctx.lineWidth = 1.5
    ctx.globalAlpha = 0.15
    for (const p of paths) {
      ctx.beginPath()
      ctx.strokeStyle = p.color
      for (let i = 0; i < p.points.length; i++) {
        if (i === 0) ctx.moveTo(p.points[i][0], p.points[i][1])
        else ctx.lineTo(p.points[i][0], p.points[i][1])
      }
      ctx.stroke()
    }
    ctx.globalAlpha = 1

    // Animated pulses — wrap using modulo over totalLen
    for (const p of paths) {
      const pos = (phase * p.totalLen * 1.5) % p.totalLen

      let acc = 0
      for (let i = 1; i < p.points.length; i++) {
        const dx = p.points[i][0] - p.points[i - 1][0]
        const dy = p.points[i][1] - p.points[i - 1][1]
        const segLen = Math.sqrt(dx * dx + dy * dy)
        if (pos >= acc && pos < acc + segLen) {
          const frac = (pos - acc) / segLen
          const px = p.points[i - 1][0] + dx * frac
          const py = p.points[i - 1][1] + dy * frac
          ctx.beginPath()
          ctx.arc(px, py, 3, 0, TAU)
          ctx.fillStyle = '#fff'
          ctx.fill()
          const glow = ctx.createRadialGradient(px, py, 0, px, py, 12)
          glow.addColorStop(0, p.color)
          glow.addColorStop(1, 'transparent')
          ctx.fillStyle = glow
          ctx.globalAlpha = 0.5
          ctx.beginPath()
          ctx.arc(px, py, 12, 0, TAU)
          ctx.fill()
          ctx.globalAlpha = 1
          break
        }
        acc += segLen
      }

      for (const pt of p.points) {
        ctx.beginPath()
        ctx.arc(pt[0], pt[1], 2, 0, TAU)
        ctx.fillStyle = 'rgba(100,200,255,0.3)'
        ctx.fill()
      }
    }

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 9. Concentric Waves  ✨ NEW
// ═══════════════════════════════════════════════════════

async function generateConcentricWaves(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const imageData = ctx.createImageData(SIZE, SIZE)
  const frames: Uint8Array[] = []

  const waveColors = [
    [0, 180, 255],
    [80, 255, 200],
    [200, 100, 255],
  ]

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    const t = phase * TAU
    const data = imageData.data

    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        const dx = x - HALF, dy = y - HALF
        const dist = Math.sqrt(dx * dx + dy * dy)

        // Multiple concentric wave rings expanding outward
        const wave1 = Math.sin(dist * 0.06 - t * 3) * 0.5 + 0.5
        const wave2 = Math.sin(dist * 0.04 - t * 2 + 1.5) * 0.5 + 0.5
        const wave3 = Math.sin(dist * 0.08 - t * 4 + 3.0) * 0.5 + 0.5

        // Blend waves with different colors
        const i = (y * SIZE + x) * 4
        data[i]     = Math.floor(waveColors[0][0] * wave1 + waveColors[1][0] * wave2 + waveColors[2][0] * wave3) / 2
        data[i + 1] = Math.floor(waveColors[0][1] * wave1 + waveColors[1][1] * wave2 + waveColors[2][1] * wave3) / 2
        data[i + 2] = Math.floor(waveColors[0][2] * wave1 + waveColors[1][2] * wave2 + waveColors[2][2] * wave3) / 2
        data[i + 3] = 255

        // Fade out at edges
        const edgeFade = Math.max(0, 1 - dist / RADIUS)
        data[i]     = Math.floor(data[i] * edgeFade)
        data[i + 1] = Math.floor(data[i + 1] * edgeFade)
        data[i + 2] = Math.floor(data[i + 2] * edgeFade)
      }
    }

    ctx.putImageData(imageData, 0, 0)
    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 10. Dither Magic  ✨ NEW
// ═══════════════════════════════════════════════════════

async function generateDitherMagic(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const imageData = ctx.createImageData(SIZE, SIZE)
  const frames: Uint8Array[] = []

  // Bayer 8×8 dither matrix
  const bayer8 = [
    [ 0,32, 8,40, 2,34,10,42],
    [48,16,56,24,50,18,58,26],
    [12,44, 4,36,14,46, 6,38],
    [60,28,52,20,62,30,54,22],
    [ 3,35,11,43, 1,33, 9,41],
    [51,19,59,27,49,17,57,25],
    [15,47, 7,39,13,45, 5,37],
    [63,31,55,23,61,29,53,21],
  ]

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    const t = phase * TAU
    const data = imageData.data

    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        const dx = x - HALF, dy = y - HALF
        const dist = Math.sqrt(dx * dx + dy * dy) / RADIUS
        const angle = Math.atan2(dy, dx)

        // Animated gradient — morphing shapes
        const v1 = Math.sin(dist * 8 - t * 2) * 0.5 + 0.5
        const v2 = Math.sin(angle * 3 + t * 1.5) * 0.5 + 0.5
        const v3 = Math.sin(dist * 4 + angle * 2 - t * 3) * 0.5 + 0.5
        const intensity = (v1 + v2 + v3) / 3

        // Apply Bayer dithering
        const threshold = bayer8[y & 7][x & 7] / 64
        const dithered = intensity > threshold ? 1 : 0

        // Color palette cycles with phase
        const hueShift = t * 0.5
        const r = Math.sin(hueShift) * 0.5 + 0.5
        const g = Math.sin(hueShift + 2.094) * 0.5 + 0.5
        const b = Math.sin(hueShift + 4.189) * 0.5 + 0.5

        const i = (y * SIZE + x) * 4
        if (dithered) {
          data[i]     = Math.floor(r * 255)
          data[i + 1] = Math.floor(g * 255)
          data[i + 2] = Math.floor(b * 255)
        } else {
          data[i]     = Math.floor(r * 30)
          data[i + 1] = Math.floor(g * 30)
          data[i + 2] = Math.floor(b * 30)
        }
        data[i + 3] = 255
      }
    }

    ctx.putImageData(imageData, 0, 0)
    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// 11. Emoji Burst  ✨ NEW
// ═══════════════════════════════════════════════════════

async function generateEmojiBurst(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []
  const rng = mulberry32(2025)

  const emojis = ['🔥', '⭐', '💜', '🌈', '✨', '🎉', '💎', '🌸', '🚀', '🎶', '💥', '🌀']
  const particleCount = 28

  // Each particle has a fixed trajectory from center outward, looping
  const particles = Array.from({ length: particleCount }, () => {
    const angle = rng() * TAU
    const speed = 0.3 + rng() * 0.7 // fraction of RADIUS per cycle
    const phaseOffset = rng() // stagger launches
    const emoji = emojis[Math.floor(rng() * emojis.length)]
    const spin = (rng() - 0.5) * TAU * 2 // rotation per cycle
    const sizeBase = 18 + rng() * 18
    return { angle, speed, phaseOffset, emoji, spin, sizeBase }
  })

  for (let f = 0; f < opts.frames; f++) {
    const phase = f / opts.frames
    clear(ctx, '#0a0010')

    // Subtle radial glow at center
    const cg = ctx.createRadialGradient(HALF, HALF, 0, HALF, HALF, 60)
    cg.addColorStop(0, 'rgba(180,100,255,0.3)')
    cg.addColorStop(1, 'rgba(180,100,255,0)')
    ctx.fillStyle = cg
    ctx.beginPath()
    ctx.arc(HALF, HALF, 60, 0, TAU)
    ctx.fill()

    for (const p of particles) {
      // t goes 0→1 for this particle's journey outward, then wraps
      const t = ((phase + p.phaseOffset) % 1)
      const dist = t * RADIUS * p.speed * 2
      if (dist > RADIUS + 20) continue

      const x = HALF + Math.cos(p.angle) * dist
      const y = HALF + Math.sin(p.angle) * dist

      // Fade: ramp in 0→0.1, full 0.1→0.7, fade out 0.7→1
      let alpha = 1
      if (t < 0.1) alpha = t / 0.1
      else if (t > 0.7) alpha = Math.max(0, 1 - (t - 0.7) / 0.3)

      // Size: starts small, grows, then shrinks slightly
      const sizeMul = t < 0.2 ? t / 0.2 : 1 - (t - 0.2) * 0.3
      const size = p.sizeBase * Math.max(0.3, sizeMul)

      ctx.save()
      ctx.translate(x, y)
      ctx.rotate(p.spin * phase)
      ctx.globalAlpha = alpha * 0.9
      ctx.font = `${Math.round(size)}px serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(p.emoji, 0, 0)
      ctx.restore()
    }
    ctx.globalAlpha = 1

    circularMask(ctx)
    frames.push(await toJpeg(canvas))
  }
  return frames
}

// ═══════════════════════════════════════════════════════
// Registry
// ═══════════════════════════════════════════════════════

export const PATTERNS: PatternDef[] = [
  {
    id: 'matrix',
    name: 'Matrix Rain',
    icon: '🟩',
    description: 'Cascading green characters',
    generate: generateMatrixRain,
  },
  {
    id: 'gameoflife',
    name: 'Game of Life',
    icon: '🧬',
    description: 'Conway\'s cellular automata',
    generate: generateGameOfLife,
  },
  {
    id: 'plasma',
    name: 'Plasma Waves',
    icon: '🌊',
    description: 'Psychedelic color plasma',
    generate: generatePlasmaWaves,
  },
  {
    id: 'braille',
    name: 'Braille Matrix',
    icon: '⠿',
    description: 'Unicode braille wave patterns',
    generate: generateBrailleMatrix,
  },
  {
    id: 'progress',
    name: 'Circular Progress',
    icon: '⭕',
    description: 'Multi-ring progress indicators',
    generate: generateCircularProgress,
  },
  {
    id: 'radar',
    name: 'Radar Sweep',
    icon: '📡',
    description: 'Sci-fi radar with blips',
    generate: generateRadarSweep,
  },
  {
    id: 'spirals',
    name: 'Hypnotic Spirals',
    icon: '🌀',
    description: 'Twisting neon spiral arms',
    generate: generateHypnoticSpirals,
  },
  {
    id: 'circuit',
    name: 'Digital Circuit',
    icon: '⚡',
    description: 'Animated circuit board traces',
    generate: generateDigitalCircuit,
  },
  {
    id: 'waves',
    name: 'Concentric Waves',
    icon: '🎯',
    description: 'Expanding ripple rings',
    generate: generateConcentricWaves,
  },
  {
    id: 'dither',
    name: 'Dither Magic',
    icon: '🔲',
    description: 'Bayer dithered color shapes',
    generate: generateDitherMagic,
  },
  {
    id: 'emoji',
    name: 'Emoji Burst',
    icon: '🎉',
    description: 'Emojis exploding from center',
    generate: generateEmojiBurst,
  },
]
