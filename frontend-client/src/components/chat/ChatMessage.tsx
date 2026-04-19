// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import ReactMarkdown from 'react-markdown'
import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { type Message, AGENT_COLORS } from '../../types'
import { AgentIcon } from '../AgentIcon'
import { AgentActivityPanel } from './AgentActivityPanel'
import { MapViewer } from '../MapViewer'
import { DataVizViewer } from '../DataViz/DataVizViewer'
import { DatasetChoicePanel } from './DatasetChoicePanel'

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
  onSubmitChoice?: (chosenId: string, chosenQuery: string) => void
  onPrefillPrompt?: (text: string) => void
  isStreaming?: boolean
  awaitingClarification?: boolean
}

export function ChatMessage({ message, onSubmitChoice, onPrefillPrompt, isStreaming, awaitingClarification }: Props) {
  const { t } = useTranslation()
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
            <span className="text-xs text-white/40 font-medium">{t('chatMessage.routingTo')}</span>
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

        {/* Map — GeoJSON and/or OGC API Features layers */}
        {(message.geojson || message.ogcLayers?.length) && (
          <MapViewer geojson={message.geojson} ogcLayers={message.ogcLayers} />
        )}

        {/* DataViz */}
        {message.dataviz && <DataVizViewer dataviz={message.dataviz} />}

        {/* Dataset choice — agent-level disambiguation */}
        {message.choiceRequest && message.choiceRequest.items.length > 0 && (
          <DatasetChoicePanel
            candidates={message.choiceRequest.items}
            total={message.choiceRequest.total}
            onSelect={(candidate) => onSubmitChoice?.(candidate.id, `Je veux travailler avec le dataset : "${candidate.title}"${candidate.id ? ` (ID: ${candidate.id})` : ''}`)}
            onPrefillPrompt={onPrefillPrompt}
          />
        )}

        {/* Final answer / thinking indicator */}
        {(message.content || message.streaming) && (
          <div
            className={`px-4 py-3 text-sm text-white leading-relaxed prose-chat`}
          >
            {!message.streaming && message.content ? (
              // Show text only after streaming is fully done so it always appears
              // below map/dataviz (which are set by dataviz_node / mapviz_node
              // post-processing that fires after merge_node's final_answer).
              <ReactMarkdown components={markdownComponents}>{message.content}</ReactMarkdown>
            ) : (
              message.streaming && !message.geojson && !message.dataviz && !message.choiceRequest?.items.length && (
                <span className="thinking-indicator">
                  {awaitingClarification ? t('hitl.awaitingClarification') : t('chatMessage.thinking')}
                </span>
              )
            )}
          </div>
        )}
      </div>
    </div>
  )
}
