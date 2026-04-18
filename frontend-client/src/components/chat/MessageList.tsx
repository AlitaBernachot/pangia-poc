// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2 } from 'lucide-react'
import { type Message, type DatasetCandidate, type HITLRequestEvent } from '../../types'
import { ChatMessage } from './ChatMessage'
import { HITLChatInline } from './HITLChatInline'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

interface Props {
  messages: Message[]
  onSuggestion?: (text: string) => void
  onSendMessage?: (text: string) => void
  onPrefillPrompt?: (text: string) => void
  onClear?: () => void
  isStreaming?: boolean
  hitlRequest?: HITLRequestEvent | null
  onHitlDismiss?: () => void
}

function useSuggestions(): string[] {
  const [suggestions, setSuggestions] = useState<string[]>([])

  useEffect(() => {
    fetch(`${API_BASE}/api/suggestions`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.suggestions?.length) setSuggestions(data.suggestions)
      })
      .catch(() => {
        // backend not available yet — keep empty
      })
  }, [])

  return suggestions
}

export function MessageList({ messages, onSuggestion, onSendMessage, onPrefillPrompt, onClear, isStreaming, hitlRequest, onHitlDismiss }: Props) {
  const { t } = useTranslation()
  const bottomRef = useRef<HTMLDivElement>(null)
  const suggestions = useSuggestions()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-4 gap-8">
        {/* Hero */}
        <div className="text-center space-y-3">
          <div className="flex items-center justify-center mx-auto">
            <img src="/logo.png" alt="PangIA" className="size-20" />
          </div>
          <h2 className="text-2xl font-semibold text-white">{t('messageList.title')}</h2>
          <p className="text-white/50 text-sm max-w-sm">
            {t('messageList.subtitle')}
          </p>
        </div>

        {/* Suggestion chips */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl w-full">
          {suggestions.map((s) => (
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
          <ChatMessage
            key={msg.id}
            message={msg}
            onSelectDataset={(candidate: DatasetCandidate) =>
              onSendMessage?.(
                `Je veux travailler avec le dataset : "${candidate.title}"${candidate.id ? ` (ID: ${candidate.id})` : ''}`,
              )
            }
            onPrefillPrompt={onPrefillPrompt}
            isStreaming={isStreaming}
            awaitingClarification={!!hitlRequest && !!msg.streaming}
          />
        ))}
        {messages.length > 0 && !isStreaming && onClear && (
          <div className="flex justify-center pt-2">
            <button
              type="button"
              onClick={onClear}
              title={t('chat.clearConversation')}
              className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs text-white/30 hover:text-white/60 hover:bg-white/5 transition-colors"
            >
              <Trash2 size={12} />
              {t('chat.clear')}
            </button>
          </div>
        )}
        {hitlRequest && onHitlDismiss && (
          <HITLChatInline
            request={hitlRequest}
            onSelectQuestion={(q) => {
              onHitlDismiss()
              onSendMessage?.(q)
            }}
            onDismiss={onHitlDismiss}
          />
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

