// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useState } from 'react'
import { MessageSquare, Send, X } from 'lucide-react'
import type { HITLRequestEvent } from '../../types'

interface Props {
  request: HITLRequestEvent
  apiBase: string
  onResolved: (clarifiedQuery: string) => void
  onDismiss: () => void
}

export function HITLModal({ request, apiBase, onResolved, onDismiss }: Props) {
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    const trimmed = answer.trim()
    if (!trimmed) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/api/hitl/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: request.request_id, clarified_query: trimmed }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      onResolved(trimmed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send response')
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg mx-4 bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-amber-400">
            <MessageSquare size={18} />
            <span className="font-semibold text-sm">Clarification needed</span>
          </div>
          <button
            onClick={onDismiss}
            className="text-white/40 hover:text-white/80 transition-colors"
            aria-label="Dismiss"
          >
            <X size={16} />
          </button>
        </div>

        {/* Original query */}
        <div className="text-xs text-white/50 bg-white/5 rounded-lg px-3 py-2">
          <span className="text-white/30 mr-1">Original:</span>
          {request.original_query}
        </div>

        {/* Clarifying questions */}
        {request.questions.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {request.questions.map((q, i) => (
              <li key={i} className="text-sm text-white/80 flex gap-2 items-start">
                <span className="text-amber-400 shrink-0 mt-0.5">•</span>
                <span
                  className="cursor-pointer hover:text-white transition-colors"
                  onClick={() => setAnswer(q)}
                  title="Click to use as answer"
                >
                  {q}
                </span>
              </li>
            ))}
          </ul>
        )}

        {/* Answer textarea */}
        <textarea
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 resize-none focus:outline-none focus:border-amber-400/50 transition-colors"
          rows={3}
          placeholder="Type your clarification here…"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit()
          }}
          disabled={submitting}
        />

        {error && <p className="text-xs text-red-400">{error}</p>}

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          <button
            onClick={onDismiss}
            disabled={submitting}
            className="px-3 py-1.5 text-xs rounded-lg border border-white/10 text-white/60 hover:text-white hover:border-white/20 transition-colors disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !answer.trim()}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-lg bg-amber-500 hover:bg-amber-400 text-black font-medium transition-colors disabled:opacity-40"
          >
            <Send size={12} />
            {submitting ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
