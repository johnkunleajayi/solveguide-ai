import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'
const storageKey = 'solveguide-theme'

function readTheme(): Theme {
  try {
    const value = localStorage.getItem(storageKey)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch { /* Fall back to system when storage is unavailable. */ }
  return 'system'
}

function applyTheme(theme: Theme) {
  const resolved = theme === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme
  document.documentElement.dataset.theme = resolved
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#0B0E0D' : '#F6F9F7')
}

// Resolve the existing preference before React renders to avoid a light/dark flash.
export function initializeTheme() { applyTheme(readTheme()) }

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => applyTheme(theme)
    apply()
    media.addEventListener('change', apply)
    try { localStorage.setItem(storageKey, theme) } catch { /* Session-only fallback. */ }
    return () => media.removeEventListener('change', apply)
  }, [theme])
  return { theme, setTheme }
}
