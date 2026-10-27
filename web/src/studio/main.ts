import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { initializeNative } from './native'

initializeNative().then(() => mount(App, { target: document.getElementById('app')! })).catch(error => {
  document.getElementById('app')!.textContent = `Не удалось запустить приложение: ${String(error)}`
})
