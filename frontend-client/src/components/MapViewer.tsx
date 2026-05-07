// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef, useState, useCallback } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Layers, Map, Maximize2, Minimize2 } from 'lucide-react'
import type { OgcLayer } from '../types'
import { MapLayerTree, type LayerStatus } from './MapLayerTree'

// Fix default marker icon paths broken by bundlers
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const API_BASE: string = import.meta.env.VITE_API_URL ?? ''

interface Props {
  geojson?: Record<string, unknown> | null
  ogcLayers?: OgcLayer[] | null
}

// Palette for OGC/WFS layers (each layer gets a distinct colour)
const OGC_COLORS = ['#f97316', '#a855f7', '#10b981', '#eab308', '#ec4899']

function countFeatures(gj: Record<string, unknown> | null | undefined): number {
  if (!gj) return 0
  if (gj.type === 'FeatureCollection') return (gj.features as unknown[])?.length ?? 0
  if (gj.type === 'Feature') return 1
  return 0
}

function buildLayerFetchUrl(layer: OgcLayer): string {
  const proto = (layer.protocol ?? '').toLowerCase()
  const isWfs1x = proto.startsWith('ogc:wfs') || proto === 'wfs'
  let upstreamUrl: string
  if (isWfs1x) {
    const base = layer.url.split('?')[0]
    const typename = layer.name || base.split('/').pop() || 'layer'
    upstreamUrl = `${base}?SERVICE=WFS&REQUEST=GetFeature&VERSION=1.0.0&TYPENAME=${encodeURIComponent(typename)}&OUTPUTFORMAT=application%2Fjson&maxFeatures=200`
  } else {
    // OGC API Features
    const base = layer.url.split('?')[0].replace(/\/items\/?$/, '')
    upstreamUrl = `${base}/items?f=json&limit=500`
  }
  return `${API_BASE}/api/proxy/wfs?url=${encodeURIComponent(upstreamUrl)}`
}

