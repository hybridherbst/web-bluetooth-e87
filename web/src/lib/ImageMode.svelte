<script lang="ts">
  /**
   * Single image upload mode — file picker + preview.
   */

  interface Props {
    isWriting: boolean
    previewUrl: string | null
    onSelectFile: (event: Event) => void
  }

  let { isWriting, previewUrl, onSelectFile }: Props = $props()
</script>

<div class="image-source">
  <div class="row buttons" style="margin-bottom:0.5rem">
    <label class="file-btn">
      Choose image…
      <input type="file" accept="image/*" onchange={onSelectFile} disabled={isWriting} style="display:none" />
    </label>
  </div>
</div>
{#if previewUrl}
  <div class="preview">
    <img src={previewUrl} alt="Preview" />
  </div>
{/if}

<style>
  .row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.6rem; }
  .preview { margin: 0.5rem 0; }
  .preview img { max-width: 180px; max-height: 180px; border: 1px solid #334; border-radius: 6px; }
  .file-btn {
    display: inline-flex; align-items: center;
    border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.07); color: #f3f9ff;
    padding: 0.5rem 0.7rem; cursor: pointer; font-weight: 600; font-size: 0.9rem;
  }
  .file-btn:hover { border-color: rgba(129, 178, 255, 0.9); }
</style>
