<script lang="ts">
  interface Props {
    isWriting: boolean
    qrUrl: string
    qrDarkColor: string
    qrLightColor: string
    qrDotStyle: string
    qrOutsideMode: string
    qrZoom: number
    qrRotation: number
  }

  let {
    isWriting,
    qrUrl = $bindable(),
    qrDarkColor = $bindable(),
    qrLightColor = $bindable(),
    qrDotStyle = $bindable(),
    qrOutsideMode = $bindable(),
    qrZoom = $bindable(),
    qrRotation = $bindable(),
  }: Props = $props()
</script>

<div class="settings">
  <label class="wide">
    <span>URL</span>
    <input type="url" bind:value={qrUrl} placeholder="https://example.com" disabled={isWriting} />
  </label>
</div>

<div class="settings">
  <label>
    <span>Dark modules</span>
    <input type="color" bind:value={qrDarkColor} disabled={isWriting} />
  </label>
  <label>
    <span>Light modules</span>
    <input type="color" bind:value={qrLightColor} disabled={isWriting} />
  </label>
  <label>
    <span>Dot style</span>
    <select bind:value={qrDotStyle} disabled={isWriting}>
      <option value="square">Square</option>
      <option value="round">Round</option>
      <option value="squircle">Squircle</option>
    </select>
  </label>
  <label>
    <span>Outside dots</span>
    <select bind:value={qrOutsideMode} disabled={isWriting}>
      <option value="on">Enabled</option>
      <option value="off">Disabled</option>
    </select>
  </label>
</div>

<div class="settings">
  <label class="wide">
    <span>Zoom ({qrZoom.toFixed(2)}x)</span>
    <input type="range" min="0.85" max="1.45" step="0.01" bind:value={qrZoom} disabled={isWriting} />
  </label>
  <label class="wide">
    <span>Rotation ({qrRotation.toFixed(0)}°)</span>
    <input type="range" min="-180" max="180" step="45" bind:value={qrRotation} disabled={isWriting} />
  </label>
</div>

<style>
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #d4d4d4; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-transform: uppercase; letter-spacing: -0.08em; font-size: 0.75rem; }
  .settings .wide { min-width: min(420px, 100%); flex: 1; }
  select {
    border-radius: 2px;
    border: 1px solid #2a2a2a;
    background: #000;
    color: #f5f5f5;
    padding: 0.5rem 0.7rem;
    font-size: 0.9rem;
    transition: border-color 130ms ease, background-color 130ms ease;
  }
  select:hover { border-color: #3fd2fb; background: rgba(63, 210, 251, 0.12); }
  input[type="range"] {
    width: 100%;
    background: transparent;
    border: none;
    padding: 0;
  }
</style>
