<template>
  <div class="chat-container">
    <!-- ── Messages list ─────────────────────────────────────── -->
    <div class="messages-wrap" ref="messagesRef">
      <!-- Empty state -->
      <div v-if="messages.length === 0" class="empty-state">
        <span class="empty-icon">🌍</span>
        <p class="empty-title">Ask me anything about geography</p>
        <p class="empty-sub">I orchestrate Neo4j · RDF/SPARQL · Vector Search · PostGIS to answer your questions.</p>
        <div class="suggestions">
          <button
            v-for="s in suggestions"
            :key="s"
            class="suggestion-chip"
            @click="sendSuggestion(s)"
          >{{ s }}</button>
        </div>
      </div>

      <!-- Message bubbles -->
      <TransitionGroup name="msg" tag="div" class="message-list">
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="message-row"
          :class="msg.role"
        >
          <div class="avatar">
            <span v-if="msg.role === 'user'">👤</span>
            <span v-else>🤖</span>
          </div>

          <div class="bubble-wrap">
            <!-- Routing banner: which agents were selected -->
            <div v-if="msg.routingAgents && msg.routingAgents.length" class="routing-banner">
              <span class="routing-label">Routing to:</span>
              <span
                v-for="a in msg.routingAgents"
                :key="a"
                class="agent-pill"
                :class="a.toLowerCase().replace(/[^a-z]/g, '-')"
              >{{ a }}</span>
            </div>

            <!-- Sub-agent activity (thinking panels) -->
            <div
              v-if="msg.agentActivity && msg.agentActivity.length"
              class="agent-panels"
            >
              <details
                v-for="activity in msg.agentActivity"
                :key="activity.agent"
                class="agent-panel"
                :class="{ active: activity.streaming }"
              >
                <summary class="agent-panel-header">
                  <span class="agent-panel-icon">{{ agentIcon(activity.agent) }}</span>
                  <span class="agent-panel-name">{{ activity.agent }}</span>
                  <span class="agent-panel-status" :class="activity.streaming ? 'running' : 'done'">
                    {{ activity.streaming ? 'thinking…' : 'done' }}
                  </span>
                </summary>
                <div class="agent-panel-body">
                  <!-- Tool calls within this agent -->
                  <div v-if="activity.tools.length" class="tool-activity">
                    <span
                      v-for="(t, i) in activity.tools"
                      :key="i"
                      class="tool-badge"
                      :class="t.status"
                    >
                      <span class="tool-icon">🔍</span>
                      {{ t.tool }}
                      <span class="tool-status-dot" />
                    </span>
                  </div>
                  <!-- Intermediate reasoning text -->
                  <div v-if="activity.content" class="agent-reasoning">
                    <span v-html="renderContent(activity.content)" />
                    <span v-if="activity.streaming" class="cursor" />
                  </div>
                </div>
              </details>
            </div>

            <!-- Final answer bubble -->
            <div class="bubble" :class="{ streaming: msg.streaming }">
              <span v-html="renderContent(msg.content)" />
              <span v-if="msg.streaming && !msg.content" class="cursor" />
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- Typing indicator -->
      <div v-if="isThinking" class="message-row assistant">
        <div class="avatar"><span>🤖</span></div>
        <div class="bubble-wrap">
          <div class="bubble thinking">
            <span class="dot" /><span class="dot" /><span class="dot" />
          </div>
        </div>
      </div>
    </div>

    <!-- ── Input bar ──────────────────────────────────────────── -->
    <div class="input-bar">
      <!-- Agent selector (shown only when ≥ 1 agent is available) -->
      <div v-if="availableAgents.length > 0" class="agent-selector">
        <span class="agent-selector-label">Agents:</span>
        <button
          v-for="agent in availableAgents"
          :key="agent.key"
          class="agent-toggle"
          :class="[agent.key, { active: selectedAgents.includes(agent.key) }]"
          :title="`${selectedAgents.includes(agent.key) ? 'Deselect' : 'Select'} ${agent.label}`"
          @click="toggleAgent(agent.key)"
        >
          <span>{{ agentIcon(agent.label) }}</span>
          {{ agent.label }}
        </button>
      </div>

      <div class="input-wrap">
        <textarea
          ref="inputRef"
          v-model="draft"
          class="chat-input"
          placeholder="Ask a geographic question…"
          rows="1"
          :disabled="isStreaming"
          @keydown.enter.exact.prevent="sendMessage"
          @input="autoResize"
        />
        <button
          class="send-btn"
          :disabled="!draft.trim() || isStreaming"
          @click="sendMessage"
          title="Send (Enter)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
      <p class="input-hint">
        <span v-if="sessionId" class="session-id">Session: {{ sessionId.slice(0, 8) }}…</span>
        <span v-else>&nbsp;</span>
        <span>Enter to send · Shift+Enter for new line</span>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, reactive, onMounted } from 'vue'

