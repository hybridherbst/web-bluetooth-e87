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
    border: 1px solid #2a2a2a;
    background: #111;
    padding: 3px;
    gap: 3px;
  }
  .mode-switch button {
    border-radius: 999px;
    border: none;
    background: transparent;
    color: #d4d4d4;
    padding: 0.35rem 0.75rem;
    font-size: 0.82rem;
    font-weight: 700;
    transition: background 130ms ease, color 130ms ease;
  }
  .mode-switch button:hover { background: rgba(63, 210, 251, 0.14); color: #fff; }
  .mode-switch button.active {
    background: rgba(63, 210, 251, 0.2);
    color: #3fd2fb;
  }
</style>
