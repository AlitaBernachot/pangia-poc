import ReactMarkdown from 'react-markdown'
import { ExternalLink } from 'lucide-react'
import { type Message, AGENT_COLORS } from '../../types'
import { AgentIcon } from '../AgentIcon'
import { AgentActivityPanel } from './AgentActivityPanel'
import { MapViewer } from '../MapViewer'
import { DataVizViewer } from '../DataViz/DataVizViewer'

const markdownComponents = {
  a: ({ href, children }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-0.5 text-blue-400 hover:text-blue-300 underline underline-offset-2"
    >
      {children}
      <ExternalLink size={11} className="shrink-0 opacity-70" />
    </a>
  ),
}

interface Props {
  message: Message
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex gap-3 items-start justify-end">
        <div className="max-w-[75%] bg-white/8 border border-white/10 rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white leading-relaxed">
          {message.content}
          {message.attachments && message.attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {message.attachments.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center gap-1.5 px-2 py-1 bg-white/8 rounded-md text-xs text-white/60"
                >
                  <span>📎</span>
                  <span className="truncate max-w-[120px]">{a.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex gap-3 items-start">
      <div className="flex flex-col gap-2.5 min-w-0 flex-1">
        {/* Routing chips */}
        {message.routingAgents && message.routingAgents.length > 0 && (
          <div className="flex items-center flex-wrap gap-1.5">
            <span className="text-xs text-white/40 font-medium">Routing to</span>
            {message.routingAgents.map((agent) => {
              const colors = AGENT_COLORS[agent]
              return (
                <span
                  key={agent}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border"
                  style={colors ? { color: colors.text, borderColor: colors.border, background: colors.bg } : {}}
                >
                  <AgentIcon agent={agent} size={11} /> {agent}
                </span>
              )
            })}
          </div>
        )}

        {/* Agent activity panels */}
        {message.agentActivity && message.agentActivity.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {message.agentActivity.map((activity) => (
              <AgentActivityPanel key={activity.agent} activity={activity} />
            ))}
          </div>
        )}

        {/* Map */}
        {message.geojson && <MapViewer geojson={message.geojson} />}

        {/* DataViz */}
        {message.dataviz && <DataVizViewer dataviz={message.dataviz} />}

        {/* Final answer — always last */}
        {(message.content || message.streaming) && (
          <div
            className={`rounded-xl rounded-tl-none px-4 py-3 text-sm text-white leading-relaxed prose-chat ${
              message.streaming ? 'border-white/8' : ''
            }`}
          >
            {message.content ? (
              <>
                <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
                {message.streaming && <span className="cursor-blink" />}
              </>
            ) : (
              message.streaming && (
                <span className="thinking-indicator">
                  Thinking...
                </span>
              )
            )}
          </div>
        )}
      </div>
    </div>
  )
}
