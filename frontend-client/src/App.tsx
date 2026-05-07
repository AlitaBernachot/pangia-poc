// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import { Navbar } from './components/layout/Navbar'
import { Sidebar } from './components/layout/Sidebar'
import { ChatPage } from './pages/ChatPage'
import { FaqPage } from './pages/FaqPage'
import { useTheme } from './hooks/useTheme'

export default function App() {
  const [sessionTitle, setSessionTitle] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sidebarExpanded, setSidebarExpanded] = useState(false)
  const { theme, toggleTheme } = useTheme()

  const bgClass = theme === 'dark'
    ? 'bg-gradient-to-br from-[#07111f] via-[#0c1b30] to-[#111f38]'
    : 'bg-gradient-to-br from-[#f0f7ff] to-[#dbeafe]'

  return (
    <BrowserRouter>
      <div className={`min-h-screen ${bgClass} text-white font-sans antialiased flex`}>
        <Sidebar expanded={sidebarExpanded} onToggle={() => setSidebarExpanded(v => !v)} theme={theme} hasActiveSession={!!sessionId} />
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <Navbar sessionTitle={sessionTitle} sessionId={sessionId} theme={theme} onToggleTheme={toggleTheme} />
          <main className="flex-1 flex flex-col overflow-hidden">
            <Routes>
              <Route path="/" element={<ChatPage onSessionTitle={setSessionTitle} onSessionId={setSessionId} />} />
              <Route path="/faq" element={<FaqPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
