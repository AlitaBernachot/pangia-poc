import { Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function Sidebar() {
  const { t } = useTranslation()

  return (
    <aside className="w-14 shrink-0 flex flex-col items-center justify-end pb-4 border-r border-white/8 bg-[#0d0d0f]">
      {/* Cog icon — future settings menu */}
      <button
        type="button"
        title={t('sidebar.settings')}
        className="mb-3 size-9 flex items-center justify-center rounded-lg text-white/40 hover:text-white/80 hover:bg-white/6 transition-colors cursor-pointer"
      >
        <Settings size={18} />
      </button>

      {/* User avatar */}
      <div
        title={t('sidebar.user')}
        className="size-9 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-sm font-semibold text-cyan-300 select-none"
      >
        U
      </div>
    </aside>
  )
}