export function MapViewer({ geojson, ogcLayers }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.GeoJSON | null>(null)
  const ogcLayerRefs = useRef<Record<number, L.GeoJSON>>({})

  const [visibleLayers, setVisibleLayers] = useState<Record<number, boolean>>({})
  const [layerStatus, setLayerStatus] = useState<Record<number, LayerStatus>>({})
  const [layerFeatureCounts, setLayerFeatureCounts] = useState<Record<number, number>>({})
  const [showLayerTree, setShowLayerTree] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((fs) => {
      setTimeout(() => mapRef.current?.invalidateSize(), 50)
      return !fs
    })
  }, [])

  // ESC to exit fullscreen
  useEffect(() => {
    if (!isFullscreen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') toggleFullscreen() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isFullscreen, toggleFullscreen])

  // Reset per-layer state when ogcLayers list changes
  useEffect(() => {
    setVisibleLayers(Object.fromEntries((ogcLayers ?? []).map((_, i) => [i, true])))
    setLayerStatus({})
    setLayerFeatureCounts({})
  }, [ogcLayers])

  // Initialise map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, { zoomControl: true, attributionControl: true })
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map)
    mapRef.current = map
    return () => { map.remove(); mapRef.current = null }
  }, [])

  // Re-render GeoJSON layer when data changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (layerRef.current) { layerRef.current.remove(); layerRef.current = null }
    if (!countFeatures(geojson)) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layer = L.geoJSON(geojson as any, {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      pointToLayer(_feature: any, latlng: L.LatLng) {
        return L.circleMarker(latlng, {
          radius: 8, fillColor: '#38bdf8', color: '#ffffff',
          weight: 1.5, opacity: 1, fillOpacity: 0.85,
        })
      },
      style() {
        return { color: '#38bdf8', weight: 2, opacity: 0.85, fillColor: '#38bdf8', fillOpacity: 0.2 }
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEachFeature(feature: any, l: L.Layer) {
        const props = feature.properties ?? {}
        if (!Object.keys(props).length) return
        const SKIP = new Set(['popup_content', 'latitude', 'longitude', 'lat', 'lon', 'lng'])
        const name: string = props.name ?? props.display_name ?? props.nom_court ?? props.titre ?? ''
        const prebuiltPopup: string = props.popup_content ?? ''
        let html = ''
        if (name) html += `<strong>${name}</strong>`
        if (prebuiltPopup && prebuiltPopup !== name) html += (html ? '<br>' : '') + prebuiltPopup
        const rows = Object.entries(props)
          .filter(([k]) => !SKIP.has(k) && k !== 'name' && k !== 'display_name')
          .map(([k, v]) => {
            const val = v === null || v === undefined ? '' : String(v)
            if (!val) return ''
            return `<tr><td style="color:#94a3b8;padding-right:6px;white-space:nowrap">${k.replace(/_/g, ' ')}</td><td style="word-break:break-word">${val}</td></tr>`
          })
          .filter(Boolean)
        if (rows.length) {
          html += (html ? '<hr style="border-color:#334155;margin:4px 0">' : '')
          html += `<table style="font-size:11px;border-collapse:collapse;width:100%">${rows.join('')}</table>`
        }
        if (html) (l as L.Path).bindPopup(html, { maxWidth: 320 })
      },
    }).addTo(map)
    layerRef.current = layer
    const bounds = layer.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
  }, [geojson])

  // Load OGC / WFS layers (runs once per ogcLayers reference)
  useEffect(() => {
    if (!ogcLayers?.length) return
    const controllers: AbortController[] = []
    let mounted = true

    async function loadLayer(layer: OgcLayer, idx: number) {
      if (!mapRef.current) return
      const ctrl = new AbortController()
      controllers.push(ctrl)
      const color = OGC_COLORS[idx % OGC_COLORS.length]
      setLayerStatus(s => ({ ...s, [idx]: 'loading' }))

      try {
        const res = await fetch(buildLayerFetchUrl(layer), {
          signal: ctrl.signal,
          headers: { Accept: 'application/geo+json, application/json' },
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const fc = await res.json()
        if (!mounted || fc.type !== 'FeatureCollection') return

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const geoLayer = L.geoJSON(fc as any, {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          pointToLayer(_feature: any, latlng: L.LatLng) {
            return L.circleMarker(latlng, {
              radius: 7, fillColor: color, color: '#ffffff',
              weight: 1.5, opacity: 1, fillOpacity: 0.85,
            })
          },
          style() {
            return { color, weight: 2, opacity: 0.85, fillColor: color, fillOpacity: 0.2 }
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          onEachFeature(feature: any, l: L.Layer) {
            const props = feature.properties ?? {}
            const name: string = props.name ?? props.display_name ?? props.nom ?? layer.title ?? layer.name
            const rows = Object.entries(props)
              .filter(([, v]) => v !== null && v !== undefined && String(v))
              .slice(0, 8)
              .map(([k, v]) => `<tr><td style="color:#94a3b8;padding-right:6px;white-space:nowrap">${k.replace(/_/g, ' ')}</td><td style="word-break:break-word">${String(v)}</td></tr>`)
            let html = name ? `<strong>${name}</strong>` : ''
            if (rows.length) {
              html += (html ? '<hr style="border-color:#334155;margin:4px 0">' : '')
              html += `<table style="font-size:11px;border-collapse:collapse;width:100%">${rows.join('')}</table>`
            }
            if (html) (l as L.Path).bindPopup(html, { maxWidth: 320 })
          },
        }).addTo(mapRef.current!)

        ogcLayerRefs.current[idx] = geoLayer
        const count = (fc.features ?? []).length
        if (mounted) {
          setLayerFeatureCounts(c => ({ ...c, [idx]: count }))
          setLayerStatus(s => ({ ...s, [idx]: 'loaded' }))
        }
        const bounds = geoLayer.getBounds()
        if (bounds.isValid()) mapRef.current!.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return
        if (mounted) {
          setLayerStatus(s => ({ ...s, [idx]: 'error' }))
        }
      }
    }

    ogcLayers.forEach((l, i) => loadLayer(l, i))

    return () => {
      mounted = false
      controllers.forEach(c => c.abort())
      Object.values(ogcLayerRefs.current).forEach(l => l.remove())
      ogcLayerRefs.current = {}
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ogcLayers])

  // Sync Leaflet layer visibility when user toggles a layer
  useEffect(() => {
    if (!mapRef.current) return
    Object.entries(ogcLayerRefs.current).forEach(([idxStr, layer]) => {
      if (visibleLayers[Number(idxStr)] === false) {
        layer.remove()
      } else {
        layer.addTo(mapRef.current!)
      }
    })
  }, [visibleLayers])

  const geojsonFeatureCount = countFeatures(geojson)
  const ogcFeatureCount = Object.values(layerFeatureCounts).reduce((a, b) => a + b, 0)
  const totalFeatureCount = geojsonFeatureCount + ogcFeatureCount
  const layerCount = ogcLayers?.length ?? 0

  function downloadGeoJson() {
    if (!geojson) return
    const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/geo+json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'map.geojson'
    a.click()
    URL.revokeObjectURL(url)
  }

  const containerClass = isFullscreen
    ? 'fixed inset-0 z-[9999] flex flex-col bg-[#0f0f1a]'
    : 'rounded-xl overflow-hidden border border-white/10 mt-2 w-full'

  return (
    <div className={containerClass}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-white/5 border-b border-white/10">
        <Map size={14} className="text-white/50" />
        <span className="text-xs font-medium text-white/70">Interactive Map</span>
        <span className="text-xs text-white/30">
          {totalFeatureCount > 0 && `${totalFeatureCount} feature${totalFeatureCount !== 1 ? 's' : ''}`}
          {layerCount > 0 && ` · ${layerCount} couche${layerCount !== 1 ? 's' : ''}`}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {layerCount > 0 && (
            <button
              type="button"
              onClick={() => setShowLayerTree(v => !v)}
              title="Afficher/masquer le panneau des couches"
              className={`flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors cursor-pointer ${
                showLayerTree
                  ? 'border-white/25 text-white/80 bg-white/8'
                  : 'border-white/10 text-white/40 hover:text-white/70 hover:border-white/20'
              }`}
            >
              <Layers size={12} />
              <span>Couches</span>
            </button>
          )}
          {geojson && (
            <button
              type="button"
              onClick={downloadGeoJson}
              className="text-xs text-white/50 hover:text-white/80 px-2 py-1 rounded border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
            >
              ↓ GeoJSON
            </button>
          )}
          <button
            type="button"
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Réduire la carte' : 'Agrandir la carte'}
            className="flex items-center justify-center w-7 h-7 rounded border border-white/10 hover:border-white/25 text-white/50 hover:text-white/85 hover:bg-white/5 transition-colors cursor-pointer"
          >
            {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          </button>
        </div>
      </div>

      {/* Layer tree panel */}
      {showLayerTree && layerCount > 0 && (
        <MapLayerTree
          layers={ogcLayers!}
          colors={OGC_COLORS}
          visibleLayers={visibleLayers}
          layerStatus={layerStatus}
          layerFeatureCounts={layerFeatureCounts}
          onToggleVisibility={(idx) => setVisibleLayers(v => ({ ...v, [idx]: v[idx] !== false ? false : true }))}
        />
      )}

      {/* Map container */}
      <div
        ref={containerRef}
        style={isFullscreen ? { flex: 1, background: '#1a1a2e' } : { height: 320, background: '#1a1a2e' }}
      />
    </div>
  )
}
