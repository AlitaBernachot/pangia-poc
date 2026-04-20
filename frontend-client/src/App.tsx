// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import { Navbar } from './components/layout/Navbar'
import { Sidebar } from './components/layout/Sidebar'
import { ChatPage } from './pages/ChatPage'
import { FaqPage } from './pages/FaqPage'

export default function App() {
  const [sessionTitle, setSessionTitle] = useState('')

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0d0d0f] text-white font-sans antialiased flex">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Navbar sessionTitle={sessionTitle} />
          <main className="flex-1 flex flex-col overflow-hidden">
            <Routes>
              <Route path="/" element={<ChatPage onSessionTitle={setSessionTitle} />} />
              <Route path="/faq" element={<FaqPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
