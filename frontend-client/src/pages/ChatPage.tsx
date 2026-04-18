// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useState } from 'react'
import { usePangiaChat } from '../hooks/usePangiaChat'
import { MessageList } from '../components/chat/MessageList'
import { PromptInput } from '../components/chat/PromptInput'
import type { Attachment } from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

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
    hitlRequest,
    dismissHitl,
  } = usePangiaChat()

  const [prefillText, setPrefillText] = useState<string | undefined>(undefined)

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
      <MessageList
        messages={messages}
        onSuggestion={(text) => sendMessage(text)}
        onSendMessage={(text) => sendMessage(text)}
        onPrefillPrompt={(text) => setPrefillText(text)}
        onClear={clearMessages}
        isStreaming={isStreaming}
        hitlRequest={hitlRequest}
        hitlApiBase={API_BASE}
        onHitlResolved={(clarifiedQuery) => {
          dismissHitl()
          sendMessage(clarifiedQuery)
        }}
        onHitlDismiss={dismissHitl}
      />

      {/* Prompt */}
      <PromptInput
        isStreaming={isStreaming}
        availableAgents={agents}
        selectedAgents={selectedAgents}
        onSelectedAgentsChange={setSelectedAgents}
        onSubmit={handleSubmit}
        onStop={stopStreaming}
        prefillText={prefillText}
        onPrefillConsumed={() => setPrefillText(undefined)}
      />
    </div>
  )
}
