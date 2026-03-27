<template>
  <div class="map-viewer-wrapper rounded-xl overflow-hidden border border-white/10 mt-2">
    <div class="flex items-center gap-2 px-3 py-2 bg-white/5 border-b border-white/10">
      <span class="text-sm">🗺️</span>
      <span class="text-xs font-medium text-white/70">Interactive Map</span>
      <span class="ml-auto text-xs text-white/30">{{ featureCount }} feature{{ featureCount !== 1 ? 's' : '' }}</span>
    </div>
    <div ref="mapRef" class="map-container" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as L from 'leaflet'

const props = defineProps<{
  geojson: Record<string, unknown>
}>()

const mapRef = ref<HTMLElement | null>(null)
let mapInstance: L.Map | null = null
let geoJsonLayer: L.GeoJSON | null = null

const featureCount = ref(0)

function countFeatures(gj: Record<string, unknown>): number {
  if (gj.type === 'FeatureCollection') {
    return (gj.features as unknown[])?.length ?? 0
  }
  if (gj.type === 'Feature') return 1
  return 0
}

function initMap() {
  if (!mapRef.value) return

  // Fix default marker icon paths (bundler issue with leaflet)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (L.Icon.Default.prototype as any)._getIconUrl
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
    iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  })

  mapInstance = L.map(mapRef.value, {
    zoomControl: true,
    attributionControl: true,
  })

  // Dark CartoDB tile layer
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(mapInstance)

  renderGeoJson()
}

function renderGeoJson() {
  if (!mapInstance) return

  // Remove previous layer
  if (geoJsonLayer) {
    geoJsonLayer.remove()
    geoJsonLayer = null
  }

  featureCount.value = countFeatures(props.geojson)

  if (!featureCount.value) return

  // Cast through unknown to satisfy leaflet's GeoJsonObject type
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const geojsonData = props.geojson as unknown as any

  geoJsonLayer = L.geoJSON(geojsonData, {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pointToLayer(_feature: any, latlng: L.LatLng) {
      return L.circleMarker(latlng, {
        radius: 8,
        fillColor: '#fbbf24',
        color: '#ffffff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.85,
      })
    },
    style() {
      return {
        color: '#fbbf24',
        weight: 2,
        opacity: 0.85,
        fillColor: '#fbbf24',
        fillOpacity: 0.2,
      }
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onEachFeature(feature: any, layer: L.Layer) {
      const featureProps = feature.properties ?? {}
      const name: string = featureProps.name ?? featureProps.display_name ?? ''
      const popup: string = featureProps.popup_content ?? ''
      const lines: string[] = []
      if (name) lines.push(`<strong>${name}</strong>`)
      if (popup && popup !== name) lines.push(popup)
      if (lines.length) {
        (layer as L.Path).bindPopup(lines.join('<br>'), { maxWidth: 280 })
      }
    },
  }).addTo(mapInstance)

  // Fit map to GeoJSON bounds
  const bounds = geoJsonLayer.getBounds()
  if (bounds.isValid()) {
    mapInstance.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
  }
}

onMounted(() => {
  initMap()
})

onUnmounted(() => {
  if (mapInstance) {
    mapInstance.remove()
    mapInstance = null
  }
})

watch(
  () => props.geojson,
  () => {
    renderGeoJson()
  },
  { deep: true },
)
</script>

<style>
/* Leaflet CSS must be imported globally */
@import 'leaflet/dist/leaflet.css';
</style>

<style scoped>
.map-viewer-wrapper {
  width: 100%;
}

.map-container {
  height: 320px;
  width: 100%;
  background: #1a1a2e;
}

/* Style leaflet popup to match dark theme */
:deep(.leaflet-popup-content-wrapper) {
  background: #1e2030;
  color: #e2e8f0;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
  font-size: 12px;
}

:deep(.leaflet-popup-tip) {
  background: #1e2030;
}

:deep(.leaflet-popup-close-button) {
  color: rgba(255, 255, 255, 0.5);
}

:deep(.leaflet-popup-close-button:hover) {
  color: #ffffff;
}

:deep(.leaflet-control-attribution) {
  background: rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.4);
  font-size: 10px;
}

:deep(.leaflet-control-attribution a) {
  color: rgba(255, 255, 255, 0.5);
}

:deep(.leaflet-control-zoom a) {
  background: #1e2030;
  color: rgba(255, 255, 255, 0.7);
  border-color: rgba(255, 255, 255, 0.15);
}

:deep(.leaflet-control-zoom a:hover) {
  background: #2d3044;
  color: #ffffff;
}
</style>
