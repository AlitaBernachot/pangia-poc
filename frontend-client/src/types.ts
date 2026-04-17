// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

export interface ToolActivity {
  tool: string
  status: 'running' | 'done'
}

export interface AgentActivity {
  agent: string
  content: string
  streaming: boolean
  tools: ToolActivity[]
}

// ─── DataViz types ────────────────────────────────────────────────────────────

export interface DataVizDataset {
  label: string
  /** For bar/line/pie/histogram: array of numbers. For scatter: array of {x,y} objects. */
  data: (number | { x: number; y: number })[]
}

export interface DataVizChart {
  chart_type: 'bar' | 'line' | 'pie' | 'scatter' | 'histogram'
  title: string
  labels: string[]
  datasets: DataVizDataset[]
}

export interface DataVizKpi {
  label: string
  value: string | number
  unit?: string
  variation?: string
  trend: 'up' | 'down' | 'stable'
  threshold?: string
}

export interface DataVizTable {
  title: string
  columns: string[]
  rows: (string | number)[][]
}

export interface DataVizPayload {
  charts?: DataVizChart[]
  kpis?: DataVizKpi[]
  tables?: DataVizTable[]
}

// ─── V2 HITL (Human-in-the-Loop) ─────────────────────────────────────────────

export interface HITLRequestEvent {
  request_id: string
  questions: string[]
  original_query: string
}

// ─── Dataset choice (human-in-the-loop) ──────────────────────────────────────

export interface DatasetCandidate {
  id: string
  title: string
  description: string
  url: string
  organization: string
}
// ─── OGC Layer (GeoNetwork) ──────────────────────────────────────────────────

export interface OgcLayer {
  url: string
  name: string
  title?: string
}
// ─────────────────────────────────────────────────────────────────────────────

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  routingAgents?: string[]
  agentActivity?: AgentActivity[]
  geojson?: Record<string, unknown> | null
  dataviz?: DataVizPayload | null
  datasetChoice?: DatasetCandidate[] | null
  datasetChoiceTotal?: number | null
  ogcLayers?: OgcLayer[] | null
  attachments?: Attachment[]
  hitlRequest?: HITLRequestEvent | null
  routingPlan?: { steps: { agent_name: string; parallel_group: number }[]; reasoning: string } | null
}

export interface AgentInfo {
  key: string
  label: string
}

export interface Attachment {
  id: string
  name: string
  type: string
  url: string
  size: number
}

export const AGENT_COLORS: Record<string, { text: string; border: string; bg: string }> = {
  'Neo4j':        { text: '#4ade80', border: '#4ade80', bg: 'rgba(74,222,128,0.1)'  },
  'RDF/SPARQL':   { text: '#fb923c', border: '#fb923c', bg: 'rgba(251,146,60,0.1)'  },
  'Vector':       { text: '#60a5fa', border: '#60a5fa', bg: 'rgba(96,165,250,0.1)'  },
  'PostGIS':      { text: '#38bdf8', border: '#38bdf8', bg: 'rgba(56,189,248,0.1)'  },
  'Map':          { text: '#22d3ee', border: '#22d3ee', bg: 'rgba(34,211,238,0.1)'  },
  'Data.gouv.fr': { text: '#f43f5e', border: '#f43f5e', bg: 'rgba(244,63,94,0.1)'   },
  'DataViz':      { text: '#7dd3fc', border: '#7dd3fc', bg: 'rgba(125,211,252,0.1)' },
}

import {
  Share2, Link2, Layers, Map, MapPin, Globe, BarChart2, Bot,
  Network, Code2, Database, GitBranch, FilePlus, Download,
  Braces, Ruler, Target, Search, Circle, Clock, Navigation,
  Crosshair, Activity, Mountain, Eye, ArrowLeftRight, Hash,
  TrendingUp, Table2, Square, Filter, GitMerge, MessageSquare,
  CheckCircle, Merge,
  type LucideIcon,
} from 'lucide-react'

export const AGENT_ICON_MAP: Record<string, LucideIcon> = {
  'Neo4j':        Share2,
  'RDF/SPARQL':   Link2,
  'Vector':       Layers,
  'PostGIS':      Map,
  'Map':          MapPin,
  'Data.gouv.fr': Globe,
  'DataViz':      BarChart2,
}

