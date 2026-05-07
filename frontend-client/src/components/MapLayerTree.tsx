// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { AlertTriangle, Eye, EyeOff, Loader } from 'lucide-react'
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
  if (!layers.length) return null

  return (
    <div className="border-b border-white/10 bg-white/2 max-h-36 overflow-y-auto">
      {layers.map((layer, idx) => {
        const color = colors[idx % colors.length]
        const visible = visibleLayers[idx] !== false
        const status = layerStatus[idx]
        const count = layerFeatureCounts[idx]
        const label = layer.title || layer.name || `Couche ${idx + 1}`
        const wfs = isWfsLayer(layer)

        return (
          <div
            key={idx}
            className={`flex items-center gap-2 px-3 py-1.5 border-b border-white/5 last:border-0 transition-opacity ${!visible ? 'opacity-40' : ''}`}
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

            {/* Visibility toggle */}
            <button
              type="button"
              onClick={() => onToggleVisibility(idx)}
              className="text-white/40 hover:text-white/80 transition-colors cursor-pointer shrink-0"
              title={visible ? 'Masquer la couche' : 'Afficher la couche'}
            >
              {visible ? <Eye size={13} /> : <EyeOff size={13} />}
            </button>
          </div>
        )
      })}
    </div>
  )
}