/* ─── Types ──────────────────────────────────────────────────────────────────── */
interface ToolActivity { tool: string; status: 'running' | 'done' }
interface AgentActivity {
  agent: string
  content: string
  streaming: boolean
  tools: ToolActivity[]
}
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  /** Names of sub-agents selected by the router */
  routingAgents?: string[]
  /** Per-agent intermediate activity panels */
  agentActivity?: AgentActivity[]
}
interface AgentInfo {
  key: string
  label: string
}

/* ─── State ──────────────────────────────────────────────────────────────────── */
const messages    = ref<Message[]>([])
const draft       = ref('')
const sessionId   = ref<string | null>(null)
const isStreaming  = ref(false)
const isThinking   = ref(false)
const messagesRef  = ref<HTMLElement | null>(null)
const inputRef     = ref<HTMLTextAreaElement | null>(null)

/** Agents that are enabled in the backend configuration. */
const availableAgents = ref<AgentInfo[]>([])
/** Keys of agents the user currently wants to query (defaults to all active). */
const selectedAgents  = ref<string[]>([])

const suggestions = [
  'What are the largest countries by area?',
  'Find cities within 100 km of a major river using spatial data.',
  'Show semantic relationships between mountain ranges.',
  'Query RDF data about European capitals.',
]

/* ─── Lifecycle ───────────────────────────────────────────────────────────────── */
onMounted(async () => {
  try {
    const res = await fetch('/api/agents')
    if (res.ok) {
      const data = await res.json()
      availableAgents.value = data.agents as AgentInfo[]
      // Default: all active agents selected
      selectedAgents.value = availableAgents.value.map(a => a.key)
    }
  } catch {
    // Silently ignore – backend will use all active agents as fallback
  }
})

/* ─── Helpers ─────────────────────────────────────────────────────────────────── */
let _idCounter = 0
const uid = () => `msg-${++_idCounter}`

const AGENT_ICONS: Record<string, string> = {
  'Neo4j': '🔷',
  'RDF/SPARQL': '🔗',
  'Vector': '🧲',
  'PostGIS': '🗺️',
  'Synthesiser': '✨',
}
function agentIcon(agent: string): string {
  return AGENT_ICONS[agent] ?? '🤖'
}

/** Toggle an agent on/off.  At least one agent must remain selected. */
function toggleAgent(key: string) {
  const idx = selectedAgents.value.indexOf(key)
  if (idx >= 0) {
    if (selectedAgents.value.length > 1) {
      selectedAgents.value = selectedAgents.value.filter(k => k !== key)
    }
  } else {
    selectedAgents.value = [...selectedAgents.value, key]
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

function renderContent(text: string): string {
  // Minimal markdown: bold, code spans, line breaks
  // Use [^*]+ and [^`]+ to avoid ReDoS via catastrophic backtracking
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br/>')
}

/* ─── Send message ─────────────────────────────────────────────────────────── */
async function sendSuggestion(text: string) {
  draft.value = text
  await sendMessage()
}

async function sendMessage() {
  const text = draft.value.trim()
  if (!text || isStreaming.value) return

  draft.value = ''
  autoResize()

  messages.value.push({ id: uid(), role: 'user', content: text })
  scrollToBottom()

  isThinking.value = true
  isStreaming.value = true

  const aiId = uid()
  const aiMsg = reactive<Message>({
    id: aiId,
    role: 'assistant',
    content: '',
    streaming: true,
    routingAgents: [],
    agentActivity: [],
  })

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: sessionId.value,
        selected_agents: selectedAgents.value,
      }),
    })

    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    if (!response.body)  throw new Error('No response body')

    const reader  = response.body.getReader()
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
        const payload = line.slice(6).trim()
        if (!payload) continue

        let event: Record<string, string | string[]>
        try { event = JSON.parse(payload) } catch { continue }

        switch (event.type) {
          case 'session':
            sessionId.value = event.session_id as string
            break

          // ── Routing decision ──────────────────────────────────
          case 'routing': {
            const agents = event.agents as string[]
            aiMsg.routingAgents = agents
            // Pre-create activity panels for each agent
            aiMsg.agentActivity = agents.map(a => ({
              agent: a,
              content: '',
              streaming: true,
              tools: [],
            }))
            scrollToBottom()
            break
          }

          // ── Final synthesis tokens ────────────────────────────
          case 'token':
            // Mark all sub-agent panels as done once synthesis starts
            aiMsg.agentActivity?.forEach(a => { a.streaming = false })
            aiMsg.content += event.content as string
            scrollToBottom()
            break

          // ── Sub-agent intermediate tokens ─────────────────────
          case 'agent_token': {
            const agentLabel = event.agent as string
            let panel = aiMsg.agentActivity?.find(a => a.agent === agentLabel)
            if (!panel) {
              panel = { agent: agentLabel, content: '', streaming: true, tools: [] }
              aiMsg.agentActivity?.push(panel)
            }
            panel.content += event.content as string
            scrollToBottom()
            break
          }

          // ── Tool lifecycle ────────────────────────────────────
          case 'tool_start': {
            const agentLabel = event.agent as string
            const panel = aiMsg.agentActivity?.find(a => a.agent === agentLabel)
            if (panel) {
              panel.tools.push({ tool: event.tool as string, status: 'running' })
            }
            break
          }

          case 'tool_end': {
            const agentLabel = event.agent as string
            const panel = aiMsg.agentActivity?.find(a => a.agent === agentLabel)
            if (panel) {
              const t = panel.tools.find(
                tt => tt.tool === event.tool && tt.status === 'running'
              )
              if (t) t.status = 'done'
            }
            break
          }

          case 'error':
            aiMsg.content += `\n\n⚠️ ${event.content as string}`
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
    const message = err instanceof Error ? err.message : String(err)
    if (!messages.value.find(m => m.id === aiId)) {
      messages.value.push(aiMsg)
    }
    aiMsg.content = `⚠️ Connection error: ${message}`
    aiMsg.streaming = false
  } finally {
    isStreaming.value = false
    scrollToBottom()
    nextTick(() => inputRef.value?.focus())
  }
}
</script>

