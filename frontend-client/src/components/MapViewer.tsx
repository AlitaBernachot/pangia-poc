// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef, useState } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { OgcLayer } from '../types'

// Fix default marker icon paths broken by bundlers
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

interface Props {
  geojson?: Record<string, unknown> | null
  ogcLayers?: OgcLayer[] | null
}

function countFeatures(gj: Record<string, unknown> | null | undefined): number {
  if (!gj) return 0
  if (gj.type === 'FeatureCollection') return (gj.features as unknown[])?.length ?? 0
  if (gj.type === 'Feature') return 1
  return 0
}

// Palette for OGC layers (each layer gets a distinct colour)
const OGC_COLORS = ['#f97316', '#a855f7', '#10b981', '#eab308', '#ec4899']

export function MapViewer({ geojson, ogcLayers }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.GeoJSON | null>(null)
  const ogcLayerRefs = useRef<L.GeoJSON[]>([])
  const [ogcFeatureCount, setOgcFeatureCount] = useState(0)
  const [ogcError, setOgcError] = useState<string | null>(null)

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

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Re-render GeoJSON layer when data changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (layerRef.current) {
      layerRef.current.remove()
      layerRef.current = null
    }

    if (!countFeatures(geojson)) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layer = L.geoJSON(geojson as any, {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      pointToLayer(_feature: any, latlng: L.LatLng) {
        return L.circleMarker(latlng, {
          radius: 8,
          fillColor: '#38bdf8',
          color: '#ffffff',
          weight: 1.5,
          opacity: 1,
          fillOpacity: 0.85,
        })
      },
      style() {
        return { color: '#38bdf8', weight: 2, opacity: 0.85, fillColor: '#38bdf8', fillOpacity: 0.2 }
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEachFeature(feature: any, l: L.Layer) {
        const props = feature.properties ?? {}
        if (!Object.keys(props).length) return

        // Keys to skip from the property table (redundant or internal)
        const SKIP = new Set(['popup_content', 'latitude', 'longitude', 'lat', 'lon', 'lng'])

        const name: string = props.name ?? props.display_name ?? props.nom_court ?? props.titre ?? ''
        const prebuiltPopup: string = props.popup_content ?? ''

        let html = ''
        if (name) html += `<strong>${name}</strong>`
        if (prebuiltPopup && prebuiltPopup !== name) {
          html += (html ? '<br>' : '') + prebuiltPopup
        }

        // Build a compact key/value table for all remaining properties
        const rows = Object.entries(props)
          .filter(([k]) => !SKIP.has(k) && k !== 'name' && k !== 'display_name')
          .map(([k, v]) => {
            const label = k.replace(/_/g, ' ')
            const val = v === null || v === undefined ? '' : String(v)
            if (!val) return ''
            return `<tr><td style="color:#94a3b8;padding-right:6px;white-space:nowrap">${label}</td><td style="word-break:break-word">${val}</td></tr>`
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

  // Load and display OGC API Features layers
  useEffect(() => {
    if (!ogcLayers?.length) return
    const controllers: AbortController[] = []
    let mounted = true
    let totalFeatures = 0
    setOgcError(null)

    async function loadLayer(layer: OgcLayer, idx: number) {
      const ctrl = new AbortController()
      controllers.push(ctrl)
      try {
        // Build /items URL: strip query params and trailing /items, then re-append
        const base = layer.url.split('?')[0].replace(/\/items\/?$/, '')
        const itemsUrl = `${base}/items?f=json&limit=500`
        const res = await fetch(itemsUrl, {
          signal: ctrl.signal,
          headers: { Accept: 'application/geo+json, application/json' },
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const fc = await res.json()
        if (!mounted || fc.type !== 'FeatureCollection') return

        const color = OGC_COLORS[idx % OGC_COLORS.length]
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const geoLayer = L.geoJSON(fc as any, {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          pointToLayer(_feature: any, latlng: L.LatLng) {
            return L.circleMarker(latlng, {
              radius: 7,
              fillColor: color,
              color: '#ffffff',
              weight: 1.5,
              opacity: 1,
              fillOpacity: 0.85,
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

        ogcLayerRefs.current.push(geoLayer)
        totalFeatures += (fc.features ?? []).length
        if (mounted) setOgcFeatureCount(totalFeatures)

        const bounds = geoLayer.getBounds()
        if (bounds.isValid()) mapRef.current!.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return
        if (mounted) setOgcError(`Impossible de charger la couche "${layer.name}": ${err instanceof Error ? err.message : err}`)
      }
    }

    ogcLayers.forEach((l, i) => loadLayer(l, i))

    return () => {
      mounted = false
      controllers.forEach((c) => c.abort())
      ogcLayerRefs.current.forEach((l) => l.remove())
      ogcLayerRefs.current = []
      setOgcFeatureCount(0)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ogcLayers])

  const featureCount = countFeatures(geojson) + ogcFeatureCount
  const totalLayers = (ogcLayers?.length ?? 0)

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

  return (
    <div className="rounded-xl overflow-hidden border border-white/10 mt-2 w-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-white/5 border-b border-white/10">
        <span className="text-sm">🗺️</span>
        <span className="text-xs font-medium text-white/70">Interactive Map</span>
        <span className="text-xs text-white/30">
          {featureCount} feature{featureCount !== 1 ? 's' : ''}
          {totalLayers > 0 && ` · ${totalLayers} OGC layer${totalLayers !== 1 ? 's' : ''}`}
        </span>
        {geojson && (
          <button
            type="button"
            onClick={downloadGeoJson}
            className="ml-auto text-xs text-white/50 hover:text-white/80 px-2 py-1 rounded border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
          >
            ↓ GeoJSON
          </button>
        )}
      </div>
      {/* OGC layer names */}
      {totalLayers > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 py-1.5 bg-white/3 border-b border-white/10">
          {ogcLayers!.map((l, i) => (
            <span
              key={l.url}
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ background: `${OGC_COLORS[i % OGC_COLORS.length]}22`, color: OGC_COLORS[i % OGC_COLORS.length] }}
            >
              {l.title ?? l.name}
            </span>
          ))}
        </div>
      )}
      {ogcError && (
        <div className="px-3 py-1.5 text-xs text-amber-400 bg-amber-900/20 border-b border-amber-800/30">
          {ogcError}
        </div>
      )}
      {/* Map container */}
      <div ref={containerRef} style={{ height: 320, background: '#1a1a2e' }} />
    </div>
  )
}
