import type { DataVizPayload } from '../../types'
import { KpiCards } from './KpiCards'
import { ChartViewer } from './ChartViewer'
import { TableViewer } from './TableViewer'

interface Props {
  dataviz: DataVizPayload
}

export function DataVizViewer({ dataviz }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {dataviz.kpis && dataviz.kpis.length > 0 && <KpiCards kpis={dataviz.kpis} />}
      {dataviz.charts?.map((chart, i) => <ChartViewer key={i} chart={chart} />)}
      {dataviz.tables?.map((table, i) => <TableViewer key={i} table={table} />)}
    </div>
  )
}
