<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

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

const renderedHtml = computed(() => {
  if (isUser.value || !props.message.text) {
    return ''
  }
  return marked.parse(props.message.text.trim())
})
</script>

<template>
  <div
    class="fade-in flex max-w-[720px] gap-3"
    :class="isUser ? 'self-end flex-row-reverse' : 'self-start'"
  >
    <div
      class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
      :class="
        isUser
          ? 'bg-[var(--bg-3)] text-[var(--text-1)]'
          : 'bg-[var(--accent-glow)] text-[var(--accent)]'
      "
    >
      {{ isUser ? 'Y' : 'F' }}
    </div>

    <div>
      <div
        v-if="isUser"
        class="break-words rounded-[14px] rounded-tr-[4px] bg-[var(--accent)] px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white whitespace-pre-wrap"
      >
        {{ message.text }}
      </div>
      <div
        v-else
        class="prose-agent break-words rounded-[14px] rounded-tl-[4px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-3.5 py-2.5 text-[13.5px] leading-relaxed text-[var(--text-0)]"
        v-html="renderedHtml"
      />
      <div
        class="mt-1 px-1 text-[11px] text-[var(--text-3)]"
        :class="isUser ? 'text-right' : 'text-left'"
      >
        {{ formattedTime }}
      </div>
    </div>
  </div>
</template>
