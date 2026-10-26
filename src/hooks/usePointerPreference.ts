import { useEffect, useState } from 'react'

const key = 'solveguide-pointer-light'
function readPreference() {
  try { return localStorage.getItem(key) !== 'off' } catch { return true }
}

export function usePointerPreference() {
  const [pointerLight, setPointerLight] = useState(readPreference)
  useEffect(() => {
    try { localStorage.setItem(key, pointerLight ? 'on' : 'off') } catch { /* Session-only fallback. */ }
  }, [pointerLight])
  return { pointerLight, setPointerLight }
}
