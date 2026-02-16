<script lang="ts">
  /**
   * Upload progress bar with percentage, elapsed time, and ETA.
   */
  import { formatDuration, formatBytes } from './utils'

  interface Props {
    isWriting: boolean
    progress: number
    progressLabel: string
    uploadStartTime: number
    sentBytes: number
    totalBytes: number
  }

  let { isWriting, progress, progressLabel, uploadStartTime, sentBytes, totalBytes }: Props = $props()

  let elapsed = $state('')
  let eta = $state('')
  let timerHandle: ReturnType<typeof setInterval> | null = null

  $effect(() => {
    if (isWriting && uploadStartTime > 0) {
      // Start timer
      if (timerHandle) clearInterval(timerHandle)
      timerHandle = setInterval(() => {
        const elapsedSec = (Date.now() - uploadStartTime) / 1000
        elapsed = formatDuration(elapsedSec)
        if (sentBytes > 0) {
          const rate = sentBytes / elapsedSec
          const remaining = (totalBytes - sentBytes) / rate
          eta = formatDuration(remaining)
        } else {
          eta = 'calculating…'
        }
      }, 500)
    } else {
      // Stop timer
      if (timerHandle) {
        clearInterval(timerHandle)
        timerHandle = null
      }
      if (uploadStartTime > 0) {
        elapsed = formatDuration((Date.now() - uploadStartTime) / 1000)
      }
      eta = ''
    }

    return () => {
      if (timerHandle) clearInterval(timerHandle)
    }
  })
</script>

<div class="progress-wrap">
  <div class="progress-bar" style={`width:${progress}%`}></div>
</div>
{#if isWriting || progressLabel}
  <div class="upload-stats">
    <p class="progress-label">{progressLabel}</p>
    {#if isWriting}
      <p class="progress-label">
        ⏱ {elapsed}
        {#if eta} — ETA: {eta}{/if}
      </p>
    {/if}
  </div>
{/if}

<style>
  .progress-wrap {
    width: 100%; height: 10px; border-radius: 99px; overflow: hidden;
    background: rgba(255, 255, 255, 0.1); margin-top: 0.5rem;
  }
  .progress-bar {
    height: 100%; background: linear-gradient(90deg, #6be4ff, #6f95ff);
    transition: width 100ms ease;
  }
  .upload-stats { margin: 0.3rem 0 0; }
  .progress-label { margin: 0.2rem 0; color: #9ec0e8; font-size: 0.85rem; }
</style>
