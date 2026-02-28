<script setup>
import { ref } from 'vue'
import SidebarNav from '@/components/layout/SidebarNav.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import DiagnosticsPanel from '@/components/diagnostics/DiagnosticsPanel.vue'

const currentPanel = ref('chat')
const selectedAgent = ref('default')
</script>

<template>
  <div class="flex h-full overflow-hidden bg-[var(--bg-0)] text-[var(--text-0)]">
    <SidebarNav
      :current-panel="currentPanel"
      @update:current-panel="(panel) => (currentPanel = panel)"
    />

    <ChatPanel
      v-show="currentPanel === 'chat'"
      v-model:selected-agent="selectedAgent"
    />

    <DiagnosticsPanel
      v-show="currentPanel === 'diag'"
      :active="currentPanel === 'diag'"
      :selected-agent="selectedAgent"
    />
  </div>
</template>
