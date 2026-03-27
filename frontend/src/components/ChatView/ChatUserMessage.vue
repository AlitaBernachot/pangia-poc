<template>
  <div class="flex justify-end gap-3">
    <div class="max-w-[72%] bg-white/8 border border-white/10 rounded-xl rounded-tr-none px-4 py-3 text-sm leading-relaxed">
      {{ msg.content }}
    </div>
    <Avatar icon="pi pi-user" shape="circle" size="small" class="shrink-0 mt-1 bg-white/10! text-white/50!" />
  </div>
</template>

<script setup lang="ts">
import Avatar from 'primevue/avatar'
import { type Message } from '@/types'

defineProps<{ msg: Message }>()
</script>
