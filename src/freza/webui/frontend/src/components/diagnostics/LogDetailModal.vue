<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { formatCost, formatDuration } from '@/lib/format'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  detail: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['close'])

const title = computed(() => {
  const runId = props.detail?.instance_id || props.detail?.file || 'unknown'
  return `Run: ${runId.slice(0, 16)}`
})

const toolList = computed(() => props.detail?.tools_used || [])

const conversation = computed(() => {
  const turns = props.detail?.conversation || []

  return turns
    .map((turn, index) => {
      const role = turn.role || 'unknown'
      const lines = []

      if (role === 'assistant' && Array.isArray(turn.content)) {
        for (const block of turn.content) {
          if (block.type === 'text') {
            lines.push(block.text)
          } else if (block.type === 'tool_use') {
            lines.push(`[Tool: ${block.name}]`)
            lines.push(JSON.stringify(block.input, null, 2).slice(0, 500))
          }
        }
      } else if (role === 'user' && Array.isArray(turn.content)) {
        for (const block of turn.content) {
          if (block.type === 'tool_result') {
            const resultContent =
              typeof block.content === 'string'
                ? block.content
                : JSON.stringify(block.content)

            lines.push(`[Result for: ${(block.tool_use_id || '').slice(0, 12)}]`)
            lines.push((resultContent || '').slice(0, 500))
          }
        }
      } else if (role === 'system') {
        lines.push(JSON.stringify(turn.data || turn, null, 2).slice(0, 500))
      } else if (role === 'result') {
        lines.push(JSON.stringify(turn, null, 2))
      }

      const content = lines.join('\n').trim()
      if (!content) {
        return null
      }

      return {
        key: `${role}-${index}`,
        role,
        label: `${role}${turn.subtype ? ` (${turn.subtype})` : ''}${turn.model ? ` · ${turn.model}` : ''}`,
        content,
      }
    })
    .filter(Boolean)
})

function roleClass(role) {
  if (role === 'assistant') {
    return 'text-[var(--accent)]'
  }
  if (role === 'user') {
    return 'text-[var(--green)]'
  }
  if (role === 'system') {
    return 'text-[var(--amber)]'
  }
  if (role === 'result') {
    return 'text-[var(--blue)]'
  }
  return 'text-[var(--text-2)]'
}

function close() {
  emit('close')
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    @click.self="close"
  >
    <div
      class="flex max-h-[85vh] w-[90vw] max-w-[900px] flex-col rounded-[14px] border border-[var(--border)] bg-[var(--bg-1)] shadow-[0_8px_32px_rgba(0,0,0,0.4)]"
    >
      <header class="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-4">
        <h3 class="text-[15px] font-semibold text-[var(--text-0)]">{{ title }}</h3>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--bg-3)] text-[var(--text-1)] transition hover:bg-[var(--red-dim)] hover:text-[var(--red)]"
          @click="close"
        >
          <svg
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      <div class="scrollbar-thin flex-1 overflow-y-auto px-5 py-5 text-[13px]">
        <div class="mb-5 grid grid-cols-[120px_1fr] gap-x-4 gap-y-2">
          <div class="text-xs font-medium text-[var(--text-2)]">Instance ID</div>
          <div class="text-[var(--text-0)]">
            <code>{{ detail?.instance_id || '-' }}</code>
          </div>
          <div class="text-xs font-medium text-[var(--text-2)]">Mode</div>
          <div class="text-[var(--text-0)]">{{ detail?.mode || '-' }}</div>
          <div class="text-xs font-medium text-[var(--text-2)]">Channel</div>
          <div class="text-[var(--text-0)]">{{ detail?.channel_name || '-' }}</div>
          <div class="text-xs font-medium text-[var(--text-2)]">Duration</div>
          <div class="text-[var(--text-0)]">{{ formatDuration(detail?.duration_seconds) }}</div>
          <div class="text-xs font-medium text-[var(--text-2)]">Cost</div>
          <div class="text-[var(--text-0)]">{{ formatCost(detail?.cost_usd) }}</div>
          <div class="text-xs font-medium text-[var(--text-2)]">Turns</div>
          <div class="text-[var(--text-0)]">{{ detail?.turns || '-' }}</div>
          <div class="text-xs font-medium text-[var(--text-2)]">Tools Used</div>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="tool in toolList"
              :key="tool"
              class="rounded bg-[var(--bg-3)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-2)]"
            >
              {{ tool }}
            </span>
            <span
              v-if="toolList.length === 0"
              class="text-[var(--text-2)]"
            >
              -
            </span>
          </div>
        </div>

        <section
          v-if="detail?.trigger_message"
          class="mb-4"
        >
          <h4 class="mb-2 text-sm font-semibold">Trigger</h4>
          <pre
            class="scrollbar-thin overflow-x-auto rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-[var(--text-1)]"
          >{{ detail.trigger_message }}</pre>
        </section>

        <section
          v-if="detail?.response"
          class="mb-4"
        >
          <h4 class="mb-2 text-sm font-semibold">Response</h4>
          <pre
            class="scrollbar-thin max-h-[300px] overflow-y-auto rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-[var(--text-1)]"
          >{{ detail.response }}</pre>
        </section>

        <section v-if="conversation.length > 0">
          <h4 class="mb-2 text-sm font-semibold">Conversation Trace</h4>
          <div class="flex flex-col gap-3">
            <article
              v-for="turn in conversation"
              :key="turn.key"
              class="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-3"
            >
              <div
                class="mb-1 text-[11px] font-semibold tracking-wide uppercase"
                :class="roleClass(turn.role)"
              >
                {{ turn.label }}
              </div>
              <pre
                class="scrollbar-thin max-h-[300px] overflow-y-auto font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-[var(--text-1)]"
              >{{ turn.content }}</pre>
            </article>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
