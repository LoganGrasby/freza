<script setup>
import { ref } from 'vue'
import SidebarNav from '@/components/layout/SidebarNav.vue'
import HistoryPanel from '@/components/chat/HistoryPanel.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import DiagnosticsPanel from '@/components/diagnostics/DiagnosticsPanel.vue'

const emit = defineEmits(['settings'])

const currentPanel = ref('chat')
const selectedAgent = ref('default')
const activeThreadId = ref(null)
const historyVisible = ref(true)
const chatPanel = ref(null)
const historyPanel = ref(null)

function selectThread(threadId, agentName) {
  activeThreadId.value = threadId
  chatPanel.value?.loadThread(threadId, agentName)
}

function startNewChat() {
  activeThreadId.value = null
  chatPanel.value?.handleNewChat()
}

function onThreadChanged(threadId) {
  activeThreadId.value = threadId
  historyPanel.value?.refresh()
}
</script>

<template>
  <div class="flex h-full overflow-hidden bg-[var(--bg-0)] text-[var(--text-0)]">
    <SidebarNav
      :current-panel="currentPanel"
      :history-visible="historyVisible"
      @update:current-panel="(panel) => (currentPanel = panel)"
      @settings="emit('settings')"
      @toggle-history="historyVisible = !historyVisible"
    />

    <HistoryPanel
      v-show="currentPanel === 'chat' && historyVisible"
      ref="historyPanel"
      :active-thread-id="activeThreadId"
      @select-thread="selectThread"
      @new-chat="startNewChat"
    />

    <ChatPanel
      v-show="currentPanel === 'chat'"
      ref="chatPanel"
      v-model:selected-agent="selectedAgent"
      @thread-changed="onThreadChanged"
    />

    <DiagnosticsPanel
      v-show="currentPanel === 'diag'"
      :active="currentPanel === 'diag'"
      :selected-agent="selectedAgent"
    />
  </div>
</template>
