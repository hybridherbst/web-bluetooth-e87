<script lang="ts">
  /**
   * Single image upload mode — file picker + preview.
   */

  interface Props {
    isWriting: boolean
    selectedFile: File | null
    backdropColor: string
    onSelectFile: (event: Event) => void
  }

  let { isWriting, selectedFile, backdropColor = $bindable(), onSelectFile }: Props = $props()
</script>

<div class="image-source">
  <div class="row buttons" style="margin-bottom:0.5rem">
    <label class="file-btn">
      Choose image…
      <input type="file" accept="image/*" onchange={onSelectFile} disabled={isWriting} style="display:none" />
    </label>
    {#if selectedFile}
      <span class="dim">{selectedFile.name}</span>
    {/if}
  </div>
</div>

<div class="settings">
  <label>
    <span>Backdrop color</span>
    <input type="color" bind:value={backdropColor} disabled={isWriting} />
  </label>
</div>

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
</style>
