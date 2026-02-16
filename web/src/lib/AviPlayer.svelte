<script lang="ts">
  /**
   * AVI preview player with circular mask, play/pause, and frame counter.
   */

  interface Props {
    frames: ImageBitmap[]
    fps: number
    /** Callback when user stops preview */
    onstop?: () => void
  }

  let { frames, fps, onstop }: Props = $props()

  let canvas: HTMLCanvasElement | null = $state(null)
  let playing = $state(false)
  let currentFrame = $state(0)
  let animId: number | null = null

  function drawFrame(idx: number) {
    if (!canvas || frames.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const frame = frames[Math.min(idx, frames.length - 1)]
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(frame, 0, 0, canvas.width, canvas.height)
    // Circular mask
    ctx.save()
    ctx.globalCompositeOperation = 'destination-in'
    ctx.beginPath()
    ctx.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2 - 1, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
    // Border
    ctx.strokeStyle = 'rgba(255,255,255,0.2)'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(canvas.width / 2, canvas.height / 2, canvas.width / 2 - 1, 0, Math.PI * 2)
    ctx.stroke()
  }

  function play() {
    if (frames.length === 0) return
    playing = true
    currentFrame = 0
    let lastTime = 0
    const msPerFrame = 1000 / fps

    const loop = (time: number) => {
      if (!playing) return
      if (time - lastTime >= msPerFrame) {
        drawFrame(currentFrame)
        currentFrame = (currentFrame + 1) % frames.length
        lastTime = time
      }
      animId = requestAnimationFrame(loop)
    }
    animId = requestAnimationFrame(loop)
  }

  export function stop() {
    playing = false
    if (animId !== null) {
      cancelAnimationFrame(animId)
      animId = null
    }
    onstop?.()
  }

  function toggle() {
    if (playing) {
      stop()
    } else {
      play()
    }
  }

  /** Start playback and draw first frame. Called by parent after frames change. */
  export function startPreview() {
    if (frames.length === 0) return
    stop()
    // Wait a tick for canvas to bind
    requestAnimationFrame(() => {
      drawFrame(0)
      play()
    })
  }
</script>

{#if frames.length > 0}
  <div class="avi-preview">
    <canvas
      bind:this={canvas}
      width={200}
      height={200}
      class="avi-canvas"
    ></canvas>
    <div class="avi-controls">
      <button class="small" onclick={toggle}>
        {playing ? '⏸' : '▶'}
      </button>
      <span class="dim" style="font-size:0.8rem">
        {currentFrame + 1}/{frames.length} @ {fps}fps
      </span>
    </div>
  </div>
{/if}

<style>
  .avi-preview {
    margin: 0.8rem 0;
    display: flex; flex-direction: column; align-items: center; gap: 0.4rem;
  }
  .avi-canvas {
    border-radius: 50%;
    border: 2px solid rgba(129, 178, 255, 0.4);
    background: #000;
  }
  .avi-controls {
    display: flex; align-items: center; gap: 0.5rem;
  }
  .small { padding: 0.3rem 0.5rem; font-size: 0.85rem; }
  .dim { font-weight: 400; color: #7a9dc5; }
</style>
