<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import ToolEvent from '@/components/chat/ToolEvent.vue'

marked.setOptions({
  breaks: true,
  gfm: true,
})

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const formattedTime = computed(() => {
  if (!props.message.time) {
    return ''
  }
  return new Date(props.message.time).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
})

const isUser = computed(() => props.message.role === 'user')

const hasBlocks = computed(() => {
  return !isUser.value && props.message.blocks && props.message.blocks.length > 0
})

// Group consecutive tool blocks together and render text blocks as HTML
const renderedBlocks = computed(() => {
  if (!hasBlocks.value) return []
  const out = []
  let toolGroup = null

  for (const block of props.message.blocks) {
    if (block.kind === 'tool') {
      if (!toolGroup) {
        toolGroup = { kind: 'tools', items: [] }
        out.push(toolGroup)
      }
      toolGroup.items.push(block)
    } else {
      toolGroup = null
      if (block.kind === 'text' && block.text?.trim()) {
        out.push({ ...block, html: marked.parse(block.text.trim()) })
      } else if (block.kind === 'result') {
        out.push(block)
      }
    }
  }
  return out
})

const fallbackHtml = computed(() => {
  if (isUser.value || hasBlocks.value || !props.message.text) {
    return ''
  }
  return marked.parse(props.message.text.trim())
})

function formatDuration(ms) {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatCost(usd) {
  if (!usd) return ''
  return `$${usd.toFixed(4)}`
}
</script>

<template>
  <!-- User message: compact, right-aligned -->
  <div
    v-if="isUser"
    class="fade-in flex max-w-[560px] gap-3 self-end flex-row-reverse"
  >
    <div
      class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--bg-3)] text-xs font-semibold text-[var(--text-1)]"
    >
      Y
    </div>
    <div>
      <div
        class="break-words rounded-[14px] rounded-tr-[4px] bg-[var(--accent)] px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white whitespace-pre-wrap"
      >
        {{ message.text }}
      </div>
      <div class="mt-1 px-1 text-right text-[11px] text-[var(--text-3)]">
        {{ formattedTime }}
      </div>
    </div>
  </div>

  <!-- Agent message: full width -->
  <div
    v-else
    class="fade-in w-full self-start"
  >
    <!-- With blocks -->
    <div v-if="hasBlocks">
      <template v-for="(block, i) in renderedBlocks" :key="i">
        <div
          v-if="block.kind === 'text' && block.html"
          class="prose-agent break-words px-1 py-1 text-[14px] leading-[1.7] text-[var(--text-0)]"
          v-html="block.html"
        />
        <div
          v-else-if="block.kind === 'tools'"
          class="my-1.5 rounded-lg border border-[var(--border-subtle)]/40 bg-[var(--bg-1)] px-3 py-1"
        >
          <ToolEvent
            v-for="(tool, j) in block.items"
            :key="j"
            :name="tool.name"
            :detail="tool.detail"
            :status="tool.status"
          />
        </div>
        <div
          v-else-if="block.kind === 'result'"
          class="mt-3 flex items-center gap-2.5 border-t border-[var(--border-subtle)]/30 pt-2 text-[10.5px] text-[var(--text-3)]"
        >
          <span v-if="block.turns">{{ block.turns }} {{ block.turns === 1 ? 'turn' : 'turns' }}</span>
          <span v-if="block.turns && block.cost_usd" class="text-[var(--border)]">&middot;</span>
          <span v-if="block.cost_usd">{{ formatCost(block.cost_usd) }}</span>
          <span v-if="block.cost_usd && block.duration_ms" class="text-[var(--border)]">&middot;</span>
          <span v-if="block.duration_ms">{{ formatDuration(block.duration_ms) }}</span>
        </div>
      </template>
    </div>

    <!-- Without blocks (fallback) -->
    <div
      v-else
      class="prose-agent break-words px-1 py-1 text-[14px] leading-[1.7] text-[var(--text-0)]"
      v-html="fallbackHtml"
    />

    <div class="mt-1 px-1 text-[11px] text-[var(--text-3)]">
      {{ formattedTime }}
    </div>
  </div>
</template>
