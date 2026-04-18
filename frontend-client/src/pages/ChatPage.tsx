// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useState } from 'react'
import { usePangiaChat } from '../hooks/usePangiaChat'
import { MessageList } from '../components/chat/MessageList'
import { PromptInput } from '../components/chat/PromptInput'
import type { Attachment } from '../types'

export function ChatPage() {
  const {
    messages,
    isStreaming,
    agents,
    selectedSources,
    setSelectedSources,
    sendMessage,
    stopStreaming,
    clearMessages,
    fetchAgents,
    hitlRequest,
    dismissHitl,
    submitHitlResponse,
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
        onHitlDismiss={dismissHitl}
        onHitlSubmit={submitHitlResponse}
      />

      {/* Prompt */}
      <PromptInput
        isStreaming={isStreaming}
        availableAgents={agents}
        selectedSources={selectedSources}
        onSelectedAgentsChange={setSelectedSources}
        onSubmit={handleSubmit}
        onStop={stopStreaming}
        prefillText={prefillText}
        onPrefillConsumed={() => setPrefillText(undefined)}
      />
    </div>
  )
}
