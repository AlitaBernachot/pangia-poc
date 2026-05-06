// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from 'react'

interface Props {
  /** Content rendered in the header area (title + optional icon). */
  header: ReactNode
  /** Main body content. */
  body: ReactNode
  /** Footer content (typically action buttons). */
  footer: ReactNode
  /** Called when the backdrop is clicked. */
  onClose: () => void
}

/**
 * Generic modal overlay with header / body / footer slots.
 * Closes when the backdrop is clicked.
 */
export function Modal({ header, body, footer, onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md mx-4 rounded-2xl border border-white/12 bg-[#18181b] shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-0">
          {header}
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {body}
        </div>

        {/* Footer */}
        <div className="px-6 pb-6 flex gap-2 justify-end">
          {footer}
        </div>
      </div>
    </div>
  )
}
