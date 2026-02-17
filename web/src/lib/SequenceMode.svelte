<script lang="ts">
  /**
   * Image sequence upload mode — multi-file picker, fps, generate preview.
   */

  interface Props {
    isWriting: boolean
    isGeneratingPreview: boolean
    selectedFiles: File[]
    sequenceFps: number
    onSelectFiles: (event: Event) => void
    onGeneratePreview: () => void
  }

  let {
    isWriting, isGeneratingPreview, selectedFiles,
    sequenceFps = $bindable(), onSelectFiles, onGeneratePreview,
  }: Props = $props()

  let lastAutoPreviewSignature = $state('')

  const AUTO_PREVIEW_DEBOUNCE_MS = 250

  $effect(() => {
    if (selectedFiles.length === 0) return
    if (isWriting || isGeneratingPreview) return

    const filesSignature = selectedFiles
      .map((f) => `${f.name}:${f.size}:${f.lastModified}`)
      .join(',')
    const signature = `${filesSignature}|fps:${sequenceFps}`

    if (signature === lastAutoPreviewSignature) return

    const timeout = setTimeout(() => {
      lastAutoPreviewSignature = signature
      onGeneratePreview()
    }, AUTO_PREVIEW_DEBOUNCE_MS)

    return () => clearTimeout(timeout)
  })
</script>

<div class="image-source">
  <label class="file-btn" class:active={selectedFiles.length > 0}>
    Select images…
    <input type="file" accept="image/*" multiple onchange={onSelectFiles} disabled={isWriting} style="display:none" />
  </label>
  {#if selectedFiles.length > 0}
    <span class="dim" style="margin-left:0.5rem">{selectedFiles.length} images selected</span>
  {/if}
</div>

<div class="settings">
  <label>
    <span>Display time per image (fps)</span>
    <input type="number" min="1" max="30" step="1" bind:value={sequenceFps} disabled={isWriting} />
  </label>
</div>
<p class="dim" style="font-size:0.8rem;margin:0.2rem 0">
  {#if sequenceFps === 1}Each image shows for 1 second
  {:else}Each image shows for {(1/sequenceFps).toFixed(2)}s ({sequenceFps} fps)
  {/if}
</p>

{#if selectedFiles.length > 0}
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
</style>
