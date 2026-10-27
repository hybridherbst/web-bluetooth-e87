<script lang="ts">
  import { onMount } from 'svelte'
  import { normalizeMAC as address, systemMAC } from './device-identity'
  const platform = window.e87Desktop?.platform || 'unknown'
  let { connected = false, onSelect }: { connected?: boolean; onSelect?: (profile: { id: string; name: string; mac: string }) => void } = $props()
  type Profile = { id: string; name: string; mac: string; macSource?: string }
  const KEY = 'e87Studio.badges.v1'
  function readProfiles(): Record<string, Profile> {
    try {
      const data = JSON.parse(localStorage.getItem(KEY) || '{}')
      if (platform === 'darwin') for (const p of Object.values(data) as any[]) {
        if (p && p.mac === address(p.id || '')) p.mac = ''
      }
      return Object.fromEntries(Object.entries(data).filter(([, p]: [string, any]) => p && typeof p.id === 'string' && typeof p.name === 'string' && typeof p.mac === 'string')) as Record<string, Profile>
    } catch { return {} }
  }
  let libraryOpen = $state(false)
  let profiles = $state(readProfiles())
  let scan = $state<BadgeScan | null>(null)
  let selected = $state('')
  let active = $state<Profile | null>(null)
  let name = $state('')
  let macInput = $state('')
  let error = $state('')
  let scanDialog: HTMLDialogElement
  const key = (id: string) => id.toUpperCase()
  function profileFor(device: BadgeDevice): Profile {
    const saved = profiles[key(device.deviceId)]
    return { id: device.deviceId, name: saved?.name || device.deviceName || 'E87', mac: device.advertisedMac || saved?.mac || systemMAC(device.deviceId, platform), macSource: device.advertisedMac ? 'advertisement' : saved?.macSource || 'system' }
  }
  function choose(device: BadgeDevice) {
    selected = device.deviceId
    const profile = profileFor(device)
    name = profile.name
    macInput = profile.mac
    error = ''
  }
  async function connectSelected() {
    if (!scan || !selected || !scan.devices.some(d => d.deviceId === selected)) return
    const mac = address(macInput)
    if (macInput.trim() && !mac) { error = 'Введите MAC в формате AA:BB:CC:DD:EE:FF или ссылку из QR-кода.'; return }
    const detected = scan.devices.find(d => d.deviceId === selected)?.advertisedMac
    const profile = { id: selected, name: name.trim() || 'E87', mac, macSource: detected && mac === detected ? 'advertisement' : mac === systemMAC(selected, platform) ? 'system' : 'manual' }
    const accepted = await window.e87Desktop?.select(scan.requestId, selected)
    if (accepted) {
      active = profile
      onSelect?.(profile)
      profiles = { ...profiles, [key(selected)]: profile }
      try { localStorage.setItem(KEY, JSON.stringify(profiles)) } catch { error = 'Не удалось сохранить имя значка.' }
    } else { error = 'Значок исчез из списка. Выберите его снова.' }
  }
  function cancel() { if (scan) void window.e87Desktop?.select(scan.requestId, '') }
  function forget(id: string) {
    const next = { ...profiles }; delete next[key(id)]; profiles = next
    localStorage.setItem(KEY, JSON.stringify(profiles))
    if (active?.id === id && !connected) active = null
  }
  onMount(() => {
    const api = window.e87Desktop
    if (!api) return
    const stopScan = api.onDevices(value => {
      if (value?.requestId !== scan?.requestId) { selected = ''; name = ''; macInput = ''; error = '' }
      scan = value
      if (selected && !macInput) macInput = value?.devices.find(d => d.deviceId === selected)?.advertisedMac || ''
    })
    return stopScan
  })
  $effect(() => { if (scan) scanDialog?.showModal(); else scanDialog?.close() })
</script>

<div class="badge-library"><button class="quiet-button" onclick={() => libraryOpen = !libraryOpen} aria-expanded={libraryOpen}>Значки</button>
{#if libraryOpen}<div class="badge-library-panel">
{#if active}
  <div class="device-identity">
    <span class="eyebrow">{connected ? 'Выбранный значок' : 'Последний выбор'}</span>
    <strong>{active.name}</strong>
    <code>MAC · {active.mac || 'не раскрыт системой'}</code>
    <small>{active.macSource === 'advertisement' ? 'MAC из Bluetooth-объявления' : active.macSource === 'manual' ? 'MAC сохранён с экрана значка' : 'Идентификатор Bluetooth'}</small>
    <code class="device-id">{active.id}</code>
  </div>
{/if}

<details class="saved-badges" open>
  <summary>Мои значки <span>{Object.keys(profiles).length}</span></summary>
  {#each Object.values(profiles) as profile}
    <div class="saved-badge">
      <strong>{profile.name}</strong>
      <code>MAC · {profile.mac || 'не указан'}</code>
      <small class="device-id">ID · {profile.id}</small>
      <button class="text-button" onclick={() => forget(profile.id)} disabled={connected && active?.id === profile.id}>Забыть</button>
    </div>
  {:else}
    <p class="muted">После выбора значка здесь сохранятся его имя и MAC.</p>
  {/each}
</details>
</div>{/if}</div>

<dialog bind:this={scanDialog} class="device-dialog" oncancel={(event) => { event.preventDefault(); cancel() }}>
  <div class="dialog-header"><div><span class="eyebrow">Bluetooth</span><h2>Какой значок подключить?</h2></div><button class="icon-button" aria-label="Отменить поиск" onclick={cancel}>×</button></div>
  <p class="muted">Откройте экран Bluetooth с QR-кодом на значке и закройте ZRun и вкладку сайта, если они подключены.</p>
  <div class="scan-label"><i class="status-dot pulsing"></i> Поиск рядом с вами <span>{scan?.devices.length || 0}</span></div>
  <div class="device-list">
    {#each scan?.devices || [] as device (device.deviceId)}
      {@const profile = profileFor(device)}
      <button class="device-option" class:selected={selected === device.deviceId} aria-pressed={selected === device.deviceId} onclick={() => choose(device)}>
        <span class="mini-badge">87</span><span class="device-copy"><strong>{profile.name}</strong><code>MAC · {profile.mac || 'скрыт ОС'}</code><small>ID · {device.deviceId}</small></span><span class="radio-dot"></span>
      </button>
    {:else}
      <div class="scan-empty">Ждём значок…<small>Если рядом несколько E87, включайте режим подключения по одному, чтобы сохранить верные имена.</small></div>
    {/each}
  </div>
  {#if selected}
    <div class="identity-fields"><label>Имя значка<input bind:value={name} maxlength="60" placeholder="Например, мой E87" /></label><label>MAC с экрана или ссылка из QR<input bind:value={macInput} placeholder="AA:BB:CC:DD:EE:FF" spellcheck="false" /></label></div>
  {/if}
  <p class="address-note">{window.e87Desktop?.platform === 'darwin' ? 'MAC считывается из объявления значка, если прошивка его передаёт. ID — служебный.' : 'Если система не раскрыла MAC, указан её идентификатор.'} MAC с экрана или QR-кода можно сохранить вручную.</p>
  {#if error}<p class="form-error" role="alert">{error}</p>{/if}
  <div class="dialog-actions"><button onclick={cancel}>Отмена</button><button class="primary" onclick={connectSelected} disabled={!selected || !scan?.devices.some(d => d.deviceId === selected)}>Подключить значок →</button></div>
</dialog>
