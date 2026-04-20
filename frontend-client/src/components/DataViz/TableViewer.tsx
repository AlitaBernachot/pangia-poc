// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useState } from 'react'
import type { DataVizTable } from '../../types'

const PAGE_SIZE = 50

const IMAGE_URL_RE = /^https?:\/\/.+\.(jpe?g|png|gif|webp|svg)(\?.*)?$/i

function CellContent({ value }: { value: string | number }) {
  const s = String(value)
  if (IMAGE_URL_RE.test(s)) {
    return (
      <img
        src={s}
        alt=""
        className="size-10 object-cover rounded"
        loading="lazy"
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
      />
    )
  }
  return <>{s}</>
}

interface Props {
  table: DataVizTable
}

export function TableViewer({ table }: Props) {
  const [page, setPage] = useState(0)
  const totalPages = Math.ceil(table.rows.length / PAGE_SIZE)
  const visibleRows = table.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

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
      <div className="overflow-auto max-h-128">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0">
            <tr style={{"background": "#151517"}}>
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
            {visibleRows.map((row, i) => (
              <tr key={i} className="border-b border-white/5 last:border-0">
                {row.map((cell, j) => (
                  <td key={j} className="text-white/75 py-1 px-2">
                    <CellContent value={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Footer */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-t border-white/8 text-[11px] text-white/35">
        <span>
          {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, table.rows.length)} / {table.rows.length} enregistrement{table.rows.length !== 1 ? 's' : ''}
        </span>
        {totalPages > 1 && (
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage(0)}
              className="px-1.5 py-0.5 rounded border border-white/10 hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              «
            </button>
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="px-1.5 py-0.5 rounded border border-white/10 hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              ‹
            </button>
            <span className="px-2 text-white/50">
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page === totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
              className="px-1.5 py-0.5 rounded border border-white/10 hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              ›
            </button>
            <button
              type="button"
              disabled={page === totalPages - 1}
              onClick={() => setPage(totalPages - 1)}
              className="px-1.5 py-0.5 rounded border border-white/10 hover:border-white/20 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              »
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
