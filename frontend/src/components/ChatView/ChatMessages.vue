<template>
  <div ref="scrollRef" class="flex-1 overflow-y-auto px-4 py-6 flex flex-col gap-6">

    <!-- Empty state -->
    <div v-if="messages.length === 0" class="flex flex-col items-center justify-center flex-1 gap-4 text-center py-16">
      <span class="text-6xl">🌍</span>
      <h2 class="text-xl font-semibold">Ask me anything about geography</h2>
      <p class="text-white/40 text-sm max-w-md">
        I orchestrate Neo4j, RDF/SPARQL, Vector Search and PostGIS to answer your questions.
      </p>
      <div class="flex flex-wrap gap-2 justify-center mt-2">
        <Button
          v-for="s in suggestions"
          :key="s"
          severity="secondary"
          size="small"
          rounded
          class="text-xs!"
          @click="emit('suggest', s)"
        >{{ s }}</Button>
      </div>
    </div>

    <!-- Messages -->
    <ChatMessage v-for="msg in messages" :key="msg.id" :msg="msg" />

    <!-- Thinking indicator -->
    <div v-if="isThinking" class="flex gap-3 items-start">
      <Avatar icon="pi pi-bolt" shape="circle" size="small" class="shrink-0 mt-1 bg-violet-600/30! text-violet-300!" />
      <div class="bg-white/4 border border-white/8 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1.5 items-center">
        <span class="dot" /><span class="dot" /><span class="dot" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import Avatar from 'primevue/avatar'
import Button from 'primevue/button'
import ChatMessage from './ChatMessage.vue'
import type { Message } from '@/types'

defineProps<{
  messages: Message[]
  isThinking: boolean
  suggestions: string[]
}>()

const emit = defineEmits<{ suggest: [text: string] }>()

const scrollRef = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

defineExpose({ scrollToBottom })
</script>

<style scoped>
.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: rgba(255,255,255,0.4);
  animation: bounce 1.1s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.18s; }
.dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
  40%           { transform: scale(1);   opacity: 1;   }
}
</style>
