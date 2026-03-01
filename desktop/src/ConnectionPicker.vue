<script setup>
import { ref, onMounted, computed } from 'vue'
import { getConnections, saveConnection, deleteConnection } from './lib/connections'
import { setBaseUrl, setAuthToken, getJson } from '@/lib/api'

const props = defineProps({
  activeConnection: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['connected', 'disconnect', 'back'])

const connections = ref([])
const showForm = ref(false)
const editing = ref(null)
const form = ref({ name: '', url: '', token: '' })
const testResult = ref(null)
const testing = ref(false)

const hasActiveConnection = computed(() => !!props.activeConnection)

onMounted(async () => {
  connections.value = await getConnections()
  if (connections.value.length === 0) {
    showForm.value = true
  }
})

function resetForm() {
  form.value = { name: '', url: '', token: '' }
  editing.value = null
  testResult.value = null
}

function startEdit(conn) {
  form.value = { name: conn.name, url: conn.url, token: conn.token }
  editing.value = conn.id
  showForm.value = true
  testResult.value = null
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    setBaseUrl(form.value.url.replace(/\/+$/, ''))
    setAuthToken(form.value.token || null)
    await getJson('/api/ping')
    testResult.value = { ok: true, message: 'Connected successfully' }
  } catch (e) {
    testResult.value = { ok: false, message: e.message }
  } finally {
    if (hasActiveConnection.value) {
      setBaseUrl(props.activeConnection.url)
      setAuthToken(props.activeConnection.token || null)
    } else {
      setBaseUrl('')
      setAuthToken(null)
    }
    testing.value = false
  }
}

async function submitForm() {
  const conn = {
    id: editing.value || crypto.randomUUID(),
    name: form.value.name || form.value.url,
    url: form.value.url.replace(/\/+$/, ''),
    token: form.value.token || '',
    lastUsed: Date.now(),
  }
  await saveConnection(conn)
  connections.value = await getConnections()
  resetForm()
  showForm.value = connections.value.length === 0
}

async function connect(conn) {
  conn.lastUsed = Date.now()
  await saveConnection(conn)
  setBaseUrl(conn.url)
  setAuthToken(conn.token || null)
  emit('connected', conn)
}

async function remove(id) {
  await deleteConnection(id)
  connections.value = await getConnections()
}
</script>

