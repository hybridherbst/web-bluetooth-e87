<script lang="ts">
  /**
   * Image sequence upload mode — multi-file picker, fps, generate preview.
   */

  interface Props {
    isWriting: boolean
    selectedFiles: File[]
    sequenceSeconds: number
    onSelectFiles: (event: Event) => void
  }

  let {
    isWriting, selectedFiles,
    sequenceSeconds = $bindable(), onSelectFiles,
  }: Props = $props()
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
    <span>Display time per image (seconds)</span>
    <input type="number" min="0.03" max="60" step="0.1" bind:value={sequenceSeconds} disabled={isWriting} />
  </label>
</div>
<p class="dim" style="font-size:0.8rem;margin:0.2rem 0">
  {#if sequenceSeconds > 0}Each image shows for {sequenceSeconds} second{sequenceSeconds === 1 ? '' : 's'} ({(1 / sequenceSeconds).toFixed(2)} fps)
  {:else}Enter a time greater than zero.
  {/if}
</p>

<style>
  .dim { font-weight: 400; color: #9ba1ad; }
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
