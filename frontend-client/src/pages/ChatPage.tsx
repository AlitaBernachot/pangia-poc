// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect } from 'react'
import { Trash2 } from 'lucide-react'
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
      <div className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-white/6">
    {messages.length > 0 && (
          <button
            type="button"
            onClick={clearMessages}
            title={t('chat.clearConversation')}
            className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors"
          >
            <Trash2 size={12} />
            {t('chat.clear')}
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
