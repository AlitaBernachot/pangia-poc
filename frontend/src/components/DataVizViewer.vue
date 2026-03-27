<template>
  <div class="dataviz-wrapper flex flex-col gap-3">
    <!-- KPI cards -->
    <KpiCards v-if="dataviz.kpis?.length" :kpis="dataviz.kpis" />

    <!-- Charts (one per chart object) -->
    <ChartViewer
      v-for="(chart, i) in dataviz.charts"
      :key="i"
      :chart="chart"
    />

    <!-- Tables (one per table object) -->
    <TableViewer
      v-for="(table, j) in dataviz.tables"
      :key="j"
      :table="table"
    />
  </div>
</template>

<script setup lang="ts">
import type { DataVizPayload } from '@/types'
import ChartViewer from './DataViz/ChartViewer.vue'
import KpiCards from './DataViz/KpiCards.vue'
import TableViewer from './DataViz/TableViewer.vue'

defineProps<{ dataviz: DataVizPayload }>()
</script>
