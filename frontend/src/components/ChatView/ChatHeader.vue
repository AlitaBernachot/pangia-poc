<template>
  <header class="shrink-0 flex items-center gap-3 px-6 py-4 border-b border-white/8">
    <span class="text-2xl">🌍</span>
    <div>
      <h1 class="text-2xl font-semibold leading-tight m-0 p-0">PangIA</h1>
      <p class="text-xs text-white/40 m-0 p-0">Multi-agent GeoIA · Neo4j · SPARQL · Vector · PostGIS</p>
    </div>
    <div class="ml-auto flex items-center gap-2">
      <span v-if="sessionId" class="text-xs text-white/30 font-mono">{{ sessionId.slice(0, 8) }}…</span>
      <Tag severity="success" value="Connected" />
    </div>
  </header>
</template>

<script setup lang="ts">
import Tag from 'primevue/tag'

defineProps<{ sessionId: string | null }>()
</script>
