<script lang="ts">
  import { onMount } from 'svelte'
  import { PATTERNS, type PatternDef } from '../../pattern-generators'
  import { FASHION_PATTERNS } from '../studio-generators'
  interface Props {
    isWriting: boolean; isGeneratingPreview: boolean; isGeneratingPattern: boolean
    selectedPattern: PatternDef | null; patternFrameCount: number; patternFps: number
    outputKey?: string
    onSelectPattern: (pat: PatternDef) => void
    onGeneratePreview: () => void; onGenerateStill: () => void
  }
  let { isWriting, isGeneratingPreview, isGeneratingPattern, selectedPattern, patternFrameCount = $bindable(), patternFps = $bindable(), outputKey = '', onSelectPattern, onGeneratePreview, onGenerateStill }: Props = $props()
  let outputMode: 'still' | 'video' = $state('video')
  let classic = $state(false)
  let thumbs = $state<Record<string, string>>({})
  let lastSignature = ''
  let busy = $derived(isWriting || isGeneratingPreview || isGeneratingPattern)
  onMount(() => {
    let cancelled = false
    const urls: string[] = []
    void (async () => {
      for (const pat of FASHION_PATTERNS) {
        const frames = await pat.generate({ frames: 1, fps: 15 })
        if (cancelled) break
        const url = URL.createObjectURL(new Blob([new Uint8Array(frames[0])], { type: 'image/jpeg' }))
        urls.push(url); thumbs = { ...thumbs, [pat.id]: url }
      }
    })()
    return () => { cancelled = true; urls.forEach(url => URL.revokeObjectURL(url)) }
  })
  $effect(() => {
    if (!selectedPattern || busy) return
    const signature = `${selectedPattern.id}:${outputMode}:${patternFrameCount}:${patternFps}:${outputKey}`
    if (signature === lastSignature) return
    const timer = setTimeout(() => {
      lastSignature = signature
      if (outputMode === 'still') onGenerateStill(); else onGeneratePreview()
    }, 200)
    return () => clearTimeout(timer)
  })
</script>
<div class="collection-switch"><button class:chosen={!classic} onclick={() => classic = false}>Studio / 08</button><button class:chosen={classic} onclick={() => classic = true}>Классика / 12</button></div>
<div class="pattern-grid">
  {#each classic ? PATTERNS : FASHION_PATTERNS as pat}
    <button class="pattern-card" class:active={selectedPattern?.id === pat.id} aria-pressed={selectedPattern?.id === pat.id} onclick={() => onSelectPattern(pat)} disabled={busy} title={pat.description}>
      {#if thumbs[pat.id]}<img src={thumbs[pat.id]} alt="" />{:else}<span class="pattern-icon">{pat.icon}</span>{/if}
      <span class="pattern-name">{pat.name}</span>
    </button>
  {/each}
</div>
<div class="pattern-options">
  <div class="output-switch"><button class:chosen={outputMode === 'video'} onclick={() => outputMode = 'video'} disabled={busy}>Анимация</button><button class:chosen={outputMode === 'still'} onclick={() => outputMode = 'still'} disabled={busy}>Кадр</button></div>
  {#if outputMode === 'video'}<select aria-label="Длительность анимации" value={patternFrameCount / patternFps} disabled={busy} onchange={(event) => { patternFps = 15; patternFrameCount = Number(event.currentTarget.value) * 15 }}><option value={3}>3 сек</option><option value={5}>5 сек</option><option value={6}>6 сек</option><option value={8}>8 сек</option></select>{/if}
</div>
