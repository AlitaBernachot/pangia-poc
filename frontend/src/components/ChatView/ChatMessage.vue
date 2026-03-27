<template>
  <ChatUserMessage v-if="msg.role === 'user'" :msg="msg" />
  <ChatAgentMessage v-else :msg="msg" />
</template>

<script setup lang="ts">
import ChatUserMessage from './ChatUserMessage.vue'
import ChatAgentMessage from './ChatAgentMessage.vue'
import { type Message } from '@/types'

defineProps<{ msg: Message }>()
</script>
