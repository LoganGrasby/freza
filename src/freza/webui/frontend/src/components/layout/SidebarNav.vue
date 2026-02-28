<script setup>
const props = defineProps({
  currentPanel: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:currentPanel'])

function setPanel(panel) {
  emit('update:currentPanel', panel)
}
</script>

<template>
  <nav
    class="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-[var(--border-subtle)] bg-[var(--bg-1)] px-0 py-4"
  >
    <div
      class="mb-5 flex h-8 w-8 items-center justify-center rounded-md bg-[var(--accent)] text-sm font-bold text-white"
    >
      F
    </div>

    <button
      type="button"
      class="relative flex h-10 w-10 items-center justify-center rounded-[10px] text-[var(--text-2)] transition hover:bg-[var(--bg-3)] hover:text-[var(--text-1)]"
      :class="{
        'bg-[var(--accent-glow)] text-[var(--accent)] before:absolute before:-left-2 before:h-5 before:w-[3px] before:rounded-r-sm before:bg-[var(--accent)]':
          props.currentPanel === 'chat',
      }"
      title="Chat"
      @click="setPanel('chat')"
    >
      <svg
        class="h-5 w-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    </button>

    <button
      type="button"
      class="relative flex h-10 w-10 items-center justify-center rounded-[10px] text-[var(--text-2)] transition hover:bg-[var(--bg-3)] hover:text-[var(--text-1)]"
      :class="{
        'bg-[var(--accent-glow)] text-[var(--accent)] before:absolute before:-left-2 before:h-5 before:w-[3px] before:rounded-r-sm before:bg-[var(--accent)]':
          props.currentPanel === 'diag',
      }"
      title="Diagnostics"
      @click="setPanel('diag')"
    >
      <svg
        class="h-5 w-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    </button>

    <div class="flex-1" />

    <button
      type="button"
      class="flex h-10 w-10 cursor-default items-center justify-center rounded-[10px] text-[var(--text-3)]"
      title="Theme toggle unavailable"
      disabled
    >
      <svg
        class="h-5 w-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>
    </button>
  </nav>
</template>
