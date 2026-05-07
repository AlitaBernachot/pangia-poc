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
  waitingForChoice?: boolean
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

export interface ChoiceRequestEvent {
  request_id: string
  agent: string
  items: DatasetCandidate[]
  total?: number | null
  original_query: string
}
// ─── OGC Layer (GeoNetwork) ──────────────────────────────────────────────────

export interface OgcLayer {
  url: string
  name: string
  title?: string
  protocol?: string
}
// ─────────────────────────────────────────────────────────────────────────────

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  sessionPhrase?: string
  routingAgents?: string[]
  agentActivity?: AgentActivity[]
  geojson?: Record<string, unknown> | null
  dataviz?: DataVizPayload | null
  choiceRequest?: ChoiceRequestEvent | null
  chosenDataset?: DatasetCandidate | null
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

/** Maps raw backend agent keys to human-readable display labels. */
// FIXME: these labels are duplicated in the backend and should be defined in a shared location
export const AGENT_LABEL_MAP: Record<string, string> = {
  neo4j_agent:            'Neo4j',
  rdf_agent:              'RDF/SPARQL',
  vector_chroma_agent:    'Vector',
  postgis_agent:          'PostGIS',
  mapviz_agent:           'Map',
  datagouv_mcp_agent:     'Data.gouv.fr',
  geonetwork_mcp_agent:   'GeoNetwork',
  dataviz_agent:          'DataViz',
  rag_agent:              'Knowledge',
  humanoutput_agent:      'Output Analysis',
  summary_agent:          'Summary',
  calculator_agent:       'Calculator',
  intent_parser_agent:    'Analysis',
  smart_dispatcher_agent: 'Routing',
  merge:                  'Synthesis',
  // post-processing node names (emitted directly by sse_stream.py)
  merge_node:             'Synthesis',
  synthesis_node:         'Synthesis',
  humanoutput_node:       'Output Analysis',
  dataviz_node:           'DataViz',
  mapviz_node:            'Map',
  followup_filter_node:   'Analyse contextuelle',
  followup_filter_agent:  'Analyse contextuelle',
}

/** Agent keys that are data sources — shown as "querying" when no tool is active yet. */
export const SOURCE_AGENT_KEYS = new Set([
  'neo4j_agent',
  'rdf_agent',
  'vector_chroma_agent',
  'postgis_agent',
  'datagouv_mcp_agent',
  'geonetwork_mcp_agent',
  'rag_agent',
])

/** Returns the display label for an agent key, falling back to the raw key. */
export function getAgentLabel(agentKey: string): string {
  return AGENT_LABEL_MAP[agentKey] ?? agentKey
}

// FIXME: these colors are duplicated in the backend and should be defined in a shared location
export const AGENT_COLORS: Record<string, { text: string; border: string; bg: string }> = {
  // ── Data source agents — blues & cyans from the PangIA logo ──────────────
  'Neo4j':        { text: '#60a5fa', border: '#60a5fa', bg: 'rgba(96,165,250,0.1)'   }, // blue-400
  'RDF/SPARQL':   { text: '#38bdf8', border: '#38bdf8', bg: 'rgba(56,189,248,0.1)'   }, // sky-400
  'Vector':       { text: '#22d3ee', border: '#22d3ee', bg: 'rgba(34,211,238,0.1)'   }, // cyan-400
  'PostGIS':      { text: '#0ea5e9', border: '#0ea5e9', bg: 'rgba(14,165,233,0.1)'   }, // sky-500
  'Map':          { text: '#7dd3fc', border: '#7dd3fc', bg: 'rgba(125,211,252,0.1)'  }, // sky-300
  'Data.gouv.fr': { text: '#93c5fd', border: '#93c5fd', bg: 'rgba(147,197,253,0.1)'  }, // blue-300
  'GeoNetwork':   { text: '#06b6d4', border: '#06b6d4', bg: 'rgba(6,182,212,0.1)'    }, // cyan-500
  'DataViz':      { text: '#67e8f9', border: '#67e8f9', bg: 'rgba(103,232,249,0.1)'  }, // cyan-300
  'Knowledge':    { text: '#3b82f6', border: '#3b82f6', bg: 'rgba(59,130,246,0.1)'   }, // blue-500
  // ── Post-processing / orchestration — deeper blues ────────────────────────
  'Synthesis':    { text: '#0891b2', border: '#0891b2', bg: 'rgba(8,145,178,0.1)'    }, // cyan-600
  'Output Analysis': { text: '#0284c7', border: '#0284c7', bg: 'rgba(2,132,199,0.1)'    }, // sky-600
  'Summary':      { text: '#0284c7', border: '#0284c7', bg: 'rgba(2,132,199,0.1)'    }, // sky-600
  'Analysis':     { text: '#bae6fd', border: '#bae6fd', bg: 'rgba(186,230,253,0.08)' }, // sky-200
  'Routing':      { text: '#7ea8c9', border: '#7ea8c9', bg: 'rgba(126,168,201,0.08)' }, // muted blue-grey
  'Calculator':        { text: '#a5f3fc', border: '#a5f3fc', bg: 'rgba(165,243,252,0.08)' }, // cyan-200
  'Filtre Contextuel':    { text: '#a78bfa', border: '#a78bfa', bg: 'rgba(167,139,250,0.1)'  }, // violet-400
  'Analyse contextuelle': { text: '#a78bfa', border: '#a78bfa', bg: 'rgba(167,139,250,0.1)'  }, // violet-400
}

