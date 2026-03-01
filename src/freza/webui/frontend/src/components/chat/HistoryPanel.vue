<script setup>
import { ref, computed, onMounted } from 'vue'
import { getJson } from '@/lib/api'

const props = defineProps({
  activeThreadId: { type: String, default: null },
})

const emit = defineEmits(['select-thread', 'new-chat'])

const threads = ref([])
const loading = ref(true)

async function refresh() {
  try {
    threads.value = await getJson('/api/threads')
  } catch {
    threads.value = []
  } finally {
    loading.value = false
  }
}

defineExpose({ refresh })

onMounted(refresh)

function dateGroup(ts) {
  const now = new Date()
  const d = new Date(ts * 1000)
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const week = new Date(today)
  week.setDate(week.getDate() - 7)

  if (d >= today) return 'Today'
  if (d >= yesterday) return 'Yesterday'
  if (d >= week) return 'Previous 7 Days'
  return 'Older'
}

const grouped = computed(() => {
  const groups = []
  let currentGroup = null
  for (const t of threads.value) {
    const group = dateGroup(t.last_timestamp)
    if (group !== currentGroup) {
      currentGroup = group
      groups.push({ label: group, items: [] })
    }
    groups[groups.length - 1].items.push(t)
  }
  return groups
})

function truncate(text, len) {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}
</script>

<template>
  <aside
    class="scrollbar-thin flex w-[260px] shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-1)]"
  >
    <div class="flex items-center gap-2 px-3 pt-4 pb-2">
      <button
        class="flex h-9 flex-1 items-center justify-center gap-2 rounded-lg border border-[var(--border)] text-xs text-[var(--text-1)] transition hover:bg-[var(--bg-3)]"
        @click="emit('new-chat')"
      >
        <svg
          class="h-3.5 w-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New Chat
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-2 pb-4">
      <div v-if="loading" class="px-2 py-8 text-center text-xs text-[var(--text-3)]">
        Loading...
      </div>

      <div v-else-if="threads.length === 0" class="px-2 py-8 text-center text-xs text-[var(--text-3)]">
        No conversations yet
      </div>

      <template v-else>
        <div v-for="group in grouped" :key="group.label" class="mb-1">
          <div class="px-2 pt-3 pb-1 text-[10px] font-medium tracking-wider text-[var(--text-3)] uppercase">
            {{ group.label }}
          </div>
          <button
            v-for="t in group.items"
            :key="t.thread_id"
            class="group flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition"
            :class="
              activeThreadId === t.thread_id
                ? 'bg-[var(--accent-glow)] text-[var(--text-0)]'
                : 'text-[var(--text-1)] hover:bg-[var(--bg-3)]'
            "
            @click="emit('select-thread', t.thread_id, t.agent)"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] leading-snug">
                {{ truncate(t.title, 40) }}
              </div>
              <div class="mt-0.5 flex items-center gap-1.5 text-[10px] text-[var(--text-3)]">
                <span
                  v-if="t.agent && t.agent !== 'default'"
                  class="rounded bg-[var(--bg-3)] px-1 py-px font-medium"
                >{{ t.agent }}</span>
                <span v-if="t.channel && t.channel !== 'webui'" class="opacity-70">{{ t.channel }}</span>
                <span>{{ t.message_count }}{{ t.message_count === 1 ? ' msg' : ' msgs' }}</span>
              </div>
            </div>
          </button>
        </div>
      </template>
    </div>
  </aside>
</template>
