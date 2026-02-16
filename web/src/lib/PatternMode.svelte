<script lang="ts">
  /**
   * Pattern generator mode — grid of pattern cards, frames/fps settings,
   * Apple-style Still / Video toggle, preview.
   */
  import { PATTERNS, type PatternDef } from '../pattern-generators'
  import { formatBytes } from './utils'
  import { MAX_UPLOAD_BYTES } from './image-processing'

  interface Props {
    isWriting: boolean
    isGeneratingPreview: boolean
    isGeneratingPattern: boolean
    selectedPattern: PatternDef | null
    patternFrameCount: number
    patternFps: number
    onSelectPattern: (pat: PatternDef) => void
    onGeneratePreview: () => void
    onGenerateStill: () => void
  }

  let {
    isWriting, isGeneratingPreview, isGeneratingPattern,
    selectedPattern,
    patternFrameCount = $bindable(),
    patternFps = $bindable(),
    onSelectPattern, onGeneratePreview, onGenerateStill,
  }: Props = $props()

  let outputMode: 'still' | 'video' = $state('video')

  function estimatedSize(): number {
    return patternFrameCount * 8000 + 6000
  }

  function handleGenerate() {
    if (outputMode === 'still') {
      onGenerateStill()
    } else {
      onGeneratePreview()
    }
  }
</script>

<div class="pattern-grid">
  {#each PATTERNS as pat}
    <button
      class="pattern-card"
      class:active={selectedPattern?.id === pat.id}
      onclick={() => onSelectPattern(pat)}
      disabled={isWriting}
    >
      <span class="pattern-icon">{pat.icon}</span>
      <span class="pattern-name">{pat.name}</span>
      <span class="pattern-desc">{pat.description}</span>
    </button>
  {/each}
</div>

{#if selectedPattern}
  {#if outputMode === 'video'}
    <div class="settings" style="margin-top:0.6rem">
      <label>
        <span>Frames</span>
        <input type="number" min="10" max="300" step="10" bind:value={patternFrameCount} disabled={isWriting} />
      </label>
      <label>
        <span>FPS</span>
        <input type="number" min="1" max="30" step="1" bind:value={patternFps} disabled={isWriting} />
      </label>
    </div>
    <p class="dim" style="font-size:0.8rem;margin:0.2rem 0">
      Duration: {(patternFrameCount / patternFps).toFixed(1)}s — est. {formatBytes(estimatedSize())}
      {#if estimatedSize() > MAX_UPLOAD_BYTES}
        <span style="color:#ff6666"> ⚠ may exceed limit</span>
      {/if}
    </p>
  {:else}
    <p class="dim" style="font-size:0.8rem;margin:0.6rem 0 0.2rem">
      Generates a single representative frame from the pattern.
    </p>
  {/if}

  <div class="row buttons">
    <button onclick={handleGenerate} disabled={isWriting || isGeneratingPreview || isGeneratingPattern}>
      {isGeneratingPreview || isGeneratingPattern
        ? 'Generating…'
        : outputMode === 'still' ? '📷 Generate Still' : '▶ Preview'}
    </button>
  </div>

  <!-- Apple-style segmented control -->
  <div class="segmented-control">
    <button
      class="seg-btn"
      class:seg-active={outputMode === 'still'}
      onclick={() => outputMode = 'still'}
      disabled={isWriting}
    >Still</button>
    <button
      class="seg-btn"
      class:seg-active={outputMode === 'video'}
      onclick={() => outputMode = 'video'}
      disabled={isWriting}
    >Video</button>
  </div>
{/if}

<style>
  .row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.6rem; }
  .dim { font-weight: 400; color: #7a9dc5; }
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #b0cce8; }
  .pattern-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.5rem;
    margin: 0.5rem 0;
  }
  .pattern-card {
    display: flex; flex-direction: column; align-items: center;
    padding: 0.6rem 0.4rem; text-align: center;
    border-radius: 10px; gap: 0.2rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #e6f1ff;
    cursor: pointer;
  }
  .pattern-card:hover:not(:disabled) { border-color: rgba(129, 178, 255, 0.5); }
  .pattern-card .pattern-icon { font-size: 1.5rem; }
  .pattern-card .pattern-name { font-size: 0.8rem; font-weight: 600; }
  .pattern-card .pattern-desc { font-size: 0.7rem; color: #8badd4; }
  .active {
    border-color: rgba(129, 178, 255, 0.9) !important;
    background: rgba(129, 178, 255, 0.14);
  }

  /* Apple-style segmented control */
  .segmented-control {
    display: inline-flex;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 3px;
    gap: 2px;
    margin-top: 0.3rem;
  }
  .seg-btn {
    padding: 0.35rem 1.1rem;
    border-radius: 8px;
    border: none;
    background: transparent;
    color: #8badd4;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s, color 0.2s;
  }
  .seg-btn:hover:not(:disabled):not(.seg-active) { color: #c0d8f0; }
  .seg-active {
    background: rgba(129, 178, 255, 0.18);
    color: #e6f1ff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  }
  .seg-btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
