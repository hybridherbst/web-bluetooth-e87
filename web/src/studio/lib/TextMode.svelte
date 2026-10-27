<script lang="ts">
  import type { TextSettings } from '../studio-generators'
  let { settings = $bindable(), disabled = false }: { settings: TextSettings; disabled?: boolean } = $props()
</script>
<div class="text-controls">
  <label class="text-entry"><span>Текст</span><input bind:value={settings.text} maxlength="80" placeholder="Привет, мир!" {disabled} /></label>
  <div class="settings">
    <label><span>Шрифт</span><select bind:value={settings.font} {disabled}><option value="sans">Гротеск</option><option value="serif">Антиква</option><option value="mono">Моно</option></select></label>
    <label><span>Размер</span><select bind:value={settings.size} {disabled}><option value={48}>48 px</option><option value={68}>68 px</option><option value={92}>92 px</option><option value={120}>120 px</option></select></label>
    <label><span>Скорость</span><select bind:value={settings.speed} {disabled}><option value={100}>Медленно</option><option value={170}>Средне</option><option value={260}>Быстро</option></select></label>
    <label><span>Направление</span><select bind:value={settings.direction} {disabled}><option value="left">← Влево</option><option value="right">Вправо →</option></select></label>
    <label><span>Текст</span><input type="color" bind:value={settings.color} {disabled} /></label>
    <label><span>Фон</span><input type="color" bind:value={settings.background} {disabled} /></label>
    <label class="glow-switch"><input type="checkbox" bind:checked={settings.glow} {disabled} /><span>Свечение</span></label>
  </div>
</div>
