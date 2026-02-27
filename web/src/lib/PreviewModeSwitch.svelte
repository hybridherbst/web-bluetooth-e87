<script lang="ts">
  interface Props {
    mode: 'live' | 'preview'
    disabled?: boolean
  }

  let {
    mode = $bindable(),
    disabled = false,
  }: Props = $props()
</script>

<div class="mode-switch" aria-label="Preview mode" role="radiogroup">
  <button
    type="button"
    role="radio"
    aria-checked={mode === 'live'}
    class:active={mode === 'live'}
    onclick={() => (mode = 'live')}
    disabled={disabled}
  >Live</button>
  <button
    type="button"
    role="radio"
    aria-checked={mode === 'preview'}
    class:active={mode === 'preview'}
    onclick={() => (mode = 'preview')}
    disabled={disabled}
  >Preview</button>
</div>

<style>
  .mode-switch {
    display: inline-flex;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.18);
    background: rgba(255,255,255,0.05);
    padding: 3px;
    gap: 3px;
  }
  .mode-switch button {
    border-radius: 999px;
    border: none;
    background: transparent;
    color: #d8e9ff;
    padding: 0.35rem 0.75rem;
    font-size: 0.82rem;
    font-weight: 700;
  }
  .mode-switch button.active {
    background: linear-gradient(180deg, rgba(181, 210, 255, 0.3), rgba(129, 178, 255, 0.3));
    color: #f7fbff;
  }
</style>