import {
  Share2, Link2, Layers, Map, MapPin, Globe, BarChart2, Bot,
  Network, Code2, Database, GitBranch, FilePlus, Download,
  Braces, Ruler, Target, Search, Circle, Clock, Navigation,
  Crosshair, Activity, Mountain, Eye, ArrowLeftRight, Hash,
  TrendingUp, Table2, Square, Filter, GitMerge, MessageSquare,
  CheckCircle, Merge, BookOpen, ScanEye,
  type LucideIcon,
} from 'lucide-react'

export const AGENT_ICON_MAP: Record<string, LucideIcon> = {
  'Neo4j':        Share2,
  'RDF/SPARQL':   Link2,
  'Vector':       Layers,
  'PostGIS':      Map,
  'Map':          MapPin,
  'Data.gouv.fr': Globe,
  'GeoNetwork':   Network,
  'DataViz':      BarChart2,
  'Knowledge':    BookOpen,
  'Synthesis':    GitMerge,
  'Output Analysis': ScanEye,
  'Summary':      MessageSquare,
  'Analysis':     Crosshair,
  'Routing':           Filter,
  'Calculator':        Hash,
  'Filtre Contextuel':    Filter,
  'Analyse contextuelle': ScanEye,
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

// ─── Tool → Phase mapping (vague activity phases shown in the UI) ─────────────

export type PhaseKey = 'querying' | 'fetching' | 'locating' | 'computing' | 'processing' | 'visualizing'

const TOOL_PHASE_MAP: Record<string, PhaseKey> = {
  // querying — reads from a data source
  search_knowledge_graph:        'querying',
  run_cypher_query:              'querying',
  run_sparql_select:             'querying',
  run_sparql_construct:          'querying',
  run_postgis_query:             'querying',
  vector_similarity_search:      'querying',
  query_resource_data:           'querying',
  search_datasets:               'querying',
  // fetching — downloads / retrieves external content
  fetch_resource_file:           'fetching',
  get_dataset_resources:         'fetching',
  list_dataset_resources:        'fetching',
  get_resource_info:             'fetching',
  vector_add_documents:          'fetching',
  // locating — geocoding and spatial entity extraction
  geocode_address:               'locating',
  reverse_geocode:               'locating',
  batch_geocode:                 'locating',
  extract_spatial_entities:      'locating',
  parse_spatial_relationship:    'locating',
  extract_coordinates_from_text: 'locating',
  parse_wkt_to_geojson:          'locating',
  // computing — numerical / geometric calculations
  haversine_distance:            'computing',
  distance_matrix:               'computing',
  find_closest_point:            'computing',
  convert_distance:              'computing',
  compute_route:                 'computing',
  optimise_tour:                 'computing',
  estimate_travel_time:          'computing',
  create_circular_buffer:        'computing',
  create_multi_ring_buffer:      'computing',
  calculate_buffer_area:         'computing',
  calculate_polygon_area:        'computing',
  convert_area:                  'computing',
  compare_to_reference:          'computing',
  sum_areas:                     'computing',
  check_bbox_intersection:       'computing',
  compute_bbox_overlap:          'computing',
  point_in_bbox:                 'computing',
  classify_spatial_relationship: 'computing',
  compute_horizon_distance:      'computing',
  estimate_viewshed_radius:      'computing',
  get_elevation:                 'computing',
  compute_elevation_profile:     'computing',
  analyse_elevation_stats:       'computing',
  compute_bbox:                  'computing',
  compute_centroid:              'computing',
  simplify_linestring:           'computing',
  compute_displacement:          'computing',
  detect_temporal_pattern:       'computing',
  summarise_time_series:         'computing',
  analyse_movement:              'computing',
  detect_clusters:               'computing',
  compute_spatial_density:       'computing',
  find_clustergeo_centroid:      'computing',
  estimate_reachable_radius:     'computing',
  generate_isochrone:            'computing',
  generate_multi_isochrone:      'computing',
  find_nearest:                  'computing',
  filter_within_radius:          'computing',
  rank_by_proximity:             'computing',
  // processing — data transformation / validation
  extract_geojson_from_text:     'processing',
  extract_numbers_from_text:     'processing',
  validate_geojson:              'processing',
  merge_feature_collections:     'processing',
  // visualizing — output generation
  build_chart:                   'visualizing',
  build_kpi:                     'visualizing',
  build_table:                   'visualizing',
  create_geojson:                'visualizing',
  calculate_bounds:              'visualizing',
  add_popup_content:             'visualizing',
  generate_viewshed_zone:        'visualizing',
  check_line_of_sight:           'visualizing',
}

/** Returns the vague activity phase for a tool name (defaults to 'processing'). */
export function getToolPhase(tool: string): PhaseKey {
  return TOOL_PHASE_MAP[tool] ?? 'processing'
}
