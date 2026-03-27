<template>
  <div class="kpi-grid">
    <div
      v-for="(kpi, i) in kpis"
      :key="i"
      class="kpi-card rounded-xl border border-white/10 bg-white/3 p-3 flex flex-col gap-1"
    >
      <span class="text-[11px] text-white/50 font-medium uppercase tracking-wide leading-none">
        {{ kpi.label }}
      </span>
      <div class="flex items-end gap-1.5">
        <span class="text-2xl font-bold text-white/90 leading-none tabular-nums">
          {{ kpi.value }}
        </span>
        <span v-if="kpi.unit" class="text-sm text-white/50 mb-0.5">{{ kpi.unit }}</span>
      </div>
      <div class="flex items-center gap-2 mt-0.5">
        <span
          v-if="kpi.variation"
          class="text-xs font-semibold px-1.5 py-0.5 rounded-full"
          :class="variationClass(kpi)"
        >
          {{ trendIcon(kpi.trend) }} {{ kpi.variation }}
        </span>
        <span v-if="kpi.threshold" class="text-[10px] text-white/35 italic">
          {{ kpi.threshold }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DataVizKpi } from '@/types'

defineProps<{ kpis: DataVizKpi[] }>()

function trendIcon(trend: DataVizKpi['trend']): string {
  if (trend === 'up') return '↑'
  if (trend === 'down') return '↓'
  return '→'
}

function variationClass(kpi: DataVizKpi): string {
  if (kpi.trend === 'up') return 'bg-green-500/20 text-green-400'
  if (kpi.trend === 'down') return 'bg-red-500/20 text-red-400'
  return 'bg-white/10 text-white/50'
}
</script>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 0.5rem;
}
</style>
