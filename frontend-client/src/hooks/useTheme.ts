// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useState, useEffect } from 'react'

export type Theme = 'dark' | 'light'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem('pangia-theme') as Theme) ?? 'dark'
  })

  useEffect(() => {
    const html = document.documentElement
    html.classList.remove('dark', 'light')
    html.classList.add(theme)
    localStorage.setItem('pangia-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  return { theme, toggleTheme }
}
