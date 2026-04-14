import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { usePangiaChat } from '../hooks/usePangiaChat'
import { MessageList } from '../components/chat/MessageList'
import { PromptInput } from '../components/chat/PromptInput'
import type { Attachment } from '../types'

export function ChatPage() {
  const { t } = useTranslation()
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
      <div className="shrink-0 border-b border-white/6" />

      {/* Messages */}
      <MessageList messages={messages} onSuggestion={(text) => sendMessage(text)} onClear={clearMessages} isStreaming={isStreaming} />

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
