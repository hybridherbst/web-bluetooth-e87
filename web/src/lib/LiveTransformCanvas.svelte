<script lang="ts">
  interface Props {
    frames: ImageBitmap[]
    fps: number
    disabled?: boolean
    backdropColor?: string
    scale: number
    panX: number
    panY: number
  }

  let {
    frames,
    fps,
    disabled = false,
    backdropColor = '#000000',
    scale = $bindable(),
    panX = $bindable(),
    panY = $bindable(),
  }: Props = $props()

  let canvas: HTMLCanvasElement | null = $state(null)
  let frameIndex = $state(0)
  let isPlaying = $state(true)
  let dragging = $state(false)
  let dragStartX = $state(0)
  let dragStartY = $state(0)
  let dragStartPanX = $state(0)
  let dragStartPanY = $state(0)
  let animId: number | null = null
  let playIndex = 0

  const CANVAS_SIZE = 220

  function clamp(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value))
  }

  function drawFrame(idx: number): void {
    if (!canvas || frames.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const frame = frames[Math.min(idx, frames.length - 1)]
    const drawW = canvas.width * scale
    const drawH = canvas.height * scale
    const dx = (canvas.width - drawW) / 2 + panX * (canvas.width / 2)
    const dy = (canvas.height - drawH) / 2 + panY * (canvas.height / 2)

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = backdropColor
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(frame, dx, dy, drawW, drawH)

    ctx.save()
    ctx.globalCompositeOperation = 'destination-in'
    ctx.beginPath()
    ctx.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2 - 1, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    ctx.strokeStyle = 'rgba(142, 163, 198, 0.45)'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2 - 1, 0, Math.PI * 2)
    ctx.stroke()
  }

  function stopAnimation(): void {
    if (animId !== null) {
      cancelAnimationFrame(animId)
      animId = null
    }
  }

  function startAnimation(): void {
    stopAnimation()
    if (frames.length <= 1 || !isPlaying) {
      drawFrame(frameIndex)
      return
    }

    let lastTime = 0
    const msPerFrame = 1000 / Math.max(1, fps)
    playIndex = Math.min(frameIndex, Math.max(0, frames.length - 1))

    const loop = (time: number) => {
      if (!isPlaying) return
      if (time - lastTime >= msPerFrame) {
        frameIndex = playIndex
        drawFrame(playIndex)
        playIndex = (playIndex + 1) % frames.length
        lastTime = time
      }
      animId = requestAnimationFrame(loop)
    }

    animId = requestAnimationFrame(loop)
  }

  function resetTransform(): void {
    scale = 1
    panX = 0
    panY = 0
    drawFrame(frameIndex)
  }

  function togglePlayback(): void {
    isPlaying = !isPlaying
    if (isPlaying) {
      startAnimation()
    } else {
      stopAnimation()
      drawFrame(frameIndex)
    }
  }

  function onPointerDown(event: PointerEvent): void {
    if (!canvas || disabled || frames.length === 0) return
    dragging = true
    dragStartX = event.clientX
    dragStartY = event.clientY
    dragStartPanX = panX
    dragStartPanY = panY
    canvas.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: PointerEvent): void {
    if (!dragging || !canvas) return
    const dx = (event.clientX - dragStartX) / (canvas.width / 2)
    const dy = (event.clientY - dragStartY) / (canvas.height / 2)
    panX = clamp(dragStartPanX + dx, -1.5, 1.5)
    panY = clamp(dragStartPanY + dy, -1.5, 1.5)
    drawFrame(frameIndex)
  }

  function onPointerUp(event: PointerEvent): void {
    if (!canvas) return
    dragging = false
    if (canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId)
    }
  }

  function onWheel(event: WheelEvent): void {
    if (disabled || frames.length === 0) return
    event.preventDefault()
    const direction = event.deltaY > 0 ? -1 : 1
    scale = clamp(scale + direction * 0.08, 0.5, 4)
    drawFrame(frameIndex)
  }

  $effect(() => {
    if (frames.length === 0) {
      stopAnimation()
      return
    }

    if (frameIndex < 0 || frameIndex >= frames.length) frameIndex = 0
    drawFrame(frameIndex)
    startAnimation()

    return () => stopAnimation()
  })
</script>

<div class="live-preview">
  <canvas
    bind:this={canvas}
    width={CANVAS_SIZE}
    height={CANVAS_SIZE}
    class="canvas"
    onpointerdown={onPointerDown}
    onpointermove={onPointerMove}
    onpointerup={onPointerUp}
    onpointercancel={onPointerUp}
    onwheel={onWheel}
  ></canvas>

  <div class="controls">
    {#if frames.length > 1}
      <button class="small" onclick={togglePlayback} disabled={disabled}>
        {isPlaying ? '⏸' : '▶'}
      </button>
      <span class="dim">{frameIndex + 1}/{frames.length} @ {fps}fps</span>
    {/if}
    <button class="small" onclick={resetTransform} disabled={disabled}>Reset</button>
  </div>
</div>

<style>
  .live-preview {
    margin: 0.8rem 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.45rem;
  }
  .canvas {
    border-radius: 50%;
    border: 2px solid rgba(142, 163, 198, 0.45);
    background: #000;
    touch-action: none;
    cursor: grab;
  }
  .canvas:active { cursor: grabbing; }
  .controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }
  .small { padding: 0.3rem 0.5rem; font-size: 0.85rem; }
  .dim { color: #9ba1ad; font-size: 0.8rem; }
</style>
