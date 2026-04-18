// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { MessageSquare } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { HITLRequestEvent } from '../../types'

interface Props {
  request: HITLRequestEvent
  onSelectQuestion: (question: string) => void
  onDismiss: () => void
}

export function HITLChatInline({ request, onSelectQuestion, onDismiss }: Props) {
  const { t } = useTranslation()

  return (
    <div className="flex gap-3 items-start">
      <div className="flex flex-col gap-2.5 min-w-0 flex-1">
        <div className="bg-white/5 border border-white/8 rounded-2xl px-4 py-3 flex flex-col gap-3">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-white/60">
              <MessageSquare size={15} />
              <span className="font-semibold text-sm">{t('hitl.clarificationNeeded')}</span>
            </div>
            <button
              onClick={onDismiss}
              className="text-white/30 hover:text-white/60 text-xs transition-colors"
            >
              {t('hitl.dismiss')}
            </button>
          </div>

          {/* Clarifying questions — click to send directly to the workflow */}
          {request.questions.length > 0 && (
            <ul className="flex flex-col gap-1.5">
              {request.questions.map((q, i) => (
                <li key={i} className="text-sm text-white/80 flex gap-2 items-start">
                  <span className="text-white/30 shrink-0 mt-0.5">•</span>
                  <span
                    className="cursor-pointer hover:text-white transition-colors"
                    onClick={() => onSelectQuestion(q)}
                    title={t('hitl.clickHint')}
                  >
                    {q}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs text-white/30">
            {t('hitl.hint')}
          </p>
        </div>
      </div>
    </div>
  )
}
