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

<div class="source-controls">
<div class="image-source">
  <div class="row buttons" style="margin-bottom:0.5rem">
    <label class="file-btn">
      Выбрать изображение…
      <input type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,.gif" onchange={onSelectFile} disabled={isWriting} style="display:none" />
    </label>
    {#if selectedFile}
      <span class="dim">{selectedFile.name}</span>
    {/if}
  </div>
</div>

<div class="settings">
  <label>
    <span>Цвет фона</span>
    <input type="color" bind:value={backdropColor} disabled={isWriting} />
  </label>
</div>

</div>

<style>
  .row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.6rem; }
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
</style>
