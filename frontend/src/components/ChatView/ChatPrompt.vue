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
        <div class="flex items-center gap-1">
          <Button severity="secondary" size="small" rounded text class="text-xs! text-white/50! gap-1.5!">
            <i class="pi pi-paperclip text-[11px]" />
            Attach
          </Button>
          <Button severity="secondary" size="small" rounded text class="text-xs! text-white/50! gap-1.5!">
            <i class="pi pi-globe text-[11px]" />
            All Sources
          </Button>
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

const props = defineProps<{ isStreaming: boolean }>()
const emit = defineEmits<{ submit: [text: string] }>()

const draft    = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)

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
