// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix default marker icon paths broken by bundlers
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

interface Props {
  geojson: Record<string, unknown>
}

function countFeatures(gj: Record<string, unknown>): number {
  if (gj.type === 'FeatureCollection') return (gj.features as unknown[])?.length ?? 0
  if (gj.type === 'Feature') return 1
  return 0
}

export function MapViewer({ geojson }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.GeoJSON | null>(null)

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
        const name: string = props.name ?? props.display_name ?? ''
        const popup: string = props.popup_content ?? ''
        const lines: string[] = []
        if (name) lines.push(`<strong>${name}</strong>`)
        if (popup && popup !== name) lines.push(popup)
        if (lines.length) (l as L.Path).bindPopup(lines.join('<br>'), { maxWidth: 280 })
      },
    }).addTo(map)

    layerRef.current = layer

    const bounds = layer.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
  }, [geojson])

  const featureCount = countFeatures(geojson)

  function downloadGeoJson() {
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
        </span>
        <button
          type="button"
          onClick={downloadGeoJson}
          className="ml-auto text-xs text-white/50 hover:text-white/80 px-2 py-1 rounded border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
        >
          ↓ GeoJSON
        </button>
      </div>
      {/* Map container */}
      <div ref={containerRef} style={{ height: 320, background: '#1a1a2e' }} />
    </div>
  )
}