<style scoped>
/* ─── Layout ───────────────────────────────────────────────────────────────── */
.chat-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.messages-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0;
  scroll-behavior: smooth;
}

.message-list { display: flex; flex-direction: column; gap: 0; }

/* ─── Empty state ──────────────────────────────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 3rem 1rem;
  text-align: center;
  gap: 0.6rem;
}
.empty-icon { font-size: 3rem; }
.empty-title { font-size: 1.25rem; font-weight: 600; color: var(--color-text); }
.empty-sub   { color: var(--color-text-muted); font-size: 0.9rem; max-width: 380px; }

.suggestions { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center; margin-top: 0.75rem; }
.suggestion-chip {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-radius: 999px;
  padding: 0.35rem 0.85rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.suggestion-chip:hover { background: var(--color-primary); border-color: var(--color-primary); }

/* ─── Message rows ─────────────────────────────────────────────────────────── */
.message-row {
  display: flex;
  gap: 0.75rem;
  padding: 0.5rem 0;
  align-items: flex-start;
}
.message-row.user { flex-direction: row-reverse; }

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-surface-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  flex-shrink: 0;
  margin-top: 2px;
}

.bubble-wrap { display: flex; flex-direction: column; gap: 0.4rem; max-width: min(72%, 760px); }

/* ─── Routing banner ───────────────────────────────────────────────────────── */
.routing-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.routing-label { font-weight: 500; color: var(--color-text-muted); }
.agent-pill {
  display: inline-flex;
  align-items: center;
  padding: 0.18rem 0.6rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 500;
  border: 1px solid;
}
.agent-pill.neo4j      { color: #4ade80; border-color: #4ade80; background: rgba(74,222,128,0.08); }
.agent-pill.rdf-sparql { color: #f59e0b; border-color: #f59e0b; background: rgba(245,158,11,0.08); }
.agent-pill.vector     { color: #a78bfa; border-color: #a78bfa; background: rgba(167,139,250,0.08); }
.agent-pill.postgis    { color: #38bdf8; border-color: #38bdf8; background: rgba(56,189,248,0.08); }

/* ─── Sub-agent activity panels ────────────────────────────────────────────── */
.agent-panels { display: flex; flex-direction: column; gap: 0.3rem; }

.agent-panel {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}
.agent-panel.active { border-color: var(--color-primary); }
.agent-panel summary { list-style: none; }
.agent-panel summary::-webkit-details-marker { display: none; }

.agent-panel-header {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.4rem 0.75rem;
  cursor: pointer;
  font-size: 0.8rem;
  user-select: none;
}
.agent-panel-header:hover { background: rgba(255,255,255,0.04); }
.agent-panel-icon  { font-size: 0.9rem; }
.agent-panel-name  { flex: 1; font-weight: 500; color: var(--color-text); }
.agent-panel-status {
  font-size: 0.7rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  border: 1px solid;
}
.agent-panel-status.running { color: var(--color-accent); border-color: var(--color-accent); animation: pulse 1.4s ease-in-out infinite; }
.agent-panel-status.done    { color: #4ade80; border-color: #4ade80; }
@keyframes pulse { 50% { opacity: 0.5; } }

.agent-panel-body {
  padding: 0.5rem 0.75rem 0.6rem;
  border-top: 1px solid var(--color-border);
}

/* ─── Tool activity ────────────────────────────────────────────────────────── */
.tool-activity { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.4rem; }
.tool-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  font-size: 0.74rem;
  color: var(--color-text-muted);
}
.tool-badge.running { border-color: var(--color-accent); color: var(--color-accent); }
.tool-badge.done    { border-color: #22c55e; color: #22c55e; }
.tool-icon { font-size: 0.8rem; }
.tool-status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

/* ─── Agent reasoning text ─────────────────────────────────────────────────── */
.agent-reasoning {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ─── Bubble ───────────────────────────────────────────────────────────────── */
.bubble {
  background: var(--color-ai-bubble);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 0.7rem 1rem;
  font-size: 0.92rem;
  line-height: 1.65;
  word-break: break-word;
  position: relative;
}
.message-row.user .bubble {
  background: var(--color-user-bubble);
  border-color: var(--color-user-bubble);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.message-row.assistant .bubble { border-bottom-left-radius: 4px; }
.bubble.streaming { border-color: var(--color-primary); }

/* Cursor blink */
.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--color-accent);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 0.8s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* Typing dots */
.bubble.thinking {
  display: flex;
  gap: 5px;
  align-items: center;
  padding: 0.75rem 1.1rem;
}
.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--color-text-muted);
  animation: bounce 1.1s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.18s; }
.dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.75); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

/* ─── Inline code ──────────────────────────────────────────────────────────── */
:deep(code) {
  background: rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 0.1em 0.35em;
  font-size: 0.88em;
  font-family: 'Fira Mono', 'Consolas', monospace;
}

/* ─── Agent selector ────────────────────────────────────────────────────────── */
.agent-selector {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 0.5rem 0.25rem 0.35rem;
}

.agent-selector-label {
  font-size: 0.72rem;
  color: var(--color-text-muted);
  font-weight: 500;
  flex-shrink: 0;
}

.agent-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.18rem 0.65rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  transition: background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s;
  user-select: none;
}
.agent-toggle:hover { opacity: 0.85; }

/* Active (selected) state per agent */
.agent-toggle.active.neo4j    { color: #4ade80; border-color: #4ade80; background: rgba(74,222,128,0.10); }
.agent-toggle.active.rdf      { color: #f59e0b; border-color: #f59e0b; background: rgba(245,158,11,0.10); }
.agent-toggle.active.vector   { color: #a78bfa; border-color: #a78bfa; background: rgba(167,139,250,0.10); }
.agent-toggle.active.postgis  { color: #38bdf8; border-color: #38bdf8; background: rgba(56,189,248,0.10); }

/* ─── Input bar ─────────────────────────────────────────────────────────────── */
.input-bar {
  flex-shrink: 0;
  padding: 0.75rem 1rem 0.6rem;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
}
.input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 0.5rem 0.5rem 0.5rem 1rem;
  transition: border-color 0.15s;
}
.input-wrap:focus-within { border-color: var(--color-primary); }

.chat-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-text);
  font-size: 0.92rem;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
  max-height: 160px;
  overflow-y: auto;
}
.chat-input::placeholder { color: var(--color-text-muted); }
.chat-input:disabled { opacity: 0.5; cursor: not-allowed; }

.send-btn {
  flex-shrink: 0;
  width: 36px; height: 36px;
  border-radius: 8px;
  background: var(--color-primary);
  border: none;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, opacity 0.15s;
}
.send-btn:hover:not(:disabled) { background: var(--color-primary-hover); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.input-hint {
  display: flex;
  justify-content: space-between;
  font-size: 0.72rem;
  color: var(--color-text-muted);
  margin-top: 0.4rem;
  padding: 0 0.25rem;
}

/* ─── List transition ───────────────────────────────────────────────────────── */
.msg-enter-active { transition: all 0.25s ease; }
.msg-enter-from { opacity: 0; transform: translateY(10px); }
</style>


