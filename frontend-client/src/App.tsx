import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Navbar } from './components/layout/Navbar'
import { ChatPage } from './pages/ChatPage'
import { FaqPage } from './pages/FaqPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0d0d0f] text-white font-sans antialiased flex flex-col">
        <Navbar />
        <main className="flex-1 flex flex-col overflow-hidden">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/faq" element={<FaqPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
