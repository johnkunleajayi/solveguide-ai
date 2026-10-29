"use client"
import { useEffect, useRef } from 'react'
import { themeKey, type Theme } from '@/lib/theme'
export function ThemeControl() {
  const select = useRef<HTMLSelectElement>(null)
  useEffect(() => {
    let preference: Theme = 'system'
    try { const saved = localStorage.getItem(themeKey); if (saved === 'light' || saved === 'dark') preference = saved } catch { /* Storage is optional. */ }
    if (select.current) select.current.value = preference
    const media = matchMedia('(prefers-color-scheme: dark)')
    const apply = () => { document.documentElement.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference }
    const change = () => { preference = select.current?.value as Theme; try { localStorage.setItem(themeKey, preference) } catch { /* In-memory preference still works. */ } apply() }
    const element = select.current
    element?.addEventListener('change', change)
    media.addEventListener('change', apply)
    return () => { element?.removeEventListener('change', change); media.removeEventListener('change', apply) }
  }, [])
  return <label className="theme-control"><span>Theme</span><select ref={select} defaultValue="system" aria-label="Website theme"><option value="system">System</option><option value="dark">Dark</option><option value="light">Light</option></select></label>
}
