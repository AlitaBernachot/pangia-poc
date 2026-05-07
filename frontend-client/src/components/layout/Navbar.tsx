// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { Sun, Moon } from 'lucide-react'
import { LanguageSwitcher } from './LanguageSwitcher'
import type { Theme } from '../../hooks/useTheme'

interface Props {
  sessionTitle?: string
  sessionId?: string | null
  theme?: Theme
  onToggleTheme?: () => void
}

export function Navbar({ sessionTitle, sessionId, theme, onToggleTheme }: Props) {
  return (
    <header className="flex items-center px-5 h-14 sticky top-0 z-50">
      {/* Session title + id tag */}
      {sessionTitle ? (
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span
            id="session-title"
            className="text-xs font-semibold uppercase tracking-widest truncate max-w-100 text-white/70"
          >
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
      ) : (
        <div className="flex-1" />
      )}

      <div className="shrink-0 flex items-center gap-2">
        <LanguageSwitcher />

        {/* Dark / light theme toggle */}
        {onToggleTheme && (
          <button
            type="button"
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="size-8 flex items-center justify-center rounded-lg text-white/50 hover:text-white/90 hover:bg-white/8 transition-colors cursor-pointer"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        )}
      </div>
    </header>
  )
}
