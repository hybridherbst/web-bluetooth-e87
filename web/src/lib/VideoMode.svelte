<script lang="ts">
  /**
   * Video upload mode — file picker, trim/zoom controls, fps, preview.
   */
  import { formatBytes } from './utils'
  import { MAX_UPLOAD_BYTES } from './image-processing'

  interface Props {
    isWriting: boolean
    isGeneratingPreview: boolean
    selectedFile: File | null
    useDefaultImage: boolean
    previewUrl: string | null
    videoFps: number
    videoTrimStart: number
    videoTrimEnd: number
    videoDuration: number
    videoZoom: number
    videoZoomX: number
    videoZoomY: number
    onSelectVideo: (event: Event) => void
    onGeneratePreview: () => void
  }

  let {
    isWriting, isGeneratingPreview, selectedFile, useDefaultImage, previewUrl,
    videoFps = $bindable(),
    videoTrimStart = $bindable(),
    videoTrimEnd = $bindable(),
    videoDuration,
    videoZoom = $bindable(),
    videoZoomX = $bindable(),
    videoZoomY = $bindable(),
    onSelectVideo, onGeneratePreview,
  }: Props = $props()

  $effect(() => {
    // clamp trim start < trim end
    if (videoTrimStart >= videoTrimEnd && videoDuration > 0) {
      videoTrimStart = Math.max(0, videoTrimEnd - 0.1)
    }
  })

  function estimatedFrames(): number {
    return Math.ceil(Math.max(0, videoTrimEnd - videoTrimStart) * videoFps)
  }

  function estimatedSize(): number {
    return estimatedFrames() * 8000 + 6000
  }
</script>

<div class="image-source">
  <label class="file-btn" class:active={selectedFile !== null && !useDefaultImage}>
    Select video…
    <input type="file" accept="video/*" onchange={onSelectVideo} disabled={isWriting} style="display:none" />
  </label>
  {#if selectedFile && !useDefaultImage}
    <span class="dim" style="margin-left:0.5rem">{selectedFile.name}</span>
  {/if}
</div>

{#if selectedFile && !useDefaultImage && videoDuration > 0}
  {#if previewUrl}
    <div class="preview">
      <!-- svelte-ignore a11y_media_has_caption -->
      <video src={previewUrl} style="max-width:200px;max-height:200px;border:1px solid #334;border-radius:6px" controls muted></video>
    </div>
  {/if}

  <div class="trim-controls">
    <h3>Trim & Zoom</h3>
    <div class="settings">
      <label>
        <span>Start ({videoTrimStart.toFixed(1)}s)</span>
        <input type="range" min="0" max={videoDuration} step="0.1" bind:value={videoTrimStart} disabled={isWriting} style="width:140px" />
      </label>
      <label>
        <span>End ({videoTrimEnd.toFixed(1)}s)</span>
        <input type="range" min="0" max={videoDuration} step="0.1" bind:value={videoTrimEnd} disabled={isWriting} style="width:140px" />
      </label>
    </div>
    <p class="dim" style="font-size:0.8rem;margin:0.1rem 0">
      Duration: {(Math.max(0, videoTrimEnd - videoTrimStart)).toFixed(1)}s
      — ~{estimatedFrames()} frames
      — est. {formatBytes(estimatedSize())}
      {#if estimatedSize() > MAX_UPLOAD_BYTES}
        <span style="color:#ff6666"> ⚠ over {formatBytes(MAX_UPLOAD_BYTES)} limit!</span>
      {/if}
    </p>
    <div class="settings">
      <label>
        <span>Zoom ({videoZoom.toFixed(1)}x)</span>
        <input type="range" min="1" max="4" step="0.1" bind:value={videoZoom} disabled={isWriting} style="width:120px" />
      </label>
      <label>
        <span>Pan X</span>
        <input type="range" min="0" max="1" step="0.01" bind:value={videoZoomX} disabled={isWriting} style="width:100px" />
      </label>
      <label>
        <span>Pan Y</span>
        <input type="range" min="0" max="1" step="0.01" bind:value={videoZoomY} disabled={isWriting} style="width:100px" />
      </label>
    </div>
    <div class="settings">
      <label>
        <span>Frame rate (fps)</span>
        <input type="number" min="1" max="30" step="1" bind:value={videoFps} disabled={isWriting} />
      </label>
    </div>
  </div>

  <div class="row buttons" style="margin-top:0.5rem">
    <button onclick={onGeneratePreview} disabled={isWriting || isGeneratingPreview}>
      {isGeneratingPreview ? 'Generating…' : '▶ Preview AVI'}
    </button>
  </div>
{/if}

<style>
  .row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.6rem; }
  .dim { font-weight: 400; color: #7a9dc5; }
  h3 { margin: 0.6rem 0 0.3rem; font-size: 0.9rem; color: #8badd4; }
  .preview { margin: 0.5rem 0; }
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #b0cce8; }
  .file-btn {
    display: inline-flex; align-items: center;
    border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.07); color: #f3f9ff;
    padding: 0.5rem 0.7rem; cursor: pointer; font-weight: 600; font-size: 0.9rem;
  }
  .file-btn:hover { border-color: rgba(129, 178, 255, 0.9); }
  .active {
    border-color: rgba(129, 178, 255, 0.9);
    background: rgba(129, 178, 255, 0.14);
  }
  .trim-controls {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 0.6rem;
    margin: 0.5rem 0;
  }
  input[type="range"] { background: transparent; border: none; padding: 0; }
</style>
