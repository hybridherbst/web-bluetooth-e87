/**
 * Procedural pattern generators for E87/L8 circular LED badge (368x368).
 *
 * Each generator produces N frames of 368x368 pixel data, rendered
 * with a circular mask matching the device's round display.
 * Output: array of JPEG Uint8Array frames ready for buildMjpgAvi().
 */

const SIZE = 368
const HALF = SIZE / 2
const RADIUS = HALF - 2 // slight inset to avoid edge artifacts

export interface PatternOptions {
  frames: number
  fps: number
  /** Color palette - array of CSS color strings */
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

function clearWithBackground(ctx: OffscreenCanvasRenderingContext2D, bg = '#000') {
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, SIZE, SIZE)
}

function applyCircularMask(ctx: OffscreenCanvasRenderingContext2D) {
  ctx.globalCompositeOperation = 'destination-in'
  ctx.beginPath()
  ctx.arc(HALF, HALF, RADIUS, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalCompositeOperation = 'source-over'
}

async function canvasToJpeg(canvas: OffscreenCanvas, quality = 0.9): Promise<Uint8Array> {
  const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality })
  return new Uint8Array(await blob.arrayBuffer())
}

// ─── Pattern: Matrix Rain ───

async function generateMatrixRain(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const cols = 24
  const cellW = SIZE / cols
  const cellH = 14
  const rows = Math.ceil(SIZE / cellH)
  const drops: number[] = Array.from({ length: cols }, () => Math.random() * rows * -1)
  const chars = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'.split('')
  const frames: Uint8Array[] = []

  for (let f = 0; f < opts.frames; f++) {
    clearWithBackground(ctx, '#000')

    for (let c = 0; c < cols; c++) {
      for (let r = 0; r < rows; r++) {
        const dist = drops[c] - r
        if (dist < 0 || dist > 18) continue
        const alpha = dist === 0 ? 1 : Math.max(0, 1 - dist / 18)
        const green = dist === 0 ? 255 : Math.floor(200 * alpha)
        ctx.fillStyle = dist === 0 ? '#fff' : `rgba(0,${green},0,${alpha})`
        ctx.font = `${cellH}px monospace`
        ctx.fillText(chars[Math.floor(Math.random() * chars.length)], c * cellW, r * cellH)
      }
      drops[c] += 0.4 + Math.random() * 0.6
      if (drops[c] > rows + 10) drops[c] = Math.random() * -8
    }

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Pattern: Game of Life ───

async function generateGameOfLife(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const cellSize = 6
  const gridW = Math.ceil(SIZE / cellSize)
  const gridH = Math.ceil(SIZE / cellSize)

  // Initialize with random cells, weighted toward center circle
  let grid = Array.from({ length: gridH }, (_, y) =>
    Array.from({ length: gridW }, (_, x) => {
      const dx = x - gridW / 2, dy = y - gridH / 2
      const dist = Math.sqrt(dx * dx + dy * dy) / (gridW / 2)
      return Math.random() < (dist < 0.8 ? 0.35 : 0.05) ? 1 : 0
    })
  )

  const frames: Uint8Array[] = []
  const colors = opts.colors ?? ['#00ffcc', '#00aaff', '#ff44cc']

  for (let f = 0; f < opts.frames; f++) {
    clearWithBackground(ctx, '#0a0a12')

    // Draw cells with color based on local density
    for (let y = 0; y < gridH; y++) {
      for (let x = 0; x < gridW; x++) {
        if (!grid[y][x]) continue
        // Count neighbors for color
        let n = 0
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) continue
            const ny = (y + dy + gridH) % gridH
            const nx = (x + dx + gridW) % gridW
            n += grid[ny][nx]
          }
        }
        ctx.fillStyle = colors[Math.min(n, colors.length - 1) % colors.length]
        ctx.fillRect(x * cellSize, y * cellSize, cellSize - 1, cellSize - 1)
      }
    }

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))

    // Step simulation
    const next = grid.map((row) => [...row])
    for (let y = 0; y < gridH; y++) {
      for (let x = 0; x < gridW; x++) {
        let n = 0
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) continue
            n += grid[(y + dy + gridH) % gridH][(x + dx + gridW) % gridW]
          }
        }
        if (grid[y][x]) {
          next[y][x] = n === 2 || n === 3 ? 1 : 0
        } else {
          next[y][x] = n === 3 ? 1 : 0
        }
      }
    }
    grid = next
  }
  return frames
}

// ─── Pattern: Plasma Waves ───

async function generatePlasmaWaves(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const imageData = ctx.createImageData(SIZE, SIZE)
  const frames: Uint8Array[] = []

  for (let f = 0; f < opts.frames; f++) {
    const t = f / opts.fps
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
        data[i] = Math.floor((Math.sin(v * Math.PI) * 0.5 + 0.5) * 120)
        data[i + 1] = Math.floor((Math.sin(v * Math.PI + 2) * 0.5 + 0.5) * 255)
        data[i + 2] = Math.floor((Math.sin(v * Math.PI + 4) * 0.5 + 0.5) * 255)
        data[i + 3] = 255
      }
    }

    ctx.putImageData(imageData, 0, 0)
    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Pattern: Braille Matrix ───

