import ReactMarkdown from 'react-markdown'
import { type Message, AGENT_COLORS, agentIcon } from '../../types'
import { AgentActivityPanel } from './AgentActivityPanel'
import { User, Bot } from 'lucide-react'

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
        <div className="size-8 rounded-full bg-white/10 flex items-center justify-center shrink-0 mt-0.5">
          <User size={14} className="text-white/60" />
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex gap-3 items-start">
      <div className="size-8 rounded-full bg-yellow-500/20 flex items-center justify-center shrink-0 mt-0.5">
        <Bot size={14} className="text-yellow-300" />
      </div>

      <div className="flex flex-col gap-2.5 min-w-0 flex-1 max-w-[82%]">
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
                  {agentIcon(agent)} {agent}
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

        {/* Final answer */}
        {(message.content || message.streaming) && (
          <div
            className={`bg-white/4 border rounded-xl rounded-tl-none px-4 py-3 text-sm text-white leading-relaxed prose-chat ${
              message.streaming ? 'border-violet-500/50' : 'border-white/8'
            }`}
          >
            {message.content ? (
              <ReactMarkdown>{message.content}</ReactMarkdown>
            ) : (
              message.streaming && <span className="cursor-blink" />
            )}
            {message.streaming && message.content && <span className="cursor-blink" />}
          </div>
        )}
      </div>
    </div>
  )
}
