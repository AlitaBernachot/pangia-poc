// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { MessageSquare } from 'lucide-react'
import type { HITLRequestEvent } from '../../types'

interface Props {
  request: HITLRequestEvent
  onSelectQuestion: (question: string) => void
  onDismiss: () => void
}

export function HITLChatInline({ request, onSelectQuestion, onDismiss }: Props) {
  return (
    <div className="flex gap-3 items-start">
      <div className="flex flex-col gap-2.5 min-w-0 flex-1">
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl px-4 py-3 flex flex-col gap-3">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-400">
              <MessageSquare size={15} />
              <span className="font-semibold text-sm">Clarification needed</span>
            </div>
            <button
              onClick={onDismiss}
              className="text-white/30 hover:text-white/60 text-xs transition-colors"
            >
              Dismiss
            </button>
          </div>

          {/* Original query */}
          <div className="text-xs text-white/50 bg-white/5 rounded-lg px-3 py-2">
            <span className="text-white/30 mr-1">Original:</span>
            {request.original_query}
          </div>

          {/* Clarifying questions — click to prefill the main prompt */}
          {request.questions.length > 0 && (
            <ul className="flex flex-col gap-1.5">
              {request.questions.map((q, i) => (
                <li key={i} className="text-sm text-white/80 flex gap-2 items-start">
                  <span className="text-amber-400 shrink-0 mt-0.5">•</span>
                  <span
                    className="cursor-pointer hover:text-white transition-colors"
                    onClick={() => onSelectQuestion(q)}
                    title="Click to use as answer"
                  >
                    {q}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs text-white/30">
            Click a suggestion above or type your clarification in the prompt below.
          </p>
        </div>
      </div>
    </div>
  )
}
