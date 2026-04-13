import { useEffect } from 'react'
import { Trash2 } from 'lucide-react'
import { usePangiaChat } from '../hooks/usePangiaChat'
import { MessageList } from '../components/chat/MessageList'
import { PromptInput } from '../components/chat/PromptInput'
import type { Attachment } from '../types'

export function ChatPage() {
  const {
    messages,
    isStreaming,
    agents,
    selectedAgents,
    setSelectedAgents,
    sendMessage,
    stopStreaming,
    clearMessages,
    fetchAgents,
  } = usePangiaChat()

  useEffect(() => {
    fetchAgents()
  }, [fetchAgents])

  const handleSubmit = (text: string, _attachments: Attachment[]) => {
    sendMessage(text)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-white/6">
        <div className="flex items-center gap-2">
          <h1 className="text-sm font-medium text-white/70">AI Chat</h1>
          {isStreaming && (
            <span className="inline-flex items-center gap-1 text-xs text-amber-400">
              <span className="size-1.5 rounded-full bg-amber-400 animate-pulse" />
              Thinking…
            </span>
          )}
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={clearMessages}
            title="Clear conversation"
            className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors"
          >
            <Trash2 size={12} />
            Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <MessageList messages={messages} onSuggestion={(text) => sendMessage(text)} />

      {/* Prompt */}
      <PromptInput
        isStreaming={isStreaming}
        availableAgents={agents}
        selectedAgents={selectedAgents}
        onSelectedAgentsChange={setSelectedAgents}
        onSubmit={handleSubmit}
        onStop={stopStreaming}
      />
    </div>
  )
}
