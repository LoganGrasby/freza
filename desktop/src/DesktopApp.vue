<script setup>
import { ref, onMounted } from 'vue'
import App from '@/App.vue'
import ConnectionPicker from './ConnectionPicker.vue'
import { getLastUsedConnection } from './lib/connections'
import { setBaseUrl, setAuthToken, getJson } from '@/lib/api'

const connected = ref(false)
const activeConnection = ref(null)
const showSettings = ref(false)
const loading = ref(true)

onMounted(async () => {
  const last = await getLastUsedConnection()
  if (last) {
    try {
      setBaseUrl(last.url)
      setAuthToken(last.token || null)
      await getJson('/api/ping')
      activeConnection.value = last
      connected.value = true
    } catch {
      setBaseUrl('')
      setAuthToken(null)
    }
  }
  loading.value = false
})

function handleConnected(conn) {
  activeConnection.value = conn
  connected.value = true
  showSettings.value = false
}

function disconnect() {
  setBaseUrl('')
  setAuthToken(null)
  connected.value = false
  activeConnection.value = null
  showSettings.value = false
}

function openSettings() {
  showSettings.value = true
}

function closeSettings() {
  if (connected.value) {
    showSettings.value = false
  }
}
</script>

<template>
  <div class="h-full">
    <div
      v-if="loading"
      class="flex h-full items-center justify-center bg-[var(--bg-0)]"
    >
      <div class="text-center">
        <div
          class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--accent-glow)]"
        >
          <span class="text-lg font-bold text-[var(--accent)]">F</span>
        </div>
        <p class="text-sm text-[var(--text-2)]">Connecting...</p>
      </div>
    </div>

    <template v-else-if="connected && !showSettings">
      <App @settings="openSettings" />
    </template>

    <ConnectionPicker
      v-else
      :active-connection="activeConnection"
      @connected="handleConnected"
      @disconnect="disconnect"
      @back="closeSettings"
    />
  </div>
</template>
