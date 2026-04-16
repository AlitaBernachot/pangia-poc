import { ExternalLink, Database } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { DatasetCandidate } from '../../types'

interface Props {
  candidates: DatasetCandidate[]
  onSelect: (candidate: DatasetCandidate) => void
  onPrefillPrompt?: (title: string) => void
  disabled?: boolean
}

export function DatasetChoicePanel({ candidates, onSelect, onPrefillPrompt, disabled }: Props) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-2 w-full">
      <p className="text-xs text-white/50 font-medium uppercase tracking-wide">
        {t('datasetChoice.prompt', { count: candidates.length })}
      </p>
      <div className="flex flex-col gap-2">
        {candidates.map((candidate) => (
          <div
            key={candidate.id}
            className="flex items-start gap-3 p-3 rounded-xl border border-white/10 bg-white/3 hover:bg-white/6 hover:border-white/20 transition-colors group"
          >
            {/* Icon */}
            <div className="mt-0.5 shrink-0 text-white/40 group-hover:text-white/70 transition-colors">
              <Database size={16} />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-start gap-2">
                {/* Clickable title — pre-fills the prompt input */}
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    const idPart = candidate.id ? ` (ID: ${candidate.id})` : ''
                    onPrefillPrompt?.(`${t('datasetChoice.prefillPrefix')} "${candidate.title}"${idPart}`)
                  }}
                  title={t('datasetChoice.clickTitle')}
                  className="text-sm font-medium text-white leading-snug text-left hover:text-white/70 hover:underline underline-offset-2 transition-colors disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
                >
                  {candidate.title}
                </button>
              </div>
              {candidate.organization && (
                <span className="text-xs text-white/40">{candidate.organization}</span>
              )}
              {candidate.url && (
                <a
                  href={candidate.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-start gap-1 text-xs text-blue-400/70 hover:text-blue-400 break-all mt-0.5 transition-colors"
                >
                  <ExternalLink size={11} className="shrink-0" />
                  {candidate.url}
                </a>
              )}
              {candidate.description && (
                <p className="text-xs text-white/50 mt-1 line-clamp-2">
                  {candidate.description}
                </p>
              )}
            </div>

            {/* Select button — sends immediately */}
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSelect(candidate)}
              className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/8 text-white/70 border border-white/15 hover:bg-white/12 hover:border-white/25 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {t('datasetChoice.select')}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
