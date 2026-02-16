<script lang="ts">
  import { formatDuration, formatBytes } from './lib/utils'
  import { MAX_UPLOAD_BYTES, imageFileTo368JpegBytes, imagesToAvi, videoToAvi } from './lib/image-processing'
  import { parseAviFrames, readAviFps } from './lib/avi-preview'
  import { connectE87, disconnectE87, writeFileE87, type E87Connection, type UploadMode } from './lib/e87-protocol'
  import { buildMjpgAvi } from './avi-builder'
  import type { PatternDef } from './pattern-generators'

  import AviPlayer from './lib/AviPlayer.svelte'
  import UploadProgress from './lib/UploadProgress.svelte'
  import ImageMode from './lib/ImageMode.svelte'
  import SequenceMode from './lib/SequenceMode.svelte'
  import VideoMode from './lib/VideoMode.svelte'
  import PatternMode from './lib/PatternMode.svelte'

  // ─── Debug flag ───
  const debugMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('debug')

  // ─── BLE connection state ───
  // MUST be $state.raw — Svelte 5's deep proxy breaks the shared
  // notificationQueue array (onNotification pushes to the original,
  // but writeFileE87 would poll the proxy copy → auth timeout).
  let conn: E87Connection | null = $state.raw(null)
  let isConnecting = $state(false)
  let isWriting = $state(false)
  let cancelRequested = $state(false)
  let interChunkDelayMs = $state(0)

  let status = $state('Disconnected')
  let batteryLevel: number | null = $state(null)
  let batteryUpdatedAt = $state('')

  let logs: string[] = $state([])

  // ─── Upload mode & file state ───
  let uploadMode: UploadMode = $state('pattern')
  let selectedFile: File | null = $state(null)
  let selectedFiles: File[] = $state([])
  let previewUrl: string | null = $state(null)

  // ─── Mode-specific settings ───
  let videoFps = $state(12)
  let sequenceFps = $state(1)
  let videoTrimStart = $state(0)
  let videoTrimEnd = $state(0)
  let videoDuration = $state(0)
  let videoZoom = $state(1.0)
  let videoZoomX = $state(0.5)
  let videoZoomY = $state(0.5)
  let patternFrameCount = $state(60)
  let patternFps = $state(12)
  let selectedPattern: PatternDef | null = $state(null)

  // ─── Preview state ───
  let aviPreviewFrames: ImageBitmap[] = $state([])
  let aviPreviewFps = $state(12)
  let isGeneratingPreview = $state(false)
  let isGeneratingPattern = $state(false)
  let preparedPayload: Uint8Array | null = $state(null)
  let preparedPayloadLabel = $state('')
  let preparedIsStillImage = $state(false)
  let aviPlayer: AviPlayer | null = $state(null)

  // ─── Upload progress state ───
  let progress = $state(0)
  let progressLabel = $state('')
  let uploadStartTime = $state(0)
  let sentBytesForEta = $state(0)
  let totalBytesForEta = $state(0)

  // ─── Logging ───

  function log(message: string): void {
    const ts = new Date().toLocaleTimeString()
    logs = [`[${ts}] ${message}`, ...logs].slice(0, 250)
  }

  // ─── Connection ───

  async function connect(): Promise<void> {
    if (!('bluetooth' in navigator)) {
      status = 'Web Bluetooth is not available in this browser.'
      log(status)
      return
    }
    isConnecting = true
    try {
      status = 'Requesting device...'
      conn = await connectE87(log)
      batteryLevel = conn.batteryLevel
      batteryUpdatedAt = conn.batteryUpdatedAt
      status = `Connected: ${conn.device.name ?? 'Unknown device'}`
    } catch (error) {
      status = `Connection failed: ${(error as Error).message}`
      log(status)
      conn = null
      batteryLevel = null
      batteryUpdatedAt = ''
    } finally {
      isConnecting = false
    }
  }

  async function disconnect(): Promise<void> {
    cancelRequested = true
    if (conn) {
      await disconnectE87(conn, log)
      conn = null
    }
    batteryLevel = null
    batteryUpdatedAt = ''
    status = 'Disconnected'
    progress = 0
    progressLabel = ''
    log('Disconnected.')
  }

  // ─── File handling ───

  function revokePreviewUrl() {
    if (previewUrl && !previewUrl.startsWith('/')) URL.revokeObjectURL(previewUrl)
  }

  function setFile(event: Event): void {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    selectedFile = file
    preparedPayload = null
    preparedIsStillImage = false
    if (file) {
      log(`Selected: ${file.name}`)
      revokePreviewUrl()
      previewUrl = URL.createObjectURL(file)
    }
  }

  function setMultipleFiles(event: Event): void {
    const input = event.target as HTMLInputElement
    const files = input.files
    if (!files || files.length === 0) return
    selectedFiles = Array.from(files)
    preparedPayload = null
    preparedIsStillImage = false
    log(`Selected ${selectedFiles.length} images for sequence`)
    revokePreviewUrl()
    previewUrl = URL.createObjectURL(selectedFiles[0])
  }

  function setVideoFile(event: Event): void {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0] ?? null
    selectedFile = file
    preparedPayload = null
    preparedIsStillImage = false
    videoTrimStart = 0
    videoTrimEnd = 0
    videoDuration = 0
    if (file) {
      log(`Selected video: ${file.name} (${formatBytes(file.size)})`)
      revokePreviewUrl()
      previewUrl = URL.createObjectURL(file)
      const v = document.createElement('video')
      v.preload = 'metadata'
      v.onloadedmetadata = () => {
        videoDuration = v.duration
        videoTrimEnd = v.duration
        URL.revokeObjectURL(v.src)
      }
      v.src = URL.createObjectURL(file)
    }
  }

  function selectPattern(pat: PatternDef): void {
    selectedPattern = pat
    preparedPayload = null
    preparedIsStillImage = false
    aviPlayer?.stop()
  }

  function switchMode(mode: UploadMode): void {
    uploadMode = mode
    aviPlayer?.stop()
  }

  // ─── Pattern still-image generation ───

  async function generatePatternStill(): Promise<void> {
    if (!selectedPattern) return
    isGeneratingPattern = true
    isGeneratingPreview = true
    preparedPayload = null
    aviPlayer?.stop()
    aviPreviewFrames.forEach(f => f.close())
    aviPreviewFrames = []

    try {
      // Generate a handful of frames and pick one from the middle for a representative still
      const sampleFrames = Math.max(patternFrameCount, 30)
      const allFrames = await selectedPattern.generate({ frames: sampleFrames, fps: patternFps })
      // Pick a frame ~40% through — usually more visually interesting than exact center
      const pickIdx = Math.floor(sampleFrames * 0.4)
      const stillJpeg = allFrames[pickIdx]

      preparedPayload = stillJpeg
      preparedIsStillImage = true
      preparedPayloadLabel = `${selectedPattern.name} still — ${formatBytes(stillJpeg.length)}`

      // Show as preview image
      revokePreviewUrl()
      previewUrl = URL.createObjectURL(new Blob([stillJpeg], { type: 'image/jpeg' }))
      log(`Still ready: ${selectedPattern.name} (frame ${pickIdx + 1}/${sampleFrames}), ${formatBytes(stillJpeg.length)}`)
    } catch (err) {
      log(`Still generation failed: ${(err as Error).message}`)
    } finally {
      isGeneratingPattern = false
      isGeneratingPreview = false
    }
  }

  // ─── Preview generation ───

  async function generatePreview(): Promise<void> {
    isGeneratingPreview = true
    preparedPayload = null
    preparedIsStillImage = false
    aviPlayer?.stop()
    aviPreviewFrames.forEach(f => f.close())
    aviPreviewFrames = []

    try {
      let avi: Uint8Array
      let label: string

      if (uploadMode === 'images') {
        if (selectedFiles.length === 0) throw new Error('No images selected')
        avi = await imagesToAvi(selectedFiles, sequenceFps, log)
        label = `${selectedFiles.length} images @ ${sequenceFps}fps`
      } else if (uploadMode === 'video') {
        if (!selectedFile) throw new Error('No video selected')
        avi = await videoToAvi(selectedFile, {
          fps: videoFps, trimStart: videoTrimStart, trimEnd: videoTrimEnd,
          zoom: videoZoom, zoomCx: videoZoomX, zoomCy: videoZoomY,
        }, log)
        label = `Video ${videoTrimStart.toFixed(1)}s–${videoTrimEnd.toFixed(1)}s @ ${videoFps}fps`
      } else if (uploadMode === 'pattern') {
        if (!selectedPattern) throw new Error('No pattern selected')
        isGeneratingPattern = true
        const patternFrames = await selectedPattern.generate({ frames: patternFrameCount, fps: patternFps })
        avi = buildMjpgAvi(patternFrames, { fps: patternFps })
        label = `${selectedPattern.name} — ${patternFrameCount} frames @ ${patternFps}fps`
        isGeneratingPattern = false
      } else {
        throw new Error('Preview only for sequence/video/pattern modes')
      }

      if (avi.length > MAX_UPLOAD_BYTES) {
        log(`⚠️ Generated AVI is ${formatBytes(avi.length)} — exceeds ${formatBytes(MAX_UPLOAD_BYTES)} limit!`)
      }

      aviPreviewFps = readAviFps(avi)
      aviPreviewFrames = await parseAviFrames(avi)
      preparedPayload = avi
      preparedPayloadLabel = `${label} — ${formatBytes(avi.length)}`
      log(`Preview ready: ${aviPreviewFrames.length} frames @ ${aviPreviewFps}fps, ${formatBytes(avi.length)}`)

      // Let component mount, then start playback
      requestAnimationFrame(() => aviPlayer?.startPreview())
    } catch (err) {
      log(`Preview failed: ${(err as Error).message}`)
    } finally {
      isGeneratingPreview = false
      isGeneratingPattern = false
    }
  }

  // ─── Get upload bytes ───

  async function getUploadBytes(): Promise<Uint8Array> {
    if (preparedPayload) {
      // If this is a pattern-generated still, override uploadMode so the device gets .jpg not .avi
      if (preparedIsStillImage) uploadMode = 'image'
      log(`Using prepared payload: ${formatBytes(preparedPayload.length)}`)
      return preparedPayload
    }

    if (uploadMode === 'image') {
      if (!selectedFile) throw new Error('No file selected.')
      if (selectedFile.type.startsWith('image/')) {
        return imageFileTo368JpegBytes(selectedFile)
      }
      return new Uint8Array(await selectedFile.arrayBuffer())
    }
    if (uploadMode === 'images') {
      if (selectedFiles.length === 0) throw new Error('No images selected for sequence.')
      return imagesToAvi(selectedFiles, sequenceFps, log)
    }
    if (uploadMode === 'video') {
      if (!selectedFile) throw new Error('No video file selected.')
      return videoToAvi(selectedFile, {
        fps: videoFps, trimStart: videoTrimStart, trimEnd: videoTrimEnd,
        zoom: videoZoom, zoomCx: videoZoomX, zoomCy: videoZoomY,
      }, log)
    }
    if (uploadMode === 'pattern') {
      if (!selectedPattern) throw new Error('No pattern selected.')
      const patternFrames = await selectedPattern.generate({ frames: patternFrameCount, fps: patternFps })
      return buildMjpgAvi(patternFrames, { fps: patternFps })
    }
    throw new Error(`Unknown upload mode: ${uploadMode}`)
  }

  // ─── Upload orchestration ───

  async function startUpload(): Promise<void> {
    if (!conn) {
      status = 'Not connected.'
      return
    }
    if (uploadMode === 'image' && !selectedFile && !preparedPayload) {
      status = 'Select an image.'
      return
    }
    if (uploadMode === 'images' && selectedFiles.length === 0) {
      status = 'Select images for the sequence.'
      return
    }
    if (uploadMode === 'video' && !selectedFile) {
      status = 'Select a video file.'
      return
    }
    if (uploadMode === 'pattern' && !selectedPattern) {
      status = 'Select a pattern.'
      return
    }

    isWriting = true
    cancelRequested = false
    progress = 0
    progressLabel = 'Starting...'
    sentBytesForEta = 0
    totalBytesForEta = 0
    uploadStartTime = 0

    try {
      aviPlayer?.stop()
      const payload = await getUploadBytes()

      if (payload.length > MAX_UPLOAD_BYTES) {
        throw new Error(`File too large: ${formatBytes(payload.length)} exceeds ${formatBytes(MAX_UPLOAD_BYTES)} limit.`)
      }

      if (uploadMode === 'image') {
        revokePreviewUrl()
        previewUrl = URL.createObjectURL(new Blob([payload], { type: 'image/jpeg' }))
      }

      uploadStartTime = Date.now()
      totalBytesForEta = payload.length

      await writeFileE87({
        conn: conn!,
        payload,
        uploadMode,
        interChunkDelayMs,
        cancelRequested: () => cancelRequested,
        onProgress: (bytesSent, totalBytes, chunksSent, totalChunks) => {
          sentBytesForEta = bytesSent
          const pct = Math.min(100, Math.round((bytesSent / totalBytes) * 100))
          progress = pct
          progressLabel = `${pct}% — ${formatBytes(bytesSent)} / ${formatBytes(totalBytes)} — chunk ${chunksSent}/${totalChunks}`
        },
        log,
      })

      progress = 100
      const elapsed = formatDuration((Date.now() - uploadStartTime) / 1000)
      status = `Upload completed in ${elapsed}.`
    } catch (error) {
      status = `Upload failed: ${(error as Error).message}`
      log(status)
    } finally {
      isWriting = false
    }
  }

  function cancelWrite(): void {
    cancelRequested = true
    log('Cancel requested.')
  }
