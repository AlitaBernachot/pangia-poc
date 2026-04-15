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
import { ArrowUp, Paperclip, X, File, Square, Share2, Link2, Layers, Map, Globe, BarChart2, Bot } from 'lucide-react'
import type { AgentInfo, Attachment } from '../../types'

interface Props {
  isStreaming: boolean
  availableAgents: AgentInfo[]
  selectedAgents: string[]
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

const AGENT_COLORS_MAP: Record<string, string> = {
  'Neo4j':        'border-[#4ade80] text-[#4ade80] bg-[rgba(74,222,128,0.10)]',
  'RDF/SPARQL':   'border-[#fb923c] text-[#fb923c] bg-[rgba(251,146,60,0.10)]',
  'Vector':       'border-[#60a5fa] text-[#60a5fa] bg-[rgba(96,165,250,0.10)]',
  'PostGIS':      'border-[#38bdf8] text-[#38bdf8] bg-[rgba(56,189,248,0.10)]',
  'Data.gouv.fr': 'border-[#f43f5e] text-[#f43f5e] bg-[rgba(244,63,94,0.10)]',
}

function agentActiveClass(label: string): string {
  return AGENT_COLORS_MAP[label] ?? 'border-white/40 text-white/80 bg-white/5'
}

const AGENT_ICONS: Record<string, React.ReactElement> = {
  'Neo4j':        <Share2 size={12} />,
  'RDF/SPARQL':   <Link2 size={12} />,
  'Vector':       <Layers size={12} />,
  'PostGIS':      <Map size={12} />,
  'Data.gouv.fr': <Globe size={12} />,
  'DataViz':      <BarChart2 size={12} />,
}

export function PromptInput({
  isStreaming,
  availableAgents,
  selectedAgents,
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
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const toggleAgent = (key: string) => {
    if (selectedAgents.includes(key)) {
      if (selectedAgents.length > 1) {
        onSelectedAgentsChange(selectedAgents.filter((k) => k !== key))
      }
    } else {
      onSelectedAgentsChange([...selectedAgents, key])
    }
  }

  const isAgentSelected = (key: string) => selectedAgents.includes(key)

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
          disabled={isStreaming}
          className="w-full bg-transparent border-none outline-none resize-none text-sm text-white placeholder:text-white/30 leading-relaxed px-4 pt-4 pb-2 min-h-14 max-h-40 overflow-y-auto font-sans disabled:cursor-not-allowed"
        />

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
          {/* Left: attach button + agent toggles */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Attach button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming}
              title={t('promptInput.attachFiles')}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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

            {/* Agent toggles */}
            {availableAgents.map((agent) => (
              <button
                key={agent.key}
                type="button"
                onClick={() => toggleAgent(agent.key)}
                title={isAgentSelected(agent.key) ? t('promptInput.deselectAgent', { agent: agent.label }) : t('promptInput.selectAgent', { agent: agent.label })}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border transition-colors duration-150 cursor-pointer select-none ${
                  isAgentSelected(agent.key)
                    ? agentActiveClass(agent.label)
                    : 'border-white/15 text-white/30 bg-transparent hover:text-white/50'
                }`}
              >
                {AGENT_ICONS[agent.label] ?? <Bot size={12} />}
                {agent.label}
              </button>
            ))}
          </div>

          {/* Right: send / stop button */}
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
