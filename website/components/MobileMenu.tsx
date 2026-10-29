"use client"
import { useRef } from 'react'
const links = [['/features', 'Features'], ['/how-it-works', 'How it works'], ['/privacy', 'Privacy'], ['/download', 'Download · Coming Soon']] as const
export function MobileMenu() {
  const ref = useRef<HTMLDetailsElement>(null)
  return <details ref={ref} className="mobile-nav" onKeyDown={event => {
    if (event.key === 'Escape' && ref.current?.open) {
      ref.current.open = false
      ref.current.querySelector('summary')?.focus()
    }
  }}><summary>Menu <span aria-hidden="true">＋</span></summary><nav aria-label="Mobile navigation">{links.map(([href, label]) => <a key={href} href={href}>{label}</a>)}</nav></details>
}