</script>

<main class="app">
  <h1>E87 / L8 Badge Writer</h1>
  <p class="hint">Web Bluetooth uploader for circular LED badges.</p>

  <!-- ═══ Connection panel ═══ -->
  <section class="panel">
    <div class="row buttons">
      <button onclick={connect} disabled={isConnecting || isWriting}>
        {isConnecting ? 'Connecting…' : 'Connect'}
      </button>
      <button onclick={disconnect} disabled={!conn?.server?.connected || isWriting}>Disconnect</button>
      <button class="secondary" onclick={cancelWrite} disabled={!isWriting}>Cancel</button>
    </div>
    <div class="status">Status: {status}</div>
    {#if batteryLevel !== null}
      <div class="status">Battery: {batteryLevel}% <span class="dim">({batteryUpdatedAt})</span></div>
    {/if}
  </section>

  <!-- ═══ Upload panel ═══ -->
  <section class="panel">
    <!-- Mode tabs -->
    <div class="row buttons mode-tabs">
      <button class:active={uploadMode === 'pattern'} onclick={() => switchMode('pattern')} disabled={isWriting}>
        ✨ Pattern
      </button>
      <button class:active={uploadMode === 'image'} onclick={() => switchMode('image')} disabled={isWriting}>
        🖼 Image
      </button>
      <button class:active={uploadMode === 'images'} onclick={() => switchMode('images')} disabled={isWriting}>
        🎞 Sequence
      </button>
      <button class:active={uploadMode === 'video'} onclick={() => switchMode('video')} disabled={isWriting}>
        🎬 Video
      </button>
    </div>

    <!-- Mode-specific content -->
    {#if uploadMode === 'pattern'}
      <PatternMode
        {isWriting}
        {isGeneratingPreview}
        {isGeneratingPattern}
        {selectedPattern}
        bind:patternFrameCount
        bind:patternFps
        onSelectPattern={selectPattern}
        onGeneratePreview={generatePreview}
        onGenerateStill={generatePatternStill}
      />
    {:else if uploadMode === 'image'}
      <ImageMode
        {isWriting}
        {previewUrl}
        onSelectFile={setFile}
      />
    {:else if uploadMode === 'images'}
      <SequenceMode
        {isWriting}
        {isGeneratingPreview}
        {selectedFiles}
        bind:sequenceFps
        onSelectFiles={setMultipleFiles}
        onGeneratePreview={generatePreview}
      />
    {:else if uploadMode === 'video'}
      <VideoMode
        {isWriting}
        {isGeneratingPreview}
        {selectedFile}
        {previewUrl}
        bind:videoFps
        bind:videoTrimStart
        bind:videoTrimEnd
        {videoDuration}
        bind:videoZoom
        bind:videoZoomX
        bind:videoZoomY
        onSelectVideo={setVideoFile}
        onGeneratePreview={generatePreview}
      />
    {/if}

    <!-- Shared AVI preview player -->
    {#if aviPreviewFrames.length > 0 && uploadMode !== 'image'}
      <AviPlayer
        bind:this={aviPlayer}
        frames={aviPreviewFrames}
        fps={aviPreviewFps}
      />
      {#if preparedPayloadLabel}
        <p class="dim payload-info">
          Ready: {preparedPayloadLabel}
          {#if preparedPayload && preparedPayload.length > MAX_UPLOAD_BYTES}
            <span style="color:#ff6666">⚠ {formatBytes(preparedPayload.length)} exceeds {formatBytes(MAX_UPLOAD_BYTES)} limit</span>
          {/if}
        </p>
      {/if}
    {/if}

    <!-- Pattern still preview -->
    {#if uploadMode === 'pattern' && previewUrl && preparedPayload && aviPreviewFrames.length === 0}
      <div style="text-align:center;margin:0.5rem 0">
        <img src={previewUrl} alt="Pattern still" style="max-width:200px;max-height:200px;border:1px solid #334;border-radius:50%;aspect-ratio:1" />
      </div>
      {#if preparedPayloadLabel}
        <p class="dim payload-info">
          Ready: {preparedPayloadLabel}
        </p>
      {/if}
    {/if}

    <!-- Debug settings -->
    {#if debugMode}
      <div class="settings">
        <label>
          <span>Inter-chunk delay (ms)</span>
          <input type="number" min="0" max="1000" step="1" bind:value={interChunkDelayMs} disabled={isWriting} />
        </label>
      </div>
    {/if}

    <!-- Upload button -->
    <div class="row buttons" style="margin-top:0.5rem">
      <button onclick={startUpload} disabled={!conn || isWriting}>
        {isWriting ? 'Uploading…' : 'Upload'}
      </button>
    </div>

    <!-- Upload progress -->
    <UploadProgress
      {isWriting}
      {progress}
      {progressLabel}
      {uploadStartTime}
      sentBytes={sentBytesForEta}
      totalBytes={totalBytesForEta}
    />
  </section>

  <!-- ═══ Log panel ═══ -->
  <section class="panel logs">
    <h2>Log</h2>
    <ul>
      {#each logs as entry}
        <li>{entry}</li>
      {/each}
    </ul>
  </section>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: linear-gradient(180deg, #09111d 0%, #0f1d34 100%);
    color: #e6f1ff;
    min-height: 100vh;
  }
  .app { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
  h1 { margin: 0 0 0.25rem; font-size: 1.6rem; }
  .hint { margin: 0 0 0.8rem; color: #8badd4; font-size: 0.88rem; }
  .panel {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.8rem;
  }
  .row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .buttons { margin-bottom: 0.6rem; }
  .mode-tabs { border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.6rem; margin-bottom: 0.6rem; }
  .status { font-weight: 600; color: #d4e6ff; margin-bottom: 0.15rem; }
  .dim { font-weight: 400; color: #7a9dc5; }
  .payload-info { font-size: 0.8rem; margin: 0.2rem 0; text-align: center; }
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #b0cce8; }
  input, button {
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.07);
    color: #f3f9ff;
    padding: 0.5rem 0.7rem;
    font-size: 0.9rem;
  }
  input[type="number"] { width: 90px; }
  button { cursor: pointer; font-weight: 600; }
  button:hover:not(:disabled) { border-color: rgba(129, 178, 255, 0.9); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.secondary { background: rgba(255, 100, 100, 0.12); }
  button.active {
    border-color: rgba(129, 178, 255, 0.9);
    background: rgba(129, 178, 255, 0.14);
  }
  .logs h2 { margin: 0 0 0.3rem; font-size: 0.95rem; }
  .logs ul {
    list-style: none; padding: 0; margin: 0;
    max-height: 220px; overflow: auto;
  }
  .logs li {
    color: #b8d4f0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.8rem; line-height: 1.35; padding: 1px 0;
  }
</style>
