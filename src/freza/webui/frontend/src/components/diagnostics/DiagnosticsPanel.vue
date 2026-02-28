<script setup>
import { computed, ref, watch } from 'vue'
import LogDetailModal from '@/components/diagnostics/LogDetailModal.vue'
import { getJson } from '@/lib/api'
import { formatCost, formatDuration, formatTimestamp } from '@/lib/format'

const props = defineProps({
  active: {
    type: Boolean,
    default: false,
  },
  selectedAgent: {
    type: String,
    default: 'default',
  },
})

const section = ref('overview')
const stats = ref({
  total_runs: 0,
  total_cost_usd: 0,
  total_duration_s: 0,
  channel_counts: {},
})
const overviewInstanceCount = ref(0)
const logs = ref([])
const instances = ref([])
const shortTerm = ref([])
const memoryContent = ref('(empty)')
const channels = ref([])
const agents = ref([])
const detailOpen = ref(false)
const selectedLogDetail = ref(null)

const navItems = [
  { key: 'overview', label: 'Overview' },
  { key: 'logs', label: 'Logs' },
  { key: 'instances', label: 'Instances' },
  { key: 'memory', label: 'Memory' },
  { key: 'channels', label: 'Channels' },
  { key: 'agents', label: 'Agents' },
]

const statCards = computed(() => {
  const baseCards = [
    {
      key: 'total-runs',
      label: 'Total Runs',
      value: stats.value.total_runs,
      valueClass: 'text-[var(--accent)]',
    },
    {
      key: 'total-cost',
      label: 'Total Cost',
      value: `$${Number(stats.value.total_cost_usd || 0).toFixed(2)}`,
      valueClass: 'text-[var(--text-0)]',
    },
    {
      key: 'total-duration',
      label: 'Total Duration',
      value: formatDuration(stats.value.total_duration_s),
      valueClass: 'text-[var(--text-0)]',
    },
    {
      key: 'active-instances',
      label: 'Active Instances',
      value: overviewInstanceCount.value,
      valueClass: 'text-[var(--green)]',
    },
  ]

  const channelCards = Object.entries(stats.value.channel_counts || {}).map(
    ([channel, count]) => ({
      key: `channel-${channel}`,
      label: `${channel} runs`,
      value: count,
      valueClass: 'text-[var(--text-0)]',
    }),
  )

  return [...baseCards, ...channelCards]
})

const mergedInstances = computed(() => {
  const map = new Map()

  for (const instance of instances.value) {
    map.set(instance.instance_id, {
      id: instance.instance_id,
      mode: instance.mode,
      channel: instance.channel_name,
      status: instance.status || 'running',
      task: null,
      started: instance.started_at,
    })
  }

  for (const item of shortTerm.value) {
    const existing = map.get(item.instance_id)
    if (existing) {
      existing.task = item.current_task
      existing.status = item.status || existing.status
    } else {
      map.set(item.instance_id, {
        id: item.instance_id,
        mode: item.mode,
        channel: item.channel_name,
        status: item.status || 'unknown',
        task: item.current_task,
        started: item.started_at,
      })
    }
  }

  return [...map.values()]
})

function statusClass(status) {
  if (status === 'running') {
    return 'bg-[var(--green-dim)] text-[var(--green)]'
  }

  if (status === 'failed') {
    return 'bg-[var(--red-dim)] text-[var(--red)]'
  }

  return 'bg-[var(--bg-3)] text-[var(--text-2)]'
}

function channelTagClass(channel) {
  return channel === 'webui'
    ? 'bg-[var(--blue-dim)] text-[var(--blue)]'
    : 'bg-[var(--bg-3)] text-[var(--text-2)]'
}

async function loadOverview() {
  const [statsData, instanceData] = await Promise.all([
    getJson('/api/stats'),
    getJson('/api/instances'),
  ])

  stats.value = {
    total_runs: statsData.total_runs || 0,
    total_cost_usd: statsData.total_cost_usd || 0,
    total_duration_s: statsData.total_duration_s || 0,
    channel_counts: statsData.channel_counts || {},
  }
  overviewInstanceCount.value = instanceData.length
}

async function loadLogs() {
  logs.value = await getJson('/api/logs?limit=100')
}

async function loadInstances() {
  const [instanceData, shortTermData] = await Promise.all([
    getJson('/api/instances'),
    getJson('/api/short-term'),
  ])

  instances.value = instanceData
  shortTerm.value = shortTermData
}

async function loadMemory() {
  const agent = props.selectedAgent || 'default'
  const data = await getJson(`/api/memory?agent=${encodeURIComponent(agent)}`)
  memoryContent.value = data.content || '(empty)'
}

async function loadChannels() {
  channels.value = await getJson('/api/channels')
}

async function loadAgents() {
  agents.value = await getJson('/api/agents')
}

async function loadSection(key = section.value) {
  try {
    if (key === 'overview') {
      await loadOverview()
    } else if (key === 'logs') {
      await loadLogs()
    } else if (key === 'instances') {
      await loadInstances()
    } else if (key === 'memory') {
      await loadMemory()
    } else if (key === 'channels') {
      await loadChannels()
    } else if (key === 'agents') {
      await loadAgents()
    }
  } catch (error) {
    console.error(`Failed to load ${key}:`, error)
  }
}

