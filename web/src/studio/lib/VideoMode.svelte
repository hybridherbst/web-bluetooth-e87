<script lang="ts">
  /**
   * Video upload mode — file picker, trim/zoom controls, fps, preview.
   */
  import { formatBytes } from '../../lib/utils'
  import { MAX_UPLOAD_BYTES } from '../../lib/image-processing'

  interface Props {
    isWriting: boolean
    selectedFile: File | null
    videoFps: number
    videoTrimStart: number
    videoTrimEnd: number
    videoDuration: number
    onSelectVideo: (event: Event) => void
    onScrubStart?: () => void
    onScrubFrame?: (time: number) => void
    onScrubEnd?: () => void
  }

  let {
    isWriting, selectedFile,
    videoFps = $bindable(),
    videoTrimStart = $bindable(),
    videoTrimEnd = $bindable(),
    videoDuration,
    onSelectVideo,
    onScrubStart,
    onScrubFrame,
    onScrubEnd,
  }: Props = $props()

  const MAX_CLIP_SECONDS = 10

  $effect(() => {
    if (videoDuration <= 0) return

    videoTrimStart = Math.max(0, Math.min(videoDuration, videoTrimStart))
    videoTrimEnd = Math.max(0, Math.min(videoDuration, videoTrimEnd))

    if (videoTrimEnd < videoTrimStart) {
      videoTrimEnd = videoTrimStart
    }

    if (videoTrimEnd - videoTrimStart > MAX_CLIP_SECONDS) {
      videoTrimEnd = Math.min(videoDuration, videoTrimStart + MAX_CLIP_SECONDS)
    }
  })

  function handleStartInput(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value)
    videoTrimStart = Math.max(0, Math.min(videoDuration, value))

    if (videoTrimStart > videoTrimEnd) {
      videoTrimEnd = videoTrimStart
    }
    if (videoTrimEnd - videoTrimStart > MAX_CLIP_SECONDS) {
      videoTrimEnd = Math.min(videoDuration, videoTrimStart + MAX_CLIP_SECONDS)
    }

    onScrubFrame?.(videoTrimStart)
  }

  function handleEndInput(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value)
    videoTrimEnd = Math.max(0, Math.min(videoDuration, value))

    if (videoTrimEnd < videoTrimStart) {
      videoTrimStart = videoTrimEnd
    }
    if (videoTrimEnd - videoTrimStart > MAX_CLIP_SECONDS) {
      videoTrimStart = Math.max(0, videoTrimEnd - MAX_CLIP_SECONDS)
    }

    onScrubFrame?.(videoTrimEnd)
  }

  function handleScrubStart(): void {
    onScrubStart?.()
  }

  function handleScrubEnd(): void {
    onScrubEnd?.()
  }

  function estimatedFrames(): number {
    return Math.ceil(Math.max(0, videoTrimEnd - videoTrimStart) * videoFps)
  }

  function estimatedSize(): number {
    return estimatedFrames() * 8000 + 6000
  }

</script>

<div class="image-source">
  <label class="file-btn" class:active={selectedFile !== null}>
    Выбрать видео…
    <input type="file" accept="video/*" onchange={onSelectVideo} disabled={isWriting} style="display:none" />
  </label>
  {#if selectedFile}
    <span class="dim" style="margin-left:0.5rem">{selectedFile.name}</span>
  {/if}
</div>

{#if selectedFile && videoDuration > 0}
  <div class="trim-controls">
    <h3>Фрагмент и частота кадров</h3>
    <div class="settings trim-row">
      <label>
        <span>Начало ({videoTrimStart.toFixed(1)}с)</span>
        <input
          type="range"
          min="0"
          max={videoDuration}
          step="0.05"
          bind:value={videoTrimStart}
          disabled={isWriting}
          onpointerdown={handleScrubStart}
          onpointerup={handleScrubEnd}
          onpointercancel={handleScrubEnd}
          oninput={handleStartInput}
          onchange={handleScrubEnd}
          style="width:100%"
        />
      </label>
      <label>
        <span>Конец ({videoTrimEnd.toFixed(1)}с)</span>
        <input
          type="range"
          min="0"
          max={videoDuration}
          step="0.05"
          bind:value={videoTrimEnd}
          disabled={isWriting}
          onpointerdown={handleScrubStart}
          onpointerup={handleScrubEnd}
          onpointercancel={handleScrubEnd}
          oninput={handleEndInput}
          onchange={handleScrubEnd}
          style="width:100%"
        />
      </label>
    </div>
    <p class="dim" style="font-size:0.8rem;margin:0.1rem 0">
      Длительность: {(Math.max(0, videoTrimEnd - videoTrimStart)).toFixed(1)}с
      / {MAX_CLIP_SECONDS.toFixed(0)}с максимум
      — ~{estimatedFrames()} кадров
      — примерно {formatBytes(estimatedSize())}
      {#if estimatedSize() > MAX_UPLOAD_BYTES}
        <span style="color:#ff6666"> ⚠ больше лимита {formatBytes(MAX_UPLOAD_BYTES)}</span>
      {/if}
    </p>
    <div class="settings">
      <label>
        <span>Кадров в секунду (fps)</span>
        <input type="number" min="1" max="30" step="1" bind:value={videoFps} disabled={isWriting} />
      </label>
    </div>
  </div>
{/if}

<style>
  .dim { font-weight: 400; color: #9da99e; }
  h3 { margin: 0.6rem 0 0.3rem; font-size: 0.9rem; color: #c4d4c1; }
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .trim-row { gap: 0.8rem; }
  .trim-row label {
    flex: 1 1 calc(50% - 0.4rem);
    max-width: calc(50% - 0.4rem);
    min-width: 0;
  }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #d4d4d4; font-family: inherit; text-transform: none; letter-spacing: 0; font-size: 0.75rem; }
  .file-btn {
    display: inline-flex; align-items: center;
    border-radius: 10px; border: 1px solid #303830;
    background: #101511; color: #eef3e9;
    padding: 0.5rem 0.7rem; cursor: pointer; font-weight: 600; font-size: 0.9rem;
    transition: border-color 130ms ease, background-color 130ms ease;
  }
  .file-btn:hover { border-color: #c0ee91; background: rgba(192, 238, 145, 0.12); }
  .active {
    border-color: #c0ee91;
    background: rgba(192, 238, 145, 0.2);
  }
  .trim-controls {
    background: #141a16;
    border: 1px solid #303830;
    border-radius: 10px;
    padding: 0.6rem;
    margin: 0.5rem 0;
  }
  input[type="range"] { background: transparent; border: none; padding: 0; }
</style>
