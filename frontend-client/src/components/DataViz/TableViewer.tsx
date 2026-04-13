import type { DataVizTable } from '../../types'

interface Props {
  table: DataVizTable
}

export function TableViewer({ table }: Props) {
  function downloadCsv() {
    const escape = (v: string | number) => {
      const s = String(v)
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s.replace(/"/g, '""')}"`
        : s
    }
    const header = table.columns.map(escape).join(',')
    const body = table.rows.map((row) => row.map(escape).join(',')).join('\n')
    const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${table.title ?? 'table'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/3 overflow-hidden">
      {/* Header */}
      <div className="flex items-center px-3 py-2 border-b border-white/8">
        {table.title && <span className="text-sm font-semibold text-white/80">{table.title}</span>}
        <button
          type="button"
          onClick={downloadCsv}
          className="ml-auto text-xs text-white/50 hover:text-white/80 px-2 py-1 rounded border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
        >
          ↓ CSV
        </button>
      </div>
      {/* Table */}
      <div className="overflow-auto max-h-60">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0">
            <tr>
              {table.columns.map((col) => (
                <th
                  key={col}
                  className="bg-white/5 text-white/60 font-semibold py-1.5 px-2 border-b border-white/8 text-left whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className="border-b border-white/5 last:border-0">
                {row.map((cell, j) => (
                  <td key={j} className="text-white/75 py-1 px-2">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
