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

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  routingAgents?: string[]
  agentActivity?: AgentActivity[]
  geojson?: Record<string, unknown> | null
}

export interface AgentInfo {
  key: string
  label: string
}

export const AGENT_COLORS: Record<string, { text: string; border: string; bg: string }> = {
  'Neo4j':      { text: '#4ade80', border: '#4ade80', bg: 'rgba(74,222,128,0.1)'  },
  'RDF/SPARQL': { text: '#fb923c', border: '#fb923c', bg: 'rgba(251,146,60,0.1)'  },
  'Vector':     { text: '#a78bfa', border: '#a78bfa', bg: 'rgba(167,139,250,0.1)' },
  'PostGIS':    { text: '#38bdf8', border: '#38bdf8', bg: 'rgba(56,189,248,0.1)'  },
  'Map':        { text: '#fbbf24', border: '#fbbf24', bg: 'rgba(251,191,36,0.1)'  },
}

export const AGENT_ICONS: Record<string, string> = {
  'Neo4j':      '🔷',
  'RDF/SPARQL': '🔗',
  'Vector':     '🧲',
  'PostGIS':    '🗺️',
  'Map':        '📍',
}

export function agentIcon(agent: string): string {
  return AGENT_ICONS[agent] ?? '🤖'
}

import { marked } from 'marked'

marked.setOptions({ breaks: true })

export function renderContent(text: string): string {
  return marked.parse(text) as string
}
