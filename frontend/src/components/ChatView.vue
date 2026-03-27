<template>
  <div class="flex flex-col h-full">
    <ChatHeader :session-id="sessionId" />
    <ChatMessages
      ref="chatMessagesRef"
      :messages="messages"
      :is-thinking="isThinking"
      :suggestions="suggestions"
      @suggest="handleSuggest"
    />
    <ChatPrompt
      ref="chatPromptRef"
      :is-streaming="isStreaming"
      :available-agents="availableAgents"
      :selected-agents="selectedAgents"
      @submit="send"
      @update:selected-agents="selectedAgents = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import ChatHeader from './ChatView/ChatHeader.vue'
import ChatMessages from './ChatView/ChatMessages.vue'
import ChatPrompt from './ChatView/ChatPrompt.vue'
import { type Message, type AgentInfo, type DataVizPayload } from '@/types'

const suggestions    = ref<string[]>([])
const messages    = ref<Message[]>([])
const sessionId   = ref<string | null>(null)
const isStreaming  = ref(false)
const isThinking   = ref(false)

/** Agents that are currently enabled in the backend configuration. */
const availableAgents = ref<AgentInfo[]>([])
/** Agent keys the user currently wants to query (defaults to all active). */
const selectedAgents  = ref<string[]>([])

const chatMessagesRef = ref<InstanceType<typeof ChatMessages> | null>(null)
const chatPromptRef   = ref<InstanceType<typeof ChatPrompt>   | null>(null)

let _id = 0
const uid = () => `m${++_id}`

onMounted(async () => {
  // Fetch theme suggestions
  try {
    const res = await fetch('/api/suggestions')
    if (res.ok) {
      const data = await res.json()
      suggestions.value = data.suggestions ?? []
    }
  } catch { /* silently ignore */ }

  // Fetch available agents from backend config
  try {
    const res = await fetch('/api/agents')
    if (res.ok) {
      const data = await res.json()
      availableAgents.value = data.agents as AgentInfo[]
      // Default: all active agents selected
      selectedAgents.value = availableAgents.value.map(a => a.key)
    }
  } catch { /* silently ignore */ }
})

function handleSuggest(text: string) {
  chatPromptRef.value?.submitText(text)
}

async function send(text: string) {
  if (!text || isStreaming.value) return

  messages.value.push({ id: uid(), role: 'user', content: text })
  chatMessagesRef.value?.scrollToBottom()

  isThinking.value = true
  isStreaming.value = true

  const aiId = uid()
  const aiMsg = reactive<Message>({
    id: aiId, role: 'assistant', content: '', streaming: true,
    routingAgents: [], agentActivity: [],
  })

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: sessionId.value, selected_agents: selectedAgents.value }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    if (!res.body) throw new Error('No body')

    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    let   buffer  = ''

    messages.value.push(aiMsg)
    isThinking.value = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        let ev: Record<string, string | string[]>
        try { ev = JSON.parse(raw) } catch { continue }

        switch (ev.type) {
          case 'session':
            sessionId.value = ev.session_id as string
            break
          case 'routing': {
            const agents = ev.agents as string[]
            aiMsg.routingAgents = agents
            aiMsg.agentActivity = agents.map(a => ({ agent: a, content: '', streaming: true, tools: [] }))
            chatMessagesRef.value?.scrollToBottom()
            break
          }
          case 'token':
            aiMsg.agentActivity?.forEach(a => { a.streaming = false })
            aiMsg.content += ev.content as string
            chatMessagesRef.value?.scrollToBottom()
            break
          case 'agent_token': {
            const lbl = ev.agent as string
            let p = aiMsg.agentActivity?.find(a => a.agent === lbl)
            if (!p) { p = { agent: lbl, content: '', streaming: true, tools: [] }; aiMsg.agentActivity?.push(p) }
            p.content += ev.content as string
            chatMessagesRef.value?.scrollToBottom()
            break
          }
          case 'tool_start': {
            const p = aiMsg.agentActivity?.find(a => a.agent === ev.agent)
            if (p) p.tools.push({ tool: ev.tool as string, status: 'running' })
            break
          }
          case 'tool_end': {
            const p = aiMsg.agentActivity?.find(a => a.agent === ev.agent)
            if (p) { const t = p.tools.find(tt => tt.tool === ev.tool && tt.status === 'running'); if (t) t.status = 'done' }
            break
          }
          case 'error':
            aiMsg.content += `\n\n⚠️ ${ev.content as string}`
            break
          case 'geojson':
            aiMsg.geojson = ev.data as unknown as Record<string, unknown>
            chatMessagesRef.value?.scrollToBottom()
            break
          case 'dataviz':
            aiMsg.dataviz = ev.data as unknown as DataVizPayload
            chatMessagesRef.value?.scrollToBottom()
            break
          case 'done':
            aiMsg.streaming = false
            aiMsg.agentActivity?.forEach(a => { a.streaming = false })
            break
        }
      }
    }
  } catch (err: unknown) {
    isThinking.value = false
    if (!messages.value.find(m => m.id === aiId)) messages.value.push(aiMsg)
    aiMsg.content = `⚠️ ${err instanceof Error ? err.message : String(err)}`
    aiMsg.streaming = false
  } finally {
    isStreaming.value = false
    chatMessagesRef.value?.scrollToBottom()
    nextTick(() => chatPromptRef.value?.focus())
  }
}
</script>
    <!-- Header -->
