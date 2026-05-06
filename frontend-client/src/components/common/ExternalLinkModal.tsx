// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Modal } from './Modal'

interface Props {
  url: string
  onConfirm: () => void
  onCancel: () => void
}

/**
 * Confirmation modal shown before navigating to an untrusted external URL.
 */
export function ExternalLinkModal({ url, onConfirm, onCancel }: Props) {
  const { t } = useTranslation()

  return (
    <Modal
      onClose={onCancel}
      header={
        <div className="flex items-start gap-3">
          <AlertTriangle size={20} className="shrink-0 text-amber-400 mt-0.5" />
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-white">{t('externalLink.title')}</p>
            <p className="text-xs text-white/55 leading-relaxed">{t('externalLink.warning')}</p>
          </div>
        </div>
      }
      body={
        <div className="rounded-lg bg-white/5 border border-white/8 px-3 py-2">
          <p className="text-[10px] text-white/35 uppercase tracking-wide mb-0.5">{t('externalLink.url')}</p>
          <p className="text-xs text-blue-400 break-all">{url}</p>
        </div>
      }
      footer={
        <>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-xs rounded-lg border border-white/12 text-white/60 hover:text-white hover:border-white/25 transition-colors cursor-pointer"
          >
            {t('externalLink.cancel')}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 text-xs rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors cursor-pointer"
          >
            {t('externalLink.continue')}
          </button>
        </>
      }
    />
  )
}
