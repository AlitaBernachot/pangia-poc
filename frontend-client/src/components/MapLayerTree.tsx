// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useCallback, useRef, useState } from 'react'
import { AlertTriangle, ExternalLink, Eye, EyeOff, GripVertical, Layers, Loader } from 'lucide-react'
import type { OgcLayer } from '../types'

export type LayerStatus = 'loading' | 'loaded' | 'error' | 'cors'

interface Props {
  layers: OgcLayer[]
  colors: string[]
  visibleLayers: Record<number, boolean>
  layerStatus: Record<number, LayerStatus>
  layerFeatureCounts: Record<number, number>
  onToggleVisibility: (idx: number) => void
}

const MIN_HEIGHT = 80
const DEFAULT_HEIGHT = 176 // ~max-h-44

function isWfsLayer(layer: OgcLayer): boolean {
  const proto = (layer.protocol ?? '').toLowerCase()
  return proto.includes('wfs') || layer.url.toLowerCase().includes('wfs')
}

export function MapLayerTree({
  layers,
  colors,
  visibleLayers,
  layerStatus,
  layerFeatureCounts,
  onToggleVisibility,
}: Props) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [listHeight, setListHeight] = useState(DEFAULT_HEIGHT)
  const dragStartY = useRef<number | null>(null)
  const dragStartH = useRef<number>(DEFAULT_HEIGHT)

  const onResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragStartY.current = e.clientY
    dragStartH.current = listHeight

    const onMove = (ev: MouseEvent) => {
      if (dragStartY.current === null) return
      const delta = dragStartY.current - ev.clientY // drag up = bigger
      setListHeight(Math.max(MIN_HEIGHT, dragStartH.current + delta))
    }
    const onUp = () => {
      dragStartY.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [listHeight])

  if (!layers.length) return null

  const loadedCount = Object.values(layerStatus).filter(s => s === 'loaded').length

  return (
    <div
      className="rounded-lg border border-white/15 shadow-2xl overflow-hidden flex flex-col"
      style={{ background: 'rgba(10, 10, 26, 0.88)', backdropFilter: 'blur(8px)', minWidth: 210, maxWidth: 300 }}
    >
      {/* Panel header */}
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b border-white/10 shrink-0">
        <Layers size={11} className="text-white/40 shrink-0" />
        <span className="text-[11px] font-semibold text-white/60 tracking-wide uppercase">Couches</span>
        <span className="ml-auto text-[10px] text-white/30">
          {loadedCount}/{layers.length}
        </span>
      </div>

      {/* Layer rows */}
      <div className="overflow-y-auto" style={{ height: listHeight }}>
        {layers.map((layer, idx) => {
          const color = colors[idx % colors.length]
          const visible = visibleLayers[idx] !== false
          const status = layerStatus[idx]
          const count = layerFeatureCounts[idx]
          const label = layer.title || layer.name || `Couche ${idx + 1}`
          const wfs = isWfsLayer(layer)
          const expanded = expandedIdx === idx

          return (
            <div key={idx} className="border-b border-white/5 last:border-0">
              {/* Main row — click to expand */}
              <div
                className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-opacity hover:bg-white/5 ${!visible ? 'opacity-40' : ''}`}
                onClick={() => setExpandedIdx(expanded ? null : idx)}
                title="Cliquer pour plus d'informations"
              >
                {/* Color indicator */}
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />

                {/* Layer name */}
                <span className="text-xs text-white/80 flex-1 truncate min-w-0" title={label}>
                  {label}
                </span>

                {/* Protocol badge */}
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 font-medium ${
                    wfs ? 'bg-orange-900/50 text-orange-300' : 'bg-blue-900/50 text-blue-300'
                  }`}
                >
                  {wfs ? 'WFS' : 'OGC'}
                </span>

                {/* Load status */}
                <span className="text-[10px] text-white/30 shrink-0 w-14 text-right">
                  {status === 'loading' && (
                    <Loader size={10} className="inline animate-spin text-white/40" />
                  )}
                  {status === 'loaded' && count !== undefined && `${count} obj.`}
                  {(status === 'error' || status === 'cors') && (
                    <span
                      title={
                        status === 'cors'
                          ? 'Non chargeable depuis le navigateur (CORS)'
                          : 'Erreur de chargement'
                      }
                    >
                      <AlertTriangle size={10} className="inline text-yellow-400" />
                    </span>
                  )}
                </span>

                {/* Visibility toggle — stop propagation so it doesn't expand */}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onToggleVisibility(idx) }}
                  className="text-white/40 hover:text-white/80 transition-colors cursor-pointer shrink-0"
                  title={visible ? 'Masquer la couche' : 'Afficher la couche'}
                >
                  {visible ? <Eye size={13} /> : <EyeOff size={13} />}
                </button>
              </div>

              {/* Accordion detail panel */}
              {expanded && (
                <div className="px-3 pb-2.5 pt-0.5 bg-white/3 text-[11px] text-white/50 space-y-1.5">
                  {layer.name && (
                    <div className="flex gap-1.5">
                      <span className="text-white/30 shrink-0 w-14">Couche</span>
                      <span className="text-white/70 font-mono break-all">{layer.name}</span>
                    </div>
                  )}
                  {layer.protocol && (
                    <div className="flex gap-1.5">
                      <span className="text-white/30 shrink-0 w-14">Protocole</span>
                      <span className="text-white/70 break-all">{layer.protocol}</span>
                    </div>
                  )}
                  {layer.url && (
                    <div className="flex gap-1.5">
                      <span className="text-white/30 shrink-0 w-14">URL</span>
                      <a
                        href={layer.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 underline underline-offset-2 break-all inline-flex items-start gap-0.5"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {layer.url}
                        <ExternalLink size={9} className="shrink-0 mt-0.5 opacity-70" />
                      </a>
                    </div>
                  )}
                  {status === 'cors' && (
                    <div className="flex items-start gap-1 text-yellow-400/70 mt-1">
                      <AlertTriangle size={10} className="shrink-0 mt-0.5" />
                      <span>Service non accessible directement (CORS). Chargement via proxy.</span>
                    </div>
                  )}
                  {status === 'error' && (
                    <div className="flex items-start gap-1 text-red-400/70 mt-1">
                      <AlertTriangle size={10} className="shrink-0 mt-0.5" />
                      <span>Erreur lors du chargement de cette couche.</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Resize handle — drag upward to grow */}
      <div
        className="flex items-center justify-end px-1.5 py-0.5 border-t border-white/10 shrink-0 select-none"
        style={{ cursor: 'ns-resize' }}
        onMouseDown={onResizeMouseDown}
        title="Redimensionner"
      >
        <GripVertical size={11} className="text-white/20 rotate-90" />
      </div>
    </div>
  )
}