async function openLogDetail(file) {
  try {
    selectedLogDetail.value = await getJson(`/api/logs/${encodeURIComponent(file)}`)
    detailOpen.value = true
  } catch (error) {
    console.error('Failed to load log detail:', error)
  }
}

watch(
  () => props.active,
  (isActive) => {
    if (isActive) {
      void loadOverview()
      void loadSection(section.value)
    }
  },
  { immediate: true },
)

watch(section, () => {
  if (props.active) {
    void loadSection(section.value)
  }
})

watch(
  () => props.selectedAgent,
  () => {
    if (props.active && section.value === 'memory') {
      void loadMemory()
    }
  },
)
</script>

<template>
  <section class="flex min-w-0 flex-1 flex-col">
    <header
      class="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border-subtle)] px-6"
    >
      <svg
        class="h-5 w-5 text-[var(--accent)]"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
      <h2 class="text-[15px] font-semibold">Diagnostics</h2>
    </header>

    <div class="flex min-h-0 flex-1 overflow-hidden">
      <nav
        class="flex w-[200px] shrink-0 flex-col gap-0.5 border-r border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 py-4"
      >
        <button
          v-for="item in navItems"
          :key="item.key"
          type="button"
          class="flex items-center rounded-md px-3 py-2 text-left text-[13px] text-[var(--text-1)] transition hover:bg-[var(--bg-3)] hover:text-[var(--text-0)]"
          :class="{
            'bg-[var(--accent-glow)] text-[var(--accent)]': section === item.key,
          }"
          @click="section = item.key"
        >
          {{ item.label }}
        </button>
      </nav>

      <main class="scrollbar-thin flex-1 overflow-y-auto p-6">
        <section v-if="section === 'overview'">
          <div class="mb-4 flex items-center gap-2 text-[13px] font-semibold text-[var(--text-0)]">
            System Overview
            <button
              type="button"
              class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-2)] transition hover:text-[var(--accent)]"
              @click="loadOverview"
            >
              <svg
                class="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-1.98-9.74L23 10" />
              </svg>
            </button>
          </div>

          <div class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
            <article
              v-for="card in statCards"
              :key="card.key"
              class="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-4"
            >
              <div class="mb-1.5 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                {{ card.label }}
              </div>
              <div class="text-2xl font-semibold" :class="card.valueClass">{{ card.value }}</div>
            </article>
          </div>
        </section>

        <section v-else-if="section === 'logs'">
          <div class="mb-4 flex items-center gap-2 text-[13px] font-semibold text-[var(--text-0)]">
            Run History
            <button
              type="button"
              class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-2)] transition hover:text-[var(--accent)]"
              @click="loadLogs"
            >
              <svg
                class="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-1.98-9.74L23 10" />
              </svg>
            </button>
          </div>

          <div class="overflow-x-auto rounded-[10px] border border-[var(--border-subtle)]">
            <table class="w-full border-collapse text-left">
              <thead class="bg-[var(--bg-1)]">
                <tr>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Time
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Agent
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Channel
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Duration
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Cost
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Turns
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Tools
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Trigger
                  </th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="log in logs"
                  :key="log.file"
                  class="cursor-pointer border-t border-[var(--border-subtle)] text-[13px] text-[var(--text-1)] transition hover:bg-[var(--bg-hover)]"
                  @click="openLogDetail(log.file)"
                >
                  <td class="px-3 py-2.5">{{ formatTimestamp(log.timestamp) }}</td>
                  <td class="px-3 py-2.5">
                    <span class="rounded-full bg-[var(--accent-glow)] px-2 py-0.5 text-[11px] text-[var(--accent)]">
                      {{ log.agent || 'default' }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">
                    <span
                      class="rounded-full px-2 py-0.5 text-[11px]"
                      :class="channelTagClass(log.channel)"
                    >
                      {{ log.channel || log.mode }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">{{ formatDuration(log.duration) }}</td>
                  <td class="px-3 py-2.5">{{ formatCost(log.cost) }}</td>
                  <td class="px-3 py-2.5">{{ log.turns || '-' }}</td>
                  <td class="px-3 py-2.5">
                    <div class="flex flex-wrap gap-1">
                      <span
                        v-for="tool in (log.tools || []).slice(0, 5)"
                        :key="tool"
                        class="rounded bg-[var(--bg-3)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-2)]"
                      >
                        {{ tool }}
                      </span>
                      <span
                        v-if="(log.tools || []).length > 5"
                        class="rounded bg-[var(--bg-3)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-2)]"
                      >
                        +{{ log.tools.length - 5 }}
                      </span>
                    </div>
                  </td>
                  <td class="max-w-[220px] truncate px-3 py-2.5">
                    {{ log.trigger || '' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-else-if="section === 'instances'">
          <div class="mb-4 flex items-center gap-2 text-[13px] font-semibold text-[var(--text-0)]">
            Active Instances
            <button
              type="button"
              class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-2)] transition hover:text-[var(--accent)]"
              @click="loadInstances"
            >
              <svg
                class="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-1.98-9.74L23 10" />
              </svg>
            </button>
          </div>

          <div
            v-if="mergedInstances.length === 0"
            class="flex flex-col items-center justify-center gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] py-16 text-[var(--text-2)]"
          >
            <svg
              class="h-10 w-10 opacity-30"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <p>No active instances</p>
          </div>

          <div
            v-else
            class="overflow-x-auto rounded-[10px] border border-[var(--border-subtle)]"
          >
            <table class="w-full border-collapse text-left">
              <thead class="bg-[var(--bg-1)]">
                <tr>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Instance
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Mode
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Channel
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Status
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Task
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Started
                  </th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="item in mergedInstances"
                  :key="item.id"
                  class="border-t border-[var(--border-subtle)] text-[13px] text-[var(--text-1)]"
                >
                  <td class="px-3 py-2.5 font-mono text-xs">{{ item.id?.slice(0, 12) || '-' }}</td>
                  <td class="px-3 py-2.5">{{ item.mode || '-' }}</td>
                  <td class="px-3 py-2.5">{{ item.channel || '-' }}</td>
                  <td class="px-3 py-2.5">
                    <span
                      class="rounded-full px-2 py-0.5 text-[11px]"
                      :class="statusClass(item.status)"
                    >
                      {{ item.status }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">{{ item.task || '-' }}</td>
                  <td class="px-3 py-2.5">{{ formatTimestamp(item.started) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-else-if="section === 'memory'">
          <div class="mb-4 flex items-center gap-2 text-[13px] font-semibold text-[var(--text-0)]">
            Long-Term Memory
            <button
              type="button"
              class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-2)] transition hover:text-[var(--accent)]"
              @click="loadMemory"
            >
              <svg
                class="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-1.98-9.74L23 10" />
              </svg>
            </button>
          </div>

          <pre
            class="scrollbar-thin max-h-[calc(100vh-140px)] overflow-y-auto rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-5 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-[var(--text-1)]"
          >{{ memoryContent }}</pre>
        </section>

        <section v-else-if="section === 'channels'">
          <div class="mb-4 flex items-center gap-2 text-[13px] font-semibold text-[var(--text-0)]">
            Registered Channels
            <button
              type="button"
              class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-2)] transition hover:text-[var(--accent)]"
              @click="loadChannels"
            >
              <svg
                class="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-1.98-9.74L23 10" />
              </svg>
            </button>
          </div>

          <div
            v-if="channels.length === 0"
            class="flex flex-col items-center justify-center gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] py-16 text-[var(--text-2)]"
          >
            <p>No channels registered</p>
          </div>

          <div
            v-else
            class="overflow-x-auto rounded-[10px] border border-[var(--border-subtle)]"
          >
            <table class="w-full border-collapse text-left">
              <thead class="bg-[var(--bg-1)]">
                <tr>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Name
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Description
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Created
                  </th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="channel in channels"
                  :key="channel.name"
                  class="border-t border-[var(--border-subtle)] text-[13px] text-[var(--text-1)]"
                >
                  <td class="px-3 py-2.5">
                    <span class="rounded-full bg-[var(--blue-dim)] px-2 py-0.5 text-[11px] text-[var(--blue)]">
                      {{ channel.name }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">{{ channel.description || '' }}</td>
                  <td class="px-3 py-2.5">{{ formatTimestamp(channel.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-else>
          <div class="mb-4 flex items-center gap-2 text-[13px] font-semibold text-[var(--text-0)]">
            Registered Agents
            <button
              type="button"
              class="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-2)] transition hover:text-[var(--accent)]"
              @click="loadAgents"
            >
              <svg
                class="h-3.5 w-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-1.98-9.74L23 10" />
              </svg>
            </button>
          </div>

          <div
            v-if="agents.length === 0"
            class="flex flex-col items-center justify-center gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] py-16 text-[var(--text-2)]"
          >
            <p>No agents registered</p>
          </div>

          <div
            v-else
            class="overflow-x-auto rounded-[10px] border border-[var(--border-subtle)]"
          >
            <table class="w-full border-collapse text-left">
              <thead class="bg-[var(--bg-1)]">
                <tr>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Name
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Description
                  </th>
                  <th class="px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--text-2)] uppercase">
                    Created
                  </th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="agent in agents"
                  :key="agent.name"
                  class="border-t border-[var(--border-subtle)] text-[13px] text-[var(--text-1)]"
                >
                  <td class="px-3 py-2.5">
                    <span class="rounded-full bg-[var(--accent-glow)] px-2 py-0.5 text-[11px] text-[var(--accent)]">
                      {{ agent.name }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">{{ agent.description || '' }}</td>
                  <td class="px-3 py-2.5">{{ formatTimestamp(agent.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>

    <LogDetailModal
      :open="detailOpen"
      :detail="selectedLogDetail"
      @close="detailOpen = false"
    />
  </section>
</template>
