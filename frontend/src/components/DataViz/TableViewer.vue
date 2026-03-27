<template>
  <div class="table-wrapper rounded-xl border border-white/10 bg-white/3 overflow-hidden">
    <div v-if="table.title" class="px-3 py-2 border-b border-white/8 text-sm font-semibold text-white/80">
      {{ table.title }}
    </div>
    <DataTable
      :value="rows"
      size="small"
      scrollable
      scrollHeight="240px"
      :pt="{
        root: { class: 'text-xs' },
        thead: { class: 'sticky top-0' },
        tbody: { class: '' },
      }"
    >
      <Column
        v-for="col in table.columns"
        :key="col"
        :field="col"
        :header="col"
        :pt="{
          headerCell: { class: 'bg-white/5 text-white/60 font-semibold text-[11px] py-1.5 px-2 border-b border-white/8' },
          bodyCell: { class: 'text-white/75 text-[11px] py-1 px-2 border-b border-white/5' },
        }"
      />
    </DataTable>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import type { DataVizTable } from '@/types'

const props = defineProps<{ table: DataVizTable }>()

const rows = computed(() =>
  props.table.rows.map(row => {
    const obj: Record<string, string | number> = {}
    props.table.columns.forEach((col, i) => {
      obj[col] = row[i] ?? ''
    })
    return obj
  })
)
</script>
