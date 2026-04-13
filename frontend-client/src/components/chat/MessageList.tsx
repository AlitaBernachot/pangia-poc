import { useEffect, useRef } from 'react'
import { type Message } from '../../types'
import { ChatMessage } from './ChatMessage'
import { Bot } from 'lucide-react'

interface Props {
  messages: Message[]
  onSuggestion?: (text: string) => void
}

const SUGGESTIONS = [
  'What geospatial datasets are available?',
  'Show me flood-prone areas in Paris',
  'Find all hospitals within 5km of the city center',
  'What are the latest environmental data updates?',
]

export function MessageList({ messages, onSuggestion }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-4 gap-8">
        {/* Hero */}
        <div className="text-center space-y-3">
          <div className="size-16 rounded-2xl bg-yellow-500/15 border border-yellow-500/25 flex items-center justify-center mx-auto">
            <Bot size={28} className="text-yellow-400" />
          </div>
          <h2 className="text-2xl font-semibold text-white">PanGIA Assistant</h2>
          <p className="text-white/50 text-sm max-w-sm">
            Your intelligent geospatial AI. Ask questions about geographic data, maps, spatial
            analysis, and more.
          </p>
        </div>

        {/* Suggestion chips */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl w-full">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSuggestion?.(s)}
              className="text-left px-4 py-3 rounded-xl border border-white/10 bg-white/3 hover:bg-white/6 text-sm text-white/60 hover:text-white/80 transition-colors cursor-pointer"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-6">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

