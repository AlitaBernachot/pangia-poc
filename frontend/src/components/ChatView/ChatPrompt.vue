<template>
  <div class="shrink-0 px-4 pb-5 pt-3">
    <div
      class="mx-auto max-w-3xl rounded-sm border border-white/10 bg-white/4 backdrop-blur flex flex-col focus-within:border-yellow-500/60 transition-colors duration-150"
      :class="{ 'opacity-60': isStreaming }"
    >
      <!-- Textarea -->
      <textarea
        ref="inputRef"
        v-model="draft"
        placeholder="Ask, search, or make anything…"
        rows="1"
        :disabled="isStreaming"
        class="w-full bg-transparent border-none outline-none resize-none text-sm text-white placeholder:text-white/30 leading-relaxed px-4 pt-4 pb-2 min-h-14 max-h-40 overflow-y-auto font-sans disabled:cursor-not-allowed"
        @keydown.enter.exact.prevent="handleSubmit"
        @input="autoResize"
      />
      <!-- Footer -->
      <div class="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
        <!-- Agent selector toggles -->
        <div class="flex items-center gap-1 flex-wrap">
          <Button severity="secondary" size="small" rounded text class="text-xs! text-white/50! gap-1.5!">
            <i class="pi pi-paperclip text-[11px]" />
            Attach
          </Button>
          <template v-if="availableAgents.length > 0">
            <button
              v-for="agent in availableAgents"
              :key="agent.key"
              type="button"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border transition-colors duration-150 cursor-pointer select-none"
              :class="isAgentSelected(agent.key)
                ? agentActiveClass(agent.label)
                : 'border-white/15 text-white/30 bg-transparent hover:text-white/50'"
              :title="`${isAgentSelected(agent.key) ? 'Deselect' : 'Select'} ${agent.label}`"
              @click="toggleAgent(agent.key)"
            >
              <span>{{ agentIcon(agent.label) }}</span>
              {{ agent.label }}
            </button>
          </template>
        </div>
        <Button
          icon="pi pi-arrow-up"
          rounded
          size="small"
          class="size-8! p-0! shrink-0"
          :disabled="!draft.trim() || isStreaming"
          aria-label="Send"
          @click="handleSubmit"
        />
      </div>
    </div>
    <p class="text-center text-xs text-white/20 mt-2">Enter to send · Shift+Enter for new line</p>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import Button from 'primevue/button'
import { type AgentInfo, agentIcon } from '@/types'

const props = defineProps<{
  isStreaming: boolean
  availableAgents: AgentInfo[]
  selectedAgents: string[]
}>()

const emit = defineEmits<{
  submit: [text: string]
  'update:selectedAgents': [keys: string[]]
}>()

const draft    = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)

/** Color classes for each agent when its toggle is active. */
const _agentColors: Record<string, string> = {
  'Neo4j':      'border-[#4ade80] text-[#4ade80] bg-[rgba(74,222,128,0.10)]',
  'RDF/SPARQL': 'border-[#fb923c] text-[#fb923c] bg-[rgba(251,146,60,0.10)]',
  'Vector':     'border-[#a78bfa] text-[#a78bfa] bg-[rgba(167,139,250,0.10)]',
  'PostGIS':    'border-[#38bdf8] text-[#38bdf8] bg-[rgba(56,189,248,0.10)]',
}
function agentActiveClass(label: string): string {
  return _agentColors[label] ?? 'border-white/40 text-white/80 bg-white/5'
}

function isAgentSelected(key: string): boolean {
  return props.selectedAgents.includes(key)
}

/** Toggle an agent on/off.  At least one must remain selected. */
function toggleAgent(key: string) {
  const current = props.selectedAgents
  if (current.includes(key)) {
    if (current.length > 1) {
      emit('update:selectedAgents', current.filter(k => k !== key))
    }
  } else {
    emit('update:selectedAgents', [...current, key])
  }
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

function handleSubmit() {
  const text = draft.value.trim()
  if (!text || props.isStreaming) return
  draft.value = ''
  autoResize()
  emit('submit', text)
}

function submitText(text: string) {
  draft.value = text
  nextTick(handleSubmit)
}

function focus() {
  nextTick(() => inputRef.value?.focus())
}

defineExpose({ submitText, focus })
</script>