async function generateBrailleMatrix(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  // Braille dot patterns - use Unicode braille characters
  const brailleBase = 0x2800
  const fontSize = 16
  const cols = Math.floor(SIZE / (fontSize * 0.6))
  const rows = Math.floor(SIZE / fontSize)
  const frames: Uint8Array[] = []

  // Wave state
  const phaseGrid = Array.from({ length: rows }, (_, y) =>
    Array.from({ length: cols }, (_, x) => Math.sqrt((x - cols / 2) ** 2 + (y - rows / 2) ** 2))
  )

  for (let f = 0; f < opts.frames; f++) {
    const t = f / opts.fps
    clearWithBackground(ctx, '#000')
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

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Pattern: Circular Progress Bars ───

async function generateCircularProgress(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []

  const ringCount = 5
  const ringWidth = 18
  const gap = 6
  const colors = ['#ff3366', '#ff9933', '#33ff99', '#3399ff', '#cc33ff']

  for (let f = 0; f < opts.frames; f++) {
    const t = f / opts.frames
    clearWithBackground(ctx, '#0a0a14')

    for (let i = 0; i < ringCount; i++) {
      const r = RADIUS - i * (ringWidth + gap) - gap
      if (r < 20) break
      const speed = 0.7 + i * 0.15
      const progress = ((t * speed + i * 0.2) % 1)
      const angle = progress * Math.PI * 2
      const direction = i % 2 === 0 ? 1 : -1

      ctx.beginPath()
      ctx.arc(HALF, HALF, r, -Math.PI / 2, -Math.PI / 2 + angle * direction, direction < 0)
      ctx.strokeStyle = colors[i % colors.length]
      ctx.lineWidth = ringWidth
      ctx.lineCap = 'round'
      ctx.stroke()

      // Glow dot at tip
      const tipAngle = -Math.PI / 2 + angle * direction
      const tx = HALF + Math.cos(tipAngle) * r
      const ty = HALF + Math.sin(tipAngle) * r
      ctx.beginPath()
      ctx.arc(tx, ty, ringWidth / 2 + 2, 0, Math.PI * 2)
      ctx.fillStyle = '#fff'
      ctx.globalAlpha = 0.4
      ctx.fill()
      ctx.globalAlpha = 1
    }

    // Center text
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 36px monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(`${Math.floor(t * 100)}%`, HALF, HALF)

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Pattern: Sci-Fi Radar Sweep ───

async function generateRadarSweep(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []

  // Random "blips" on the radar
  const blips = Array.from({ length: 12 }, () => ({
    angle: Math.random() * Math.PI * 2,
    dist: 30 + Math.random() * (RADIUS - 50),
    size: 3 + Math.random() * 4,
  }))

  for (let f = 0; f < opts.frames; f++) {
    const t = f / opts.fps
    clearWithBackground(ctx, '#001008')

    // Grid rings
    ctx.strokeStyle = 'rgba(0,255,80,0.15)'
    ctx.lineWidth = 1
    for (let r = 40; r < RADIUS; r += 40) {
      ctx.beginPath()
      ctx.arc(HALF, HALF, r, 0, Math.PI * 2)
      ctx.stroke()
    }
    // Cross lines
    for (let a = 0; a < 4; a++) {
      const angle = (a * Math.PI) / 4
      ctx.beginPath()
      ctx.moveTo(HALF + Math.cos(angle) * 20, HALF + Math.sin(angle) * 20)
      ctx.lineTo(HALF + Math.cos(angle) * RADIUS, HALF + Math.sin(angle) * RADIUS)
      ctx.stroke()
    }

    // Sweep beam (gradient arc)
    const sweepAngle = (t * 1.5) % (Math.PI * 2)
    const gradient = ctx.createConicGradient(sweepAngle - Math.PI / 3, HALF, HALF)
    gradient.addColorStop(0, 'rgba(0,255,80,0)')
    gradient.addColorStop(0.08, 'rgba(0,255,80,0.3)')
    gradient.addColorStop(0.1, 'rgba(0,255,80,0.0)')
    gradient.addColorStop(1, 'rgba(0,255,80,0)')
    ctx.fillStyle = gradient
    ctx.beginPath()
    ctx.arc(HALF, HALF, RADIUS, 0, Math.PI * 2)
    ctx.fill()

    // Sweep line
    ctx.beginPath()
    ctx.moveTo(HALF, HALF)
    ctx.lineTo(HALF + Math.cos(sweepAngle) * RADIUS, HALF + Math.sin(sweepAngle) * RADIUS)
    ctx.strokeStyle = 'rgba(0,255,80,0.8)'
    ctx.lineWidth = 2
    ctx.stroke()

    // Blips - light up near sweep
    for (const b of blips) {
      let angleDiff = sweepAngle - b.angle
      while (angleDiff < -Math.PI) angleDiff += Math.PI * 2
      while (angleDiff > Math.PI) angleDiff -= Math.PI * 2
      const brightness = angleDiff > 0 && angleDiff < 1.5 ? Math.max(0, 1 - angleDiff / 1.5) : 0
      if (brightness < 0.05) continue
      ctx.beginPath()
      ctx.arc(HALF + Math.cos(b.angle) * b.dist, HALF + Math.sin(b.angle) * b.dist, b.size, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(0,255,80,${brightness})`
      ctx.fill()
    }

    // Center dot
    ctx.beginPath()
    ctx.arc(HALF, HALF, 4, 0, Math.PI * 2)
    ctx.fillStyle = '#0f6'
    ctx.fill()

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Pattern: Hypnotic Spirals ───

async function generateHypnoticSpirals(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []

  for (let f = 0; f < opts.frames; f++) {
    const t = f / opts.fps
    clearWithBackground(ctx, '#000')

    const arms = 6
    const rotSpeed = t * 0.8
    const colors = ['#ff0066', '#0066ff', '#ffcc00', '#00ff99', '#cc33ff', '#ff6600']

    for (let arm = 0; arm < arms; arm++) {
      const baseAngle = (arm / arms) * Math.PI * 2 + rotSpeed
      ctx.beginPath()
      for (let r = 0; r < RADIUS; r += 1) {
        const twist = r * 0.02 + Math.sin(r * 0.01 + t * 2) * 0.5
        const angle = baseAngle + twist
        const x = HALF + Math.cos(angle) * r
        const y = HALF + Math.sin(angle) * r
        if (r === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.strokeStyle = colors[arm % colors.length]
      ctx.lineWidth = 3
      ctx.globalAlpha = 0.7
      ctx.stroke()
      ctx.globalAlpha = 1
    }

    // Pulsing center
    const pulse = Math.sin(t * 4) * 0.3 + 0.7
    const grad = ctx.createRadialGradient(HALF, HALF, 0, HALF, HALF, 40 * pulse)
    grad.addColorStop(0, 'rgba(255,255,255,0.8)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(HALF, HALF, 40 * pulse, 0, Math.PI * 2)
    ctx.fill()

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Pattern: Digital Circuit ───

async function generateDigitalCircuit(opts: PatternOptions): Promise<Uint8Array[]> {
  const [canvas, ctx] = createCanvas()
  const frames: Uint8Array[] = []

  // Pre-generate circuit paths
  const pathCount = 30
  const paths: { points: [number, number][]; speed: number; color: string }[] = []
  const circuitColors = ['#0ff', '#0af', '#f0f', '#0f6', '#fa0']

  for (let i = 0; i < pathCount; i++) {
    const points: [number, number][] = []
    let x = Math.random() * SIZE, y = Math.random() * SIZE
    points.push([x, y])
    for (let s = 0; s < 8; s++) {
      const dir = Math.floor(Math.random() * 4) // 0=right 1=down 2=left 3=up
      const len = 20 + Math.random() * 60
      if (dir === 0) x += len
      else if (dir === 1) y += len
      else if (dir === 2) x -= len
      else y -= len
      x = Math.max(0, Math.min(SIZE, x))
      y = Math.max(0, Math.min(SIZE, y))
      points.push([x, y])
    }
    paths.push({
      points,
      speed: 0.3 + Math.random() * 0.7,
      color: circuitColors[i % circuitColors.length],
    })
  }

  for (let f = 0; f < opts.frames; f++) {
    const t = f / opts.fps
    clearWithBackground(ctx, '#050510')

    // Draw dim traces
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

    // Animated pulses along paths
    for (const p of paths) {
      const totalLen = p.points.reduce((s, pt, i) => {
        if (i === 0) return 0
        const dx = pt[0] - p.points[i - 1][0], dy = pt[1] - p.points[i - 1][1]
        return s + Math.sqrt(dx * dx + dy * dy)
      }, 0)
      const pos = ((t * p.speed * 80) % (totalLen + 40)) - 20

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
          ctx.arc(px, py, 3, 0, Math.PI * 2)
          ctx.fillStyle = '#fff'
          ctx.fill()
          // Glow
          const glow = ctx.createRadialGradient(px, py, 0, px, py, 12)
          glow.addColorStop(0, p.color)
          glow.addColorStop(1, 'transparent')
          ctx.fillStyle = glow
          ctx.globalAlpha = 0.5
          ctx.beginPath()
          ctx.arc(px, py, 12, 0, Math.PI * 2)
          ctx.fill()
          ctx.globalAlpha = 1
          break
        }
        acc += segLen
      }

      // Junction nodes
      for (const pt of p.points) {
        ctx.beginPath()
        ctx.arc(pt[0], pt[1], 2, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(100,200,255,0.3)'
        ctx.fill()
      }
    }

    applyCircularMask(ctx)
    frames.push(await canvasToJpeg(canvas))
  }
  return frames
}

// ─── Registry ───

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
]
