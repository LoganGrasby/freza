<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  detail: { type: String, default: '' },
  status: { type: String, default: 'running' },
})

const LABELS = {
  Read: ['Reading', 'Read'],
  Write: ['Writing', 'Wrote'],
  Edit: ['Editing', 'Edited'],
  Bash: ['Running', 'Ran'],
  Glob: ['Finding files', 'Found files'],
  Grep: ['Searching', 'Searched'],
  WebSearch: ['Searching web', 'Searched web'],
  WebFetch: ['Fetching', 'Fetched'],
  Agent: ['Running agent', 'Ran agent'],
}

const label = computed(() => {
  const pair = LABELS[props.name]
  if (!pair) return props.name
  return props.status === 'running' ? pair[0] : pair[1]
})

const shortDetail = computed(() => {
  if (!props.detail) return ''
  const d = props.detail
  if (d.length <= 50) return d
  const parts = d.split('/')
  if (parts.length > 2) {
    return '.../' + parts.slice(-2).join('/')
  }
  return d.slice(0, 47) + '...'
})
</script>

<template>
  <div class="flex items-center gap-1.5 py-[3px] text-[11px] leading-none">
    <span
      class="inline-block h-1 w-1 shrink-0 rounded-full"
      :class="{
        'bg-[var(--accent)] tool-pulse': status === 'running',
        'bg-[var(--text-3)]/40': status === 'done',
        'bg-[var(--red)]': status === 'error',
      }"
    />
    <span class="text-[var(--text-3)]">{{ label }}</span>
    <span
      v-if="shortDetail"
      class="truncate font-mono text-[var(--text-3)]/60"
    >{{ shortDetail }}</span>
  </div>
</template>

<style scoped>
.tool-pulse {
  animation: tool-glow 1.5s ease-in-out infinite;
}
@keyframes tool-glow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
