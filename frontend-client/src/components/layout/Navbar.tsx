// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { NavLink } from 'react-router-dom'
import { MessageSquare, HelpCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from './LanguageSwitcher'

interface Props {
  sessionTitle?: string
  sessionId?: string | null
}

export function Navbar({ sessionTitle, sessionId }: Props) {
  const { t } = useTranslation()

  return (
    <header className="flex items-center justify-between px-5 h-14 border-b border-white/8 bg-[#0d0d0f]/80 backdrop-blur-sm sticky top-0 z-50">
      <a href="/" className="flex items-center gap-2 text-white font-semibold text-lg shrink-0">
        <img src="/logo.png" alt="PangIA" className="size-7 rounded" />
        <span>PangIA</span>
      </a>

      {/* Session title + id tag — right of the logo */}
      {sessionTitle && (
        <div className="ml-8 flex items-center gap-2 min-w-0">
          <span id="session-title" className="text-xs font-semibold uppercase tracking-widest truncate max-w-[260px]">
            {sessionTitle}
          </span>
          {sessionId && (
            <span
              title={sessionId}
              className="shrink-0 font-mono text-[10px] text-white/40 bg-white/5 border border-white/10 rounded px-1.5 py-0.5"
            >
              {sessionId.slice(0, 8)}
            </span>
          )}
        </div>
      )}

      <div className="flex-1" />

      <div className="flex items-center gap-3 shrink-0">
        <nav className="flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'text-white bg-white/10'
                  : 'text-white/50 hover:text-white hover:bg-white/5'
              }`
            }
          >
            <MessageSquare size={15} />
            {t('navbar.chat')}
          </NavLink>

          <NavLink
            to="/faq"
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'text-white bg-white/10'
                  : 'text-white/50 hover:text-white hover:bg-white/5'
              }`
            }
          >
            <HelpCircle size={15} />
            {t('navbar.faq')}
          </NavLink>
        </nav>

        <div className="h-4 w-px bg-white/10" />
        <LanguageSwitcher />
      </div>
    </header>
  )
}
