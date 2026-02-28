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
</style>
