// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { NavLink } from 'react-router-dom'
import { MessageSquare, HelpCircle, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Theme } from '../../hooks/useTheme'

interface Props {
  expanded: boolean
  onToggle: () => void
  theme?: Theme
  hasActiveSession?: boolean
}

/** Sidebar nav item — icon only when collapsed, icon + label when expanded. */
function SidebarNavItem({
  to,
  icon,
  label,
  expanded,
  end,
  dot,
}: {
  to: string
  icon: React.ReactNode
  label: string
  expanded: boolean
  end?: boolean
  dot?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={!expanded ? label : undefined}
      className={({ isActive }) =>
        `relative flex items-center gap-3 rounded-lg transition-colors cursor-pointer select-none
         ${expanded ? 'px-3 py-2 w-full' : 'size-9 justify-center'}
         ${isActive
           ? 'text-white bg-white/10'
           : 'text-white/45 hover:text-white/80 hover:bg-white/6'
         }`
      }
    >
      <span className="relative shrink-0">
        {icon}
        {dot && (
          <span className="absolute -top-1 -right-1 size-2 rounded-full bg-blue-400 ring-1 ring-blue-300/40" />
        )}
      </span>
      {expanded && <span className="text-sm font-medium truncate">{label}</span>}
    </NavLink>
  )
}

export function Sidebar({ expanded, onToggle, theme, hasActiveSession }: Props) {
  const { t } = useTranslation()

  return (
    <aside
      className={`shrink-0 flex flex-col border-r border-white/8 overflow-hidden transition-[width] duration-200 ease-in-out ${theme === 'light' ? 'bg-white/30 backdrop-blur-sm' : 'bg-black/20 backdrop-blur-sm'}`}
      style={{ width: expanded ? 200 : 56 }}
    >
      {/* ── Logo / toggle ──────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={onToggle}
        title={expanded ? 'Réduire' : 'PangIA'}
        className="flex items-center gap-3 px-3 h-14 transition-colors cursor-pointer shrink-0 w-full text-left"
      >
        <img src="/logo.png" alt="PangIA" className="size-7 rounded shrink-0" />
        {expanded && (
          <span className="text-white font-semibold text-base truncate">PangIA</span>
        )}
      </button>

      {/* ── Navigation ─────────────────────────────────────────────────── */}
      <nav className={`flex flex-col gap-1 pt-3 ${expanded ? 'px-2' : 'items-center px-0'}`}>
        <SidebarNavItem
          to="/"
          end
          icon={<MessageSquare size={18} />}
          label={t('navbar.chat')}
          expanded={expanded}
          dot={hasActiveSession}
        />
        <SidebarNavItem
          to="/faq"
          icon={<HelpCircle size={18} />}
          label={t('navbar.faq')}
          expanded={expanded}
        />
      </nav>

      <div className="flex-1" />

      {/* ── Bottom actions ─────────────────────────────────────────────── */}
      <div className={`flex flex-col gap-2 pb-4 ${expanded ? 'px-2' : 'items-center px-0'}`}>

        {/* Settings */}
        <button
          type="button"
          title={!expanded ? t('sidebar.settings') : undefined}
          className={`flex items-center gap-3 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/6 transition-colors cursor-pointer
            ${expanded ? 'px-3 py-2 w-full' : 'size-9 justify-center'}`}
        >
          <Settings size={18} className="shrink-0" />
          {expanded && <span className="text-sm font-medium truncate">{t('sidebar.settings')}</span>}
        </button>

        {/* User */}
        <div
          title={!expanded ? t('sidebar.user') : undefined}
          className={`flex items-center gap-3 rounded-lg cursor-default select-none
            ${expanded ? 'px-3 py-2 w-full' : 'size-9 justify-center'}`}
        >
          <div className="size-7 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-xs font-semibold text-cyan-300 shrink-0">
            U
          </div>
          {expanded && <span className="text-sm text-white/60 truncate">{t('sidebar.user')}</span>}
        </div>
      </div>
    </aside>
  )
}
