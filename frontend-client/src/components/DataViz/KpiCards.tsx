import type { DataVizKpi } from '../../types'

interface Props {
  kpis: DataVizKpi[]
}

function trendIcon(trend: DataVizKpi['trend']): string {
  if (trend === 'up') return '↑'
  if (trend === 'down') return '↓'
  return '→'
}

function variationClass(trend: DataVizKpi['trend']): string {
  if (trend === 'up') return 'bg-green-500/20 text-green-400'
  if (trend === 'down') return 'bg-red-500/20 text-red-400'
  return 'bg-white/10 text-white/50'
}

export function KpiCards({ kpis }: Props) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))' }}>
      {kpis.map((kpi, i) => (
        <div
          key={i}
          className="rounded-xl border border-white/10 bg-white/3 p-3 flex flex-col gap-1"
        >
          <span className="text-[11px] text-white/50 font-medium uppercase tracking-wide leading-none">
            {kpi.label}
          </span>
          <div className="flex items-end gap-1.5">
            <span className="text-2xl font-bold text-white/90 leading-none tabular-nums">
              {kpi.value}
            </span>
            {kpi.unit && (
              <span className="text-sm text-white/50 mb-0.5">{kpi.unit}</span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            {kpi.variation && (
              <span className={`text-xs font-semibold px-1.5 py-0.5 rounded-full ${variationClass(kpi.trend)}`}>
                {trendIcon(kpi.trend)} {kpi.variation}
              </span>
            )}
            {kpi.threshold && (
              <span className="text-[10px] text-white/35 italic">{kpi.threshold}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
