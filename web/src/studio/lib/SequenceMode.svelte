<script lang="ts">
  /**
   * Image sequence upload mode — multi-file picker, fps, generate preview.
   */

  interface Props {
    isWriting: boolean
    selectedFiles: File[]
    sequenceFps: number
    onSelectFiles: (event: Event) => void
  }

  let {
    isWriting, selectedFiles,
    sequenceFps = $bindable(), onSelectFiles,
  }: Props = $props()
</script>

<div class="image-source">
  <label class="file-btn" class:active={selectedFiles.length > 0}>
    Выбрать кадры…
    <input type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,.gif" multiple onchange={onSelectFiles} disabled={isWriting} style="display:none" />
  </label>
  {#if selectedFiles.length > 0}
    <span class="dim" style="margin-left:0.5rem">{selectedFiles.length} кадров выбрано</span>
  {/if}
</div>

<div class="settings">
  <label>
    <span>Кадров в секунду (fps)</span>
    <input type="number" min="1" max="30" step="1" bind:value={sequenceFps} disabled={isWriting} />
  </label>
</div>
<p class="dim" style="font-size:0.8rem;margin:0.2rem 0">
  {#if sequenceFps === 1}Каждый кадр — 1 секунда
  {:else}Длительность кадра — {(1/sequenceFps).toFixed(2)}s ({sequenceFps} fps)
  {/if}
</p>

<style>
  .dim { font-weight: 400; color: #9da99e; }
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
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
</style>
