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

// ─── Dataset choice (human-in-the-loop) ──────────────────────────────────────

export interface DatasetCandidate {
  id: string
  title: string
  description: string
  url: string
  organization: string
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
  attachments?: Attachment[]
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

import { Share2, Link2, Layers, Map, MapPin, Globe, BarChart2, Bot, type LucideIcon } from 'lucide-react'

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
