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
    <span>Цвет кода</span>
    <input type="color" bind:value={qrDarkColor} disabled={isWriting} />
  </label>
  <label>
    <span>Цвет фона</span>
    <input type="color" bind:value={qrLightColor} disabled={isWriting} />
  </label>
  <label>
    <span>Форма точек</span>
    <select bind:value={qrDotStyle} disabled={isWriting}>
      <option value="square">Квадрат</option>
      <option value="round">Круг</option>
      <option value="squircle">Скруглённые</option>
    </select>
  </label>
  <label>
    <span>Точки вокруг</span>
    <select bind:value={qrOutsideMode} disabled={isWriting}>
      <option value="on">Включены</option>
      <option value="off">Выключены</option>
    </select>
  </label>
</div>

<div class="settings">
  <label class="wide">
    <span>Масштаб ({qrZoom.toFixed(2)}x)</span>
    <input type="range" min="0.85" max="1.45" step="0.01" bind:value={qrZoom} disabled={isWriting} />
  </label>
  <label class="wide">
    <span>Поворот ({qrRotation.toFixed(0)}°)</span>
    <input type="range" min="-180" max="180" step="45" bind:value={qrRotation} disabled={isWriting} />
  </label>
</div>

<style>
  .settings { display: flex; gap: 0.8rem; margin: 0.6rem 0; flex-wrap: wrap; align-items: flex-end; }
  .settings label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.88rem; }
  .settings label span { color: #d4d4d4; font-family: inherit; text-transform: none; letter-spacing: 0; font-size: 0.75rem; }
  .settings .wide { min-width: min(420px, 100%); flex: 1; }
  select {
    border-radius: 10px;
    border: 1px solid #303830;
    background: #101511;
    color: #eef3e9;
    padding: 0.5rem 0.7rem;
    font-size: 0.9rem;
    transition: border-color 130ms ease, background-color 130ms ease;
  }
  select:hover { border-color: #c0ee91; background: rgba(192, 238, 145, 0.12); }
  input[type="range"] {
    width: 100%;
    background: transparent;
    border: none;
    padding: 0;
  }
</style>
