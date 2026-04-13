import { useState } from 'react'
import { ChevronDown, ChevronUp, Globe, Database, Zap, Shield, HelpCircle } from 'lucide-react'

interface FaqItem {
  question: string
  answer: string
}

const FAQ_ITEMS: FaqItem[] = [
  {
    question: 'What is PangIA?',
    answer:
      'PangIA (Pansophic Geospatial Intelligence Assistant) is an AI-powered platform that lets you query and analyse geospatial data using natural language. It connects to multiple specialised backends — including graph databases, RDF stores, vector search, and PostGIS — to provide rich, contextual answers about geographic information.',
  },
  {
    question: 'What kind of questions can I ask?',
    answer:
      'You can ask anything related to geospatial data. Examples: "Show me all hospitals within 5 km of the Eiffel Tower", "What environmental datasets are available for the Seine-Saint-Denis department?", "Find roads intersecting flood zones in Lyon", or "Visualise population density in Île-de-France". The assistant will route your query to the appropriate data agents.',
  },
  {
    question: 'Which data agents are available?',
    answer:
      'PangIA orchestrates several specialised agents: Neo4j (graph relationships), RDF/SPARQL (linked open data), Vector/Chroma (semantic search), PostGIS (spatial SQL), Map (geocoding & GeoJSON visualisation), Data.gouv.fr (French open data portal), and DataViz (chart & KPI generation). Agents can be toggled individually in the chat prompt.',
  },
  {
    question: 'Can I attach files to my messages?',
    answer:
      'Yes! You can attach files by clicking the paperclip icon or by dragging and dropping files onto the prompt. Image files will show a thumbnail preview. Note that file processing depends on the backend configuration — check with your administrator to confirm which file types are supported.',
  },
  {
    question: 'How does session memory work?',
    answer:
      'PangIA maintains conversation history within a session using a Redis-backed store. The AI can reference earlier messages in the same conversation. Starting a new chat (via the Clear button) begins a fresh session without prior context.',
  },
  {
    question: 'Is my data private?',
    answer:
      'Queries are processed server-side by the configured LLM provider and specialised agents. Please consult your organisation\'s data handling policies before submitting sensitive or personal information. The chat history is stored in Redis and is tied to a session identifier.',
  },
  {
    question: 'What do the agent activity panels mean?',
    answer:
      'When the assistant is generating a response, you may see collapsible panels for each agent that was queried. These show the agent\'s intermediate reasoning and any tools it invoked (e.g. database queries). Once the agent finishes, the panel collapses and a "done" badge is shown. This transparency helps you understand how the answer was constructed.',
  },
  {
    question: 'What browsers are supported?',
    answer:
      'PangIA works best in modern browsers — Chrome, Edge, Firefox, and Safari (latest versions). It requires JavaScript and support for Server-Sent Events (SSE) for the streaming chat feature.',
  },
]

const AGENTS_INFO = [
  {
    icon: <Database size={20} className="text-[#4ade80]" />,
    name: 'Neo4j',
    color: 'border-[#4ade80]/30 bg-[rgba(74,222,128,0.06)]',
    description: 'Graph database for relationship-rich queries.',
  },
  {
    icon: <Globe size={20} className="text-[#fb923c]" />,
    name: 'RDF / SPARQL',
    color: 'border-[#fb923c]/30 bg-[rgba(251,146,60,0.06)]',
    description: 'Linked open data & semantic web queries.',
  },
  {
    icon: <Zap size={20} className="text-[#60a5fa]" />,
    name: 'Vector / Chroma',
    color: 'border-[#60a5fa]/30 bg-[rgba(96,165,250,0.06)]',
    description: 'Semantic similarity & embedding search.',
  },
  {
    icon: <Globe size={20} className="text-[#38bdf8]" />,
    name: 'PostGIS',
    color: 'border-[#38bdf8]/30 bg-[rgba(56,189,248,0.06)]',
    description: 'Spatial SQL queries on geographic data.',
  },
  {
    icon: <Shield size={20} className="text-[#f43f5e]" />,
    name: 'Data.gouv.fr',
    color: 'border-[#f43f5e]/30 bg-[rgba(244,63,94,0.06)]',
    description: 'French government open data portal.',
  },
]

export function FaqPage() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  const toggle = (i: number) => setOpenIndex((prev) => (prev === i ? null : i))

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-12">
      {/* Hero */}
      <section className="text-center space-y-3">
        <div className="inline-flex size-14 rounded-2xl bg-cyan-500/15 border border-cyan-500/25 items-center justify-center">
          <HelpCircle size={26} className="text-cyan-400" />
        </div>
        <h1 className="text-3xl font-semibold text-white">FAQ & About</h1>
        <p className="text-white/50 text-sm max-w-lg mx-auto">
          Everything you need to know about PangIA — the Pansophic Geospatial Intelligence
          Assistant.
        </p>
      </section>

      {/* About section */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">About PangIA</h2>
        <div className="bg-white/3 border border-white/8 rounded-xl px-5 py-4 text-sm text-white/70 leading-relaxed space-y-3">
          <p>
            PangIA is an open-source proof-of-concept demonstrating how large language models can
            be combined with heterogeneous geospatial backends to deliver intelligent, multi-source
            geographic insights via a conversational interface.
          </p>
          <p>
            The backend is built with <strong className="text-white/80">FastAPI</strong> and{' '}
            <strong className="text-white/80">LangGraph</strong>, orchestrating a graph of
            specialised agents that each query a different data source. Responses are streamed in
            real time using Server-Sent Events.
          </p>
          <p>
            This frontend client is built with{' '}
            <strong className="text-white/80">React</strong>,{' '}
            <strong className="text-white/80">Vite</strong>, and{' '}
            <strong className="text-white/80">Tailwind CSS</strong>. File attachment support is
            modelled after the{' '}
            <a
              href="https://elements.ai-sdk.dev/components/attachments"
              target="_blank"
              rel="noreferrer"
              className="text-blue-400 underline"
            >
              AI SDK Elements Attachments
            </a>{' '}
            component pattern.
          </p>
        </div>

        {/* Agent grid */}
        <div className="grid sm:grid-cols-2 gap-3">
          {AGENTS_INFO.map((agent) => (
            <div
              key={agent.name}
              className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-sm ${agent.color}`}
            >
              <span className="mt-0.5 shrink-0">{agent.icon}</span>
              <div>
                <p className="font-medium text-white/90">{agent.name}</p>
                <p className="text-white/50 text-xs">{agent.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ accordion */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-white">Frequently Asked Questions</h2>
        <div className="space-y-2">
          {FAQ_ITEMS.map((item, i) => (
            <div
              key={i}
              className="border border-white/8 rounded-xl overflow-hidden bg-white/2"
            >
              <button
                type="button"
                onClick={() => toggle(i)}
                className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left text-sm font-medium text-white/80 hover:text-white hover:bg-white/3 transition-colors"
              >
                <span>{item.question}</span>
                {openIndex === i ? (
                  <ChevronUp size={16} className="text-white/40 shrink-0" />
                ) : (
                  <ChevronDown size={16} className="text-white/40 shrink-0" />
                )}
              </button>

              {openIndex === i && (
                <div className="px-5 pb-4 text-sm text-white/55 leading-relaxed border-t border-white/6 pt-3">
                  {item.answer}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Footer note */}
      <p className="text-center text-xs text-white/25 pb-4">
        PangIA · Open-source Proof of Concept ·{' '}
        <a
          href="https://github.com/AlitaBernachot/PangIA-poc"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-white/50 transition-colors"
        >
          GitHub
        </a>
      </p>
    </div>
  )
}