<template>
  <div class="flex h-full items-center justify-center bg-[var(--bg-0)]">
    <div class="w-full max-w-lg px-6">
      <div class="mb-8 text-center">
        <div
          class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--accent-glow)]"
        >
          <span class="text-2xl font-bold text-[var(--accent)]">F</span>
        </div>
        <h1 class="text-xl font-semibold text-[var(--text-0)]">
          {{ hasActiveConnection ? 'Connections' : 'Connect to Freza' }}
        </h1>
        <p v-if="!hasActiveConnection" class="mt-1 text-sm text-[var(--text-2)]">
          Add a freza instance to get started
        </p>
      </div>

      <!-- Active connection indicator -->
      <div
        v-if="hasActiveConnection && !showForm"
        class="mb-4 flex items-center gap-3 rounded-xl border border-[var(--accent-dim)] bg-[var(--accent-glow)] px-4 py-3"
      >
        <div class="h-2 w-2 shrink-0 rounded-full bg-[var(--green)]" />
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium text-[var(--text-0)]">
            {{ activeConnection.name }}
          </div>
          <div class="truncate text-xs text-[var(--text-2)]">{{ activeConnection.url }}</div>
        </div>
        <button
          class="shrink-0 text-xs text-[var(--text-2)] hover:text-[var(--red)]"
          @click="emit('disconnect')"
        >
          Disconnect
        </button>
      </div>

      <!-- Saved connections -->
      <div v-if="connections.length > 0 && !showForm" class="space-y-2">
        <div
          v-for="conn in connections"
          :key="conn.id"
          class="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-1)] px-4 py-3 transition hover:border-[var(--accent-dim)]"
          :class="{ 'opacity-50': hasActiveConnection && conn.id === activeConnection?.id }"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-[var(--text-0)]">
              {{ conn.name }}
            </div>
            <div class="truncate text-xs text-[var(--text-2)]">{{ conn.url }}</div>
          </div>
          <button
            class="shrink-0 text-xs text-[var(--text-2)] hover:text-[var(--text-0)]"
            @click="startEdit(conn)"
          >
            Edit
          </button>
          <button
            class="shrink-0 text-xs text-[var(--text-2)] hover:text-[var(--red)]"
            @click="remove(conn.id)"
          >
            Delete
          </button>
          <button
            v-if="!hasActiveConnection || conn.id !== activeConnection?.id"
            class="shrink-0 rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white transition hover:bg-[var(--accent-dim)]"
            @click="connect(conn)"
          >
            Connect
          </button>
        </div>

        <button
          class="mt-4 w-full rounded-xl border border-dashed border-[var(--border)] py-3 text-sm text-[var(--text-2)] transition hover:border-[var(--accent-dim)] hover:text-[var(--text-1)]"
          @click="showForm = true; resetForm()"
        >
          + Add Connection
        </button>
      </div>

      <!-- Add/Edit form -->
      <div
        v-if="showForm"
        class="rounded-xl border border-[var(--border)] bg-[var(--bg-1)] p-5"
      >
        <h3 class="mb-4 text-sm font-semibold text-[var(--text-0)]">
          {{ editing ? 'Edit Connection' : 'New Connection' }}
        </h3>

        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-xs text-[var(--text-2)]">Name</label>
            <input
              v-model="form.name"
              type="text"
              placeholder="My Server"
              class="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-2)] px-3 py-2 text-sm text-[var(--text-0)] outline-none placeholder:text-[var(--text-3)] focus:border-[var(--accent)]"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs text-[var(--text-2)]">Server URL</label>
            <input
              v-model="form.url"
              type="text"
              placeholder="http://localhost:7888"
              class="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-2)] px-3 py-2 text-sm text-[var(--text-0)] outline-none placeholder:text-[var(--text-3)] focus:border-[var(--accent)]"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs text-[var(--text-2)]">API Token</label>
            <input
              v-model="form.token"
              type="password"
              placeholder="Leave empty for local connections"
              class="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-2)] px-3 py-2 text-sm text-[var(--text-0)] outline-none placeholder:text-[var(--text-3)] focus:border-[var(--accent)]"
            />
          </div>
        </div>

        <!-- Test result -->
        <div
          v-if="testResult"
          class="mt-3 rounded-lg px-3 py-2 text-xs"
          :class="
            testResult.ok
              ? 'bg-[var(--green-dim)] text-[var(--green)]'
              : 'bg-[var(--red-dim)] text-[var(--red)]'
          "
        >
          {{ testResult.message }}
        </div>

        <div class="mt-4 flex gap-2">
          <button
            v-if="connections.length > 0"
            class="rounded-lg border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-2)] transition hover:bg-[var(--bg-3)]"
            @click="showForm = false; resetForm()"
          >
            Cancel
          </button>
          <div class="flex-1" />
          <button
            class="rounded-lg border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-1)] transition hover:bg-[var(--bg-3)]"
            :disabled="!form.url || testing"
            @click="testConnection"
          >
            {{ testing ? 'Testing...' : 'Test Connection' }}
          </button>
          <button
            class="rounded-lg bg-[var(--accent)] px-4 py-2 text-xs font-medium text-white transition hover:bg-[var(--accent-dim)]"
            :disabled="!form.url"
            @click="submitForm"
          >
            {{ editing ? 'Save' : 'Add' }}
          </button>
        </div>
      </div>

      <!-- Back button when opened from settings -->
      <button
        v-if="hasActiveConnection && !showForm"
        class="mt-6 w-full rounded-xl border border-[var(--border)] py-3 text-center text-sm text-[var(--text-2)] transition hover:bg-[var(--bg-2)] hover:text-[var(--text-1)]"
        @click="emit('back')"
      >
        Back
      </button>
    </div>
  </div>
</template>
