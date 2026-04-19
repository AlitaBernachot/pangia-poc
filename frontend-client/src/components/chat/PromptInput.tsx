// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import {
  useRef,
  useState,
  useCallback,
  useEffect,
  type ChangeEvent,
  type KeyboardEvent,
  type DragEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, Paperclip, X, File, Square, ChevronUp, Database, Check } from 'lucide-react'
import type { AgentInfo, Attachment } from '../../types'
import { AgentIcon } from '../AgentIcon'

interface Props {
  isStreaming: boolean
  availableAgents: AgentInfo[]
  selectedSources: string[]
  onSelectedAgentsChange: (keys: string[]) => void
  onSubmit: (text: string, attachments: Attachment[]) => void
  onStop?: () => void
  /** When set, pre-fills the textarea with this text and focuses it. */
  prefillText?: string
  /** Called once the prefill has been consumed so the parent can clear the value. */
  onPrefillConsumed?: () => void
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImageType(type: string): boolean {
  return type.startsWith('image/')
}

export function PromptInput({
  isStreaming,
  availableAgents,
  selectedSources,
  onSelectedAgentsChange,
  onSubmit,
  onStop,
  prefillText,
  onPrefillConsumed,
}: Props) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState('')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [agentMenuOpen, setAgentMenuOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const agentMenuRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (agentMenuRef.current && !agentMenuRef.current.contains(e.target as Node)) {
        setAgentMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [])

  // When a prefill is requested, set the draft and focus the textarea.
  useEffect(() => {
    if (!prefillText) return
    setDraft(prefillText)
    // Allow the DOM to update before resizing and focusing
    requestAnimationFrame(() => {
      autoResize()
      textareaRef.current?.focus()
    })
    onPrefillConsumed?.()
  }, [prefillText, autoResize, onPrefillConsumed])

  const handleSubmit = () => {
    const text = draft.trim()
    if ((!text && attachments.length === 0) || isStreaming) return
    onSubmit(text, attachments)
    setDraft('')
    setAttachments([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  // ─── Attachment handling ────────────────────────────────────────────────────

  const addFiles = useCallback((files: FileList | File[]) => {
    const newAttachments: Attachment[] = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      type: file.type,
      url: URL.createObjectURL(file),
      size: file.size,
    }))
    setAttachments((prev) => [...prev, ...newAttachments])
  }, [])

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files)
    e.target.value = ''
  }

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const removed = prev.find((a) => a.id === id)
      if (removed) URL.revokeObjectURL(removed.url)
      return prev.filter((a) => a.id !== id)
    })
  }

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => setIsDragging(false)

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files) addFiles(e.dataTransfer.files)
  }

  // ─── Agent selector ─────────────────────────────────────────────────────────

  return (
    <div className="shrink-0 px-4 pb-5 pt-3">
      <div
        className={`mx-auto max-w-3xl rounded-xl border bg-white/4 backdrop-blur flex flex-col transition-all duration-150 ${
          isDragging
            ? 'border-cyan-400/60 bg-cyan-500/5'
            : isStreaming
              ? 'border-white/8 opacity-90'
              : 'border-white/10 focus-within:border-cyan-500/60'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drag overlay hint */}
        {isDragging && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl pointer-events-none z-10">
          <span className="text-sm text-cyan-300 font-medium">{t('promptInput.dropFiles')}</span>
          </div>
        )}

        {/* Attachment previews */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pt-3">
            {attachments.map((att) => (
              <AttachmentPreview
                key={att.id}
                attachment={att}
                onRemove={() => removeAttachment(att.id)}
              />
            ))}
          </div>
        )}

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            autoResize()
          }}
          onKeyDown={handleKeyDown}
          placeholder={isDragging ? '' : t('promptInput.placeholder')}
          rows={1}
          className="w-full bg-transparent border-none outline-none resize-none text-sm text-white placeholder:text-white/30 leading-relaxed px-4 pt-4 pb-2 min-h-14 max-h-40 overflow-y-auto font-sans"
        />

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
          {/* Left: attach button */}
          <div className="flex items-center gap-1.5">
            {/* Attach button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title={t('promptInput.attachFiles')}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors"
            >
              <Paperclip size={13} />
              <span>{t('promptInput.attach')}</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          {/* Right: sources dropdown + send / stop button */}
          <div className="flex items-center gap-1.5">
            {/* Agent source dropdown */}
            <div ref={agentMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setAgentMenuOpen((o) => !o)}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors select-none"
              >
                <Database size={13} />
                <span>{t('promptInput.sources')}</span>
                {selectedSources.length < availableAgents.length && (
                  <span className="ml-0.5 px-1 py-0 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-semibold leading-4">
                    {selectedSources.length}
                  </span>
                )}
                <ChevronUp
                  size={11}
                  className={`transition-transform duration-150 ${agentMenuOpen ? 'rotate-180' : ''}`}
                />
              </button>

              {agentMenuOpen && (
                <div className="absolute bottom-full right-0 mb-1.5 w-52 rounded-lg border border-white/10 bg-[#1a1a20] shadow-xl z-50 py-1 overflow-hidden">
                  <p className="px-3 pt-1.5 pb-1 text-[10px] font-semibold text-white/30 uppercase tracking-wider">
                    {t('promptInput.sourcesLabel')}
                  </p>
                  {availableAgents.map((agent) => {
                    const selected = selectedSources.includes(agent.key)
                    const isLast = selectedSources.length === 1 && selected
                    return (
                      <button
                        key={agent.key}
                        type="button"
                        onClick={() => {
                          if (selected) {
                            if (!isLast) onSelectedAgentsChange(selectedSources.filter((k) => k !== agent.key))
                          } else {
                            onSelectedAgentsChange([...selectedSources, agent.key])
                          }
                        }}
                        disabled={isLast}
                        className="w-full flex items-center gap-2.5 px-3 py-1.5 text-xs hover:bg-white/5 transition-colors disabled:cursor-not-allowed"
                      >
                        <span className={`size-3.5 shrink-0 rounded flex items-center justify-center border transition-colors ${
                          selected
                            ? 'bg-cyan-500 border-cyan-500 text-black'
                            : 'border-white/20 bg-transparent'
                        }`}>
                          {selected && <Check size={9} strokeWidth={3} />}
                        </span>
                        <AgentIcon agent={agent.label} size={11} />
                        <span className={selected ? 'text-white/80' : 'text-white/40'}>{agent.label}</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

          {/* Send / stop button */}
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              title={t('promptInput.stopGenerating')}
              className="size-8 p-0 shrink-0 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors"
            >
              <Square size={14} className="text-white" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={(!draft.trim() && attachments.length === 0) || isStreaming}
              title={t('promptInput.send')}
              className="size-8 p-0 shrink-0 rounded-full bg-white flex items-center justify-center hover:bg-white/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ArrowUp size={15} className="text-black" />
            </button>
          )}
          </div>
        </div>
      </div>

      <p className="text-center text-xs text-white/20 mt-2">
        {t('promptInput.hint')}
      </p>
    </div>
  )
}

// ─── Attachment preview component ─────────────────────────────────────────────

interface AttachmentPreviewProps {
  attachment: Attachment
  onRemove: () => void
}

function AttachmentPreview({ attachment, onRemove }: AttachmentPreviewProps) {
  const { t } = useTranslation()
  return (
    <div className="relative group flex items-center gap-2 bg-white/8 border border-white/12 rounded-lg p-1.5 pr-2 text-xs text-white/70 max-w-[180px]">
      {isImageType(attachment.type) ? (
        <img
          src={attachment.url}
          alt={attachment.name}
          className="size-10 rounded object-cover shrink-0"
        />
      ) : (
        <div className="size-10 rounded bg-white/8 flex items-center justify-center shrink-0">
          <File size={18} className="text-white/40" />
        </div>
      )}

      <div className="min-w-0">
        <p className="truncate font-medium text-white/80 leading-tight">{attachment.name}</p>
        <p className="text-white/35 text-[10px]">{formatSize(attachment.size)}</p>
      </div>

      <button
        type="button"
        onClick={onRemove}
        className="absolute -top-1.5 -right-1.5 size-4 rounded-full bg-zinc-700 border border-white/20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-zinc-600"
        title={t('promptInput.removeAttachment')}
      >
        <X size={9} className="text-white" />
      </button>
    </div>
  )
}
