<template>
  <div class="flex gap-3 items-start">
    <Avatar icon="pi pi-globe" shape="circle" size="small" class="shrink-0 mt-1 bg-yellow-500/20! text-yellow-300!" />

    <div class="flex flex-col gap-2.5 min-w-0 flex-1 max-w-[82%]">

      <!-- Routing chips -->
      <div v-if="msg.routingAgents?.length" class="flex items-center flex-wrap gap-1.5">
        <span class="text-xs text-white/40 font-medium">Routing to</span>
        <span
          v-for="a in msg.routingAgents"
          :key="a"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border"
          :style="agentChipStyle(a)"
        >{{ agentIcon(a) }} {{ a }}</span>
      </div>

      <!-- Agent activity panels -->
      <div v-if="msg.agentActivity?.length" class="flex flex-col gap-1.5">
        <Fieldset
          v-for="activity in msg.agentActivity"
          :key="activity.agent"
          toggleable
          v-model:collapsed="collapsed[activity.agent]"
          :pt="{
            root: { class: 'pb-0!' },
            content: { class: 'p-3 pb-0 text-xs' },
          }"
        >
          <template #legend>
            <div
              class="flex items-center gap-2 px-3 py-1.5 text-xs"
              @click="collapsed[activity.agent] = !collapsed[activity.agent]"
            >
              <i class="pi text-[10px] text-white/40" :class="collapsed[activity.agent] ? 'pi-chevron-right' : 'pi-chevron-down'" />
              <span class="text-sm">{{ agentIcon(activity.agent) }}</span>
              <span class="font-medium">{{ activity.agent }}</span>
              <span
                class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] border"
                :class="activity.streaming
                  ? 'text-amber-400 border-amber-400 animate-pulse'
                  : 'text-green-400 border-green-400'"
              >{{ activity.streaming ? 'thinking…' : 'done' }}</span>
            </div>
          </template>

          <!-- Tool badges -->
          <div v-if="activity.tools.length" class="flex flex-wrap gap-1.5 mb-2">
            <span
              v-for="(t, i) in activity.tools"
              :key="i"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] border"
              :class="t.status === 'running' ? 'text-amber-400 border-amber-400' : 'text-green-400 border-green-400'"
            >
              <i class="pi pi-search text-[10px]" />
              {{ t.tool }}
              <span class="size-1.5 rounded-full bg-current" />
            </span>
          </div>

          <!-- Reasoning text -->
          <div v-if="activity.content" class="text-white/50 leading-snug whitespace-pre-wrap break-words prose-msg">
            <span v-html="renderContent(activity.content)" />
            <span v-if="activity.streaming" class="cursor-blink" />
          </div>
        </Fieldset>
      </div>

      <!-- Final answer -->
      <div
        v-if="msg.content || msg.streaming"
        class="bg-white/4 border border-white/8 rounded-xl rounded-tl-none px-4 py-3 text-sm leading-relaxed prose-msg"
        :class="{ 'border-violet-500/50': msg.streaming }"
      >
        <span v-html="renderContent(msg.content)" />
        <span v-if="msg.streaming && !msg.content" class="cursor-blink" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import Avatar from 'primevue/avatar'
import Fieldset from 'primevue/fieldset'
import { type Message, AGENT_COLORS, agentIcon, renderContent } from '@/types'

const props = defineProps<{ msg: Message }>()

const collapsed = reactive<Record<string, boolean>>({})
const autoManaged = new Set<string>()

watch(
  () => props.msg.agentActivity,
  (activities) => {
    for (const activity of activities ?? []) {
      if (!(activity.agent in collapsed)) {
        collapsed[activity.agent] = false
        autoManaged.add(activity.agent)
      }
      if (!activity.streaming && autoManaged.has(activity.agent)) {
        collapsed[activity.agent] = true
        autoManaged.delete(activity.agent)
      }
    }
  },
  { deep: true, immediate: true }
)

function agentChipStyle(agent: string) {
  const c = AGENT_COLORS[agent]
  return c ? { color: c.text, borderColor: c.border, background: c.bg } : {}
}
</script>

<style scoped>
.cursor-blink {
  display: inline-block;
  width: 2px; height: 1em;
  background: currentColor;
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 0.8s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
</style>
