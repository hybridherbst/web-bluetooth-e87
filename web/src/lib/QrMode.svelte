<script lang="ts">
  interface Props {
    isWriting: boolean
    qrUrl: string
    qrDarkColor: string
    qrLightColor: string
    qrDotStyle: string
    qrEdgeStyle: string
    qrZoom: number
    qrRotation: number
  }

  let {
    isWriting,
    qrUrl = $bindable(),
    qrDarkColor = $bindable(),
    qrLightColor = $bindable(),
    qrDotStyle = $bindable(),
    qrEdgeStyle = $bindable(),
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
    <span>Edge style</span>
    <select bind:value={qrEdgeStyle} disabled={isWriting}>
      <option value="square">Square</option>
      <option value="round">Round</option>
      <option value="squircle">Squircle</option>
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
    <input type="range" min="-180" max="180" step="1" bind:value={qrRotation} disabled={isWriting} />
  </label>
</div>

<style>
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #b0cce8; }
  .settings .wide { min-width: min(420px, 100%); flex: 1; }
  select {
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    background: rgba(255, 255, 255, 0.07);
    color: #f3f9ff;
    padding: 0.5rem 0.7rem;
    font-size: 0.9rem;
  }
  input[type="range"] {
    width: 100%;
    background: transparent;
    border: none;
    padding: 0;
  }
</style>
