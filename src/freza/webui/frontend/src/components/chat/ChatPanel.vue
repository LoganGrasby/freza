<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import { getJson, postJson, sseUrl } from '@/lib/api'

const props = defineProps({
  selectedAgent: {
    type: String,
    default: 'default',
  },
})

const emit = defineEmits(['update:selectedAgent', 'thread-changed'])

const agents = ref([])
const streaming = ref(false)
const inputText = ref('')
const messages = ref([])
const statusText = ref('ready')
const statusColor = ref('var(--green)')
const chatInput = ref(null)
const chatMessages = ref(null)

const threadIdsByAgent = new Map()
let currentStream = null

const selectedAgentModel = computed({
  get: () => props.selectedAgent || 'default',
  set: (value) => emit('update:selectedAgent', value || 'default'),
})

function makeMessage(role, text) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    blocks: [],
    time: Date.now(),
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (!chatMessages.value) {
      return
    }
    chatMessages.value.scrollTop = chatMessages.value.scrollHeight
  })
}

function resizeInput() {
  if (!chatInput.value) {
    return
  }
  chatInput.value.style.height = 'auto'
  chatInput.value.style.height = `${Math.min(chatInput.value.scrollHeight, 160)}px`
}

function setStatus(text, colorToken) {
  statusText.value = text
  statusColor.value = `var(--${colorToken})`
}

async function loadAgentSelector() {
  try {
    const fetchedAgents = await getJson('/api/agents')
    agents.value = fetchedAgents.length ? fetchedAgents : [{ name: 'default' }]

    const isCurrentAvailable = agents.value.some((agent) => agent.name === selectedAgentModel.value)
    if (!isCurrentAvailable) {
      selectedAgentModel.value = agents.value[0].name
    }
  } catch {
    agents.value = [{ name: 'default' }]
    selectedAgentModel.value = 'default'
  }
}

function handleNewChat() {
  if (streaming.value) {
    return
  }
  const agent = selectedAgentModel.value || 'default'
  threadIdsByAgent.delete(agent)
  messages.value = []
  inputText.value = ''
  resizeInput()
  emit('thread-changed', null)
  nextTick(() => chatInput.value?.focus())
}

async function loadThread(threadId, agentName) {
  if (streaming.value) return
  try {
    const entries = await getJson(`/api/threads/${threadId}`)
    if (!entries.length) return
    messages.value = []
    const agent = agentName || entries[0].agent || 'default'
    selectedAgentModel.value = agent
    threadIdsByAgent.set(agent, threadId)
    for (const entry of entries) {
      if (entry.trigger_message) {
        messages.value.push(makeMessage('user', entry.trigger_message))
      }
      if (entry.response) {
        messages.value.push(makeMessage('agent', entry.response))
      }
    }
    scrollToBottom()
    nextTick(() => chatInput.value?.focus())
  } catch {
    // silently fail
  }
}

defineExpose({ loadThread, handleNewChat })

function finishStreaming() {
  streaming.value = false
  setStatus('ready', 'green')

  if (currentStream) {
    currentStream.close()
    currentStream = null
  }

  const agent = selectedAgentModel.value || 'default'
  const threadId = threadIdsByAgent.get(agent)
  emit('thread-changed', threadId || null)
}

function handleInputKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) {
    return
  }

  messages.value.push(makeMessage('user', text))
  inputText.value = ''
  resizeInput()
  scrollToBottom()

  streaming.value = true
  setStatus('thinking', 'amber')

  try {
    const agent = selectedAgentModel.value || 'default'
    const body = {
      message: text,
      agent,
    }

    const threadId = threadIdsByAgent.get(agent)
    if (threadId) {
      body.thread_id = threadId
    }

    const chatStart = await postJson('/api/chat', body)
    if (!chatStart.proc_id) {
      throw new Error('No proc_id returned')
    }

    if (chatStart.thread_id) {
      threadIdsByAgent.set(agent, chatStart.thread_id)
    }

    messages.value.push(makeMessage('agent', ''))
    const agentIdx = messages.value.length - 1
    scrollToBottom()

    setStatus('streaming', 'green')

    let fullText = ''
    let blockText = ''
    currentStream = new EventSource(sseUrl(`/api/stream/${chatStart.proc_id}`))

    currentStream.onmessage = (event) => {
      const payload = JSON.parse(event.data)
      const msg = messages.value[agentIdx]

      if (payload.done) {
        if (!fullText.trim()) {
          msg.text = '(Agent completed with no text output)'
        }
        finishStreaming()
        return
      }

      if (payload.text) {
        fullText += payload.text
        blockText += payload.text
        msg.text = fullText
        const lastBlock = msg.blocks[msg.blocks.length - 1]
        if (lastBlock && lastBlock.kind === 'text') {
          lastBlock.text = blockText
        } else {
          msg.blocks.push({ kind: 'text', text: blockText })
        }
        scrollToBottom()
      } else if (payload.type === 'tool_use') {
        blockText = ''
        msg.blocks.push({
          kind: 'tool',
          toolId: payload.tool_id,
          name: payload.name,
          detail: payload.detail || '',
          status: 'running',
        })
        setStatus(payload.name, 'amber')
        scrollToBottom()
      } else if (payload.type === 'tool_result') {
        const tool = msg.blocks.find(
          (b) => b.kind === 'tool' && b.toolId === payload.tool_id
        )
        if (tool) {
          tool.status = payload.is_error ? 'error' : 'done'
        }
        setStatus('streaming', 'green')
        scrollToBottom()
      } else if (payload.type === 'result') {
        msg.blocks.push({
          kind: 'result',
          cost_usd: payload.cost_usd,
          turns: payload.turns,
          duration_ms: payload.duration_ms,
        })
        scrollToBottom()
      }
    }

    currentStream.onerror = () => {
      if (!fullText.trim()) {
        messages.value[agentIdx].text = '(Connection lost)'
      }
      finishStreaming()
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    messages.value.push(makeMessage('agent', `Error: ${message}`))

    streaming.value = false
    setStatus('error', 'red')
    window.setTimeout(() => setStatus('ready', 'green'), 3000)
  }
}

onMounted(async () => {
  await loadAgentSelector()
  nextTick(() => {
    chatInput.value?.focus()
    resizeInput()
  })
})

onBeforeUnmount(() => {
  if (currentStream) {
    currentStream.close()
  }
})
</script>

<template>
  <section class="flex min-w-0 flex-1 flex-col">
    <header
      class="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border-subtle)] px-6"
    >
      <div
        class="h-2 w-2 rounded-full"
        :style="{
          background: statusColor,
          boxShadow: `0 0 8px ${statusColor}`,
        }"
      />
      <h2 class="text-[15px] font-semibold">freza</h2>
      <span class="text-xs text-[var(--text-2)]">{{ statusText }}</span>

      <select
        v-model="selectedAgentModel"
        class="ml-2 rounded-md border border-[var(--border)] bg-[var(--bg-2)] px-2 py-1 text-xs text-[var(--text-1)] outline-none focus:border-[var(--accent)]"
        title="Select agent"
      >
        <option
          v-for="agent in agents"
          :key="agent.name"
          :value="agent.name"
        >
          {{ agent.name }}
        </option>
      </select>

      <div class="flex-1" />

      <button
        type="button"
        class="flex h-10 items-center gap-1.5 rounded-[10px] px-3 text-xs text-[var(--text-2)] transition hover:bg-[var(--bg-3)] hover:text-[var(--text-1)]"
        :disabled="streaming"
        title="New chat"
        @click="handleNewChat"
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
    </header>

    <div
      ref="chatMessages"
      class="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-6"
    >
      <div
        v-if="messages.length === 0"
        class="m-auto flex max-w-md flex-col items-center gap-4 px-6 text-center"
      >
        <div
          class="flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--accent-glow)]"
        >
          <svg
            class="h-8 w-8 text-[var(--accent)]"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <h3 class="text-xl font-semibold">Welcome</h3>
        <p class="text-sm text-[var(--text-2)]">
          Send a message to your autonomous agent. It has full access to bash, file editing,
          web search, and more.
        </p>
      </div>

      <ChatMessage
        v-for="message in messages"
        :key="message.id"
        :message="message"
      />
    </div>

    <footer class="shrink-0 border-t border-[var(--border-subtle)] px-6 py-4">
      <div
        class="flex items-end gap-2.5 rounded-[14px] border border-[var(--border)] bg-[var(--bg-2)] px-3 py-2 transition focus-within:border-[var(--accent)] focus-within:shadow-[0_0_0_3px_var(--accent-glow)]"
      >
        <textarea
          ref="chatInput"
          v-model="inputText"
          rows="1"
          class="max-h-40 min-h-6 flex-1 resize-none border-none bg-transparent text-sm leading-relaxed text-[var(--text-0)] outline-none placeholder:text-[var(--text-3)]"
          placeholder="Message your agent..."
          @input="resizeInput"
          @keydown="handleInputKeydown"
        />

        <button
          type="button"
          class="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-[var(--accent)] text-white transition hover:scale-105 hover:bg-[var(--accent-dim)] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
          :disabled="streaming"
          title="Send"
          @click="sendMessage"
        >
          <svg
            class="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </footer>
  </section>
</template>