export function getAgentIcon(agent: string): LucideIcon {
  return AGENT_ICON_MAP[agent] ?? Bot
}

// ─── Tool metadata ────────────────────────────────────────────────────────────

export interface ToolMeta {
  /** i18n key under `toolLabels.*` */
  labelKey: string
  icon: LucideIcon
}

export const TOOL_META_MAP: Record<string, ToolMeta> = {
  // ── Neo4j ──────────────────────────────────────────────────────────────────
  search_knowledge_graph:        { labelKey: 'search_knowledge_graph',        icon: Network       },
  run_cypher_query:              { labelKey: 'run_cypher_query',              icon: Code2         },

  // ── RDF / SPARQL ───────────────────────────────────────────────────────────
  run_sparql_select:             { labelKey: 'run_sparql_select',             icon: Database      },
  run_sparql_construct:          { labelKey: 'run_sparql_construct',          icon: GitBranch     },

  // ── Vector / Chroma ────────────────────────────────────────────────────────
  vector_similarity_search:      { labelKey: 'vector_similarity_search',      icon: Layers        },
  vector_add_documents:          { labelKey: 'vector_add_documents',          icon: FilePlus      },

  // ── PostGIS ────────────────────────────────────────────────────────────────
  run_postgis_query:             { labelKey: 'run_postgis_query',             icon: Map           },

  // ── Data.gouv.fr ───────────────────────────────────────────────────────────
  fetch_resource_file:           { labelKey: 'fetch_resource_file',           icon: Download      },

  // ── Map / GeoJSON output ───────────────────────────────────────────────────
  extract_geojson_from_text:     { labelKey: 'extract_geojson_from_text',     icon: Braces        },
  geocode_address:               { labelKey: 'geocode_address',               icon: MapPin        },
  create_geojson:                { labelKey: 'create_geojson',                icon: MapPin        },
  calculate_bounds:              { labelKey: 'calculate_bounds',              icon: Square        },
  add_popup_content:             { labelKey: 'add_popup_content',             icon: MessageSquare },
  parse_wkt_to_geojson:          { labelKey: 'parse_wkt_to_geojson',          icon: MapPin        },

  // ── DataViz output ─────────────────────────────────────────────────────────
  extract_numbers_from_text:     { labelKey: 'extract_numbers_from_text',     icon: Hash          },
  build_chart:                   { labelKey: 'build_chart',                   icon: BarChart2     },
  build_kpi:                     { labelKey: 'build_kpi',                     icon: TrendingUp    },
  build_table:                   { labelKey: 'build_table',                   icon: Table2        },

  // ── Geo L1 – Address ───────────────────────────────────────────────────────
  reverse_geocode:               { labelKey: 'reverse_geocode',               icon: MapPin        },
  batch_geocode:                 { labelKey: 'batch_geocode',                 icon: MapPin        },

  // ── Geo L1 – Buffer ────────────────────────────────────────────────────────
  create_circular_buffer:        { labelKey: 'create_circular_buffer',        icon: Circle        },
  create_multi_ring_buffer:      { labelKey: 'create_multi_ring_buffer',      icon: Circle        },
  calculate_buffer_area:         { labelKey: 'calculate_buffer_area',         icon: Circle        },

  // ── Geo L1 – Distance ──────────────────────────────────────────────────────
  haversine_distance:            { labelKey: 'haversine_distance',            icon: Ruler         },
  distance_matrix:               { labelKey: 'distance_matrix',               icon: Ruler         },
  find_closest_point:            { labelKey: 'find_closest_point',            icon: Target        },
  convert_distance:              { labelKey: 'convert_distance',              icon: ArrowLeftRight},

  // ── Geo L1 – Spatial parser ────────────────────────────────────────────────
  extract_spatial_entities:      { labelKey: 'extract_spatial_entities',      icon: Search        },
  parse_spatial_relationship:    { labelKey: 'parse_spatial_relationship',    icon: GitMerge      },
  extract_coordinates_from_text: { labelKey: 'extract_coordinates_from_text', icon: Crosshair     },

  // ── Geo L2 – Routing ───────────────────────────────────────────────────────
  compute_route:                 { labelKey: 'compute_route',                 icon: Navigation    },
  optimise_tour:                 { labelKey: 'optimise_tour',                 icon: Navigation    },
  estimate_travel_time:          { labelKey: 'estimate_travel_time',          icon: Clock         },

  // ── Geo L2 – Hotspot ───────────────────────────────────────────────────────
  detect_clusters:               { labelKey: 'detect_clusters',               icon: Activity      },
  compute_spatial_density:       { labelKey: 'compute_spatial_density',       icon: Activity      },
  find_clustergeo_centroid:      { labelKey: 'find_clustergeo_centroid',      icon: Target        },

  // ── Geo L2 – Proximity ─────────────────────────────────────────────────────
  find_nearest:                  { labelKey: 'find_nearest',                  icon: Target        },
  filter_within_radius:          { labelKey: 'filter_within_radius',          icon: Filter        },
  rank_by_proximity:             { labelKey: 'rank_by_proximity',             icon: Target        },

  // ── Geo L2 – Isochrone ─────────────────────────────────────────────────────
  estimate_reachable_radius:     { labelKey: 'estimate_reachable_radius',     icon: Circle        },
  generate_isochrone:            { labelKey: 'generate_isochrone',            icon: Circle        },
  generate_multi_isochrone:      { labelKey: 'generate_multi_isochrone',      icon: Circle        },

  // ── Geo L2 – Area ──────────────────────────────────────────────────────────
  calculate_polygon_area:        { labelKey: 'calculate_polygon_area',        icon: Square        },
  convert_area:                  { labelKey: 'convert_area',                  icon: ArrowLeftRight},
  compare_to_reference:          { labelKey: 'compare_to_reference',          icon: BarChart2     },
  sum_areas:                     { labelKey: 'sum_areas',                     icon: Hash          },

  // ── Geo L2 – Intersection ──────────────────────────────────────────────────
  check_bbox_intersection:       { labelKey: 'check_bbox_intersection',       icon: Square        },
  compute_bbox_overlap:          { labelKey: 'compute_bbox_overlap',          icon: Square        },
  point_in_bbox:                 { labelKey: 'point_in_bbox',                 icon: MapPin        },
  classify_spatial_relationship: { labelKey: 'classify_spatial_relationship', icon: GitMerge      },

  // ── Geo L3 – Viewshed ──────────────────────────────────────────────────────
  compute_horizon_distance:      { labelKey: 'compute_horizon_distance',      icon: Eye           },
  estimate_viewshed_radius:      { labelKey: 'estimate_viewshed_radius',      icon: Eye           },
  generate_viewshed_zone:        { labelKey: 'generate_viewshed_zone',        icon: Eye           },
  check_line_of_sight:           { labelKey: 'check_line_of_sight',           icon: Eye           },

  // ── Geo L3 – Elevation ─────────────────────────────────────────────────────
  get_elevation:                 { labelKey: 'get_elevation',                 icon: Mountain      },
  compute_elevation_profile:     { labelKey: 'compute_elevation_profile',     icon: Mountain      },
  analyse_elevation_stats:       { labelKey: 'analyse_elevation_stats',       icon: Mountain      },

  // ── Geo L3 – Geometry ops ──────────────────────────────────────────────────
  compute_bbox:                  { labelKey: 'compute_bbox',                  icon: Square        },
  compute_centroid:              { labelKey: 'compute_centroid',              icon: Target        },
  simplify_linestring:           { labelKey: 'simplify_linestring',           icon: Navigation    },
  validate_geojson:              { labelKey: 'validate_geojson',              icon: CheckCircle   },
  merge_feature_collections:     { labelKey: 'merge_feature_collections',     icon: Merge         },

  // ── Geo L3 – Temporal ──────────────────────────────────────────────────────
  analyse_movement:              { labelKey: 'analyse_movement',              icon: Activity      },
  compute_displacement:          { labelKey: 'compute_displacement',          icon: ArrowLeftRight},
  detect_temporal_pattern:       { labelKey: 'detect_temporal_pattern',       icon: Clock         },
  summarise_time_series:         { labelKey: 'summarise_time_series',         icon: TrendingUp    },
}

export function getToolMeta(tool: string): ToolMeta {
  return TOOL_META_MAP[tool] ?? { labelKey: tool, icon: Search }
}
