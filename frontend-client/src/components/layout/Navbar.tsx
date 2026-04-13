import { NavLink } from 'react-router-dom'
import { MessageSquare, HelpCircle } from 'lucide-react'

export function Navbar() {
  return (
    <header className="flex items-center justify-between px-5 h-14 border-b border-white/8 bg-[#0d0d0f]/80 backdrop-blur-sm sticky top-0 z-50">
      <NavLink to="/" className="flex items-center gap-2 text-white font-semibold text-lg">
        <span className="text-2xl">🌍</span>
        <span>PanGIA</span>
      </NavLink>

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
          Chat
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
          FAQ
        </NavLink>
      </nav>
    </header>
  )
}
