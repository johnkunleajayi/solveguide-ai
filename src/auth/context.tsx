import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { authApi } from './client'
import { createAuthController } from './controller'
import type { AuthState } from './types'
type Controller = ReturnType<typeof createAuthController>
const AuthContext = createContext<{ state: AuthState; controller: Controller } | null>(null)
export function AuthProvider({ children }: { children: ReactNode }) {
  const [controller] = useState(() => createAuthController(authApi))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => {
    void controller.check()
    const refresh = () => { if (document.visibilityState === 'visible') void controller.check() }
    window.addEventListener('focus', refresh)
    const interval = setInterval(refresh, 60_000)
    return () => { window.removeEventListener('focus', refresh); clearInterval(interval); controller.dispose() }
  }, [controller])
  return <AuthContext.Provider value={{ state, controller }}>{children}</AuthContext.Provider>
}
export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw Error('Authentication boundary is missing')
  return auth
}
