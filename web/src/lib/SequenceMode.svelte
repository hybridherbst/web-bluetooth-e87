<script lang="ts">
  /**
   * Image sequence upload mode — multi-file picker, fps, generate preview.
   * Supports animated sources (GIF, animated WebP): when any selected file
   * is an animation, frameInfo reports its unpacked frame count.
   */
  import type { ExpandedFileFrames } from './image-processing'

  interface Props {
    isWriting: boolean
    selectedFiles: File[]
    /** Per-file expansion info (animations report frame count), from App.svelte. */
    frameInfo?: ExpandedFileFrames[]
    sequenceFps: number
    onSelectFiles: (event: Event) => void
  }

  let {
    isWriting, selectedFiles,
    frameInfo = [],
    sequenceFps = $bindable(), onSelectFiles,
  }: Props = $props()

  function pluralize(n: number, one: string, many: string): string {
    return `${n} ${n === 1 ? one : many}`
  }

  const summary = $derived.by(() => {
    if (selectedFiles.length === 0) return ''
    if (frameInfo.length === 0) {
      return pluralize(selectedFiles.length, 'file', 'files') + ' selected'
    }

    let animCount = 0
    let stillCount = 0
    let totalFrames = 0
    for (const e of frameInfo) {
      if (e.fromAnimation) animCount++
      else stillCount++
      totalFrames += e.bitmaps.length
    }

    if (animCount === 0) return pluralize(stillCount, 'image', 'images') + ' selected'

    const parts: string[] = []
    parts.push(pluralize(animCount, 'animation', 'animations'))
    if (stillCount > 0) parts.push(pluralize(stillCount, 'still', 'stills'))
    return `${parts.join(' + ')} — ${totalFrames} frame${totalFrames === 1 ? '' : 's'} total`
  })
</script>

<div class="image-source">
  <label class="file-btn" class:active={selectedFiles.length > 0}>
    Select images…
    <input type="file" accept="image/*" multiple onchange={onSelectFiles} disabled={isWriting} style="display:none" />
  </label>
  <span class="hint" title="GIFs and animated WebP files expand into their frames automatically">
    supports GIFs
  </span>
  {#if selectedFiles.length > 0}
    <span class="dim" style="margin-left:0.5rem">{summary}</span>
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

<style>
  .dim { font-weight: 400; color: #9ba1ad; }
  .hint {
    margin-left: 0.5rem;
    font-size: 0.72rem;
    color: #6a7380;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    text-transform: uppercase;
    letter-spacing: -0.05em;
    padding: 0.15rem 0.35rem;
    border: 1px dashed #3a4150;
    border-radius: 2px;
  }
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #d4d4d4; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-transform: uppercase; letter-spacing: -0.08em; font-size: 0.75rem; }
  .file-btn {
    display: inline-flex; align-items: center;
    border-radius: 2px; border: 1px solid #2a2a2a;
    background: #000; color: #f5f5f5;
    padding: 0.5rem 0.7rem; cursor: pointer; font-weight: 600; font-size: 0.9rem;
    transition: border-color 130ms ease, background-color 130ms ease;
  }
  .file-btn:hover { border-color: #3fd2fb; background: rgba(63, 210, 251, 0.12); }
  .active {
    border-color: #3fd2fb;
    background: rgba(63, 210, 251, 0.2);
  }
</style>
