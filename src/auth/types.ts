export interface AuthUser { id: string; email: string; email_verified: boolean; display_name: string; avatar_url: string | null }
export interface AuthState { phase: 'checking' | 'signed_out' | 'signing_in' | 'signed_in' | 'error'; user: AuthUser | null; message: string | null }
export interface AuthApi { me(): Promise<AuthUser | null>; start(): Promise<void>; poll(): Promise<AuthUser | null>; cancel(): Promise<void>; logout(): Promise<void> }
export function parseUser(value: unknown): AuthUser | null {
  if (value === null) return null
  if (typeof value !== 'object') throw new Error('Invalid account response')
  const user = value as Record<string, unknown>
  if (typeof user.id !== 'string' || typeof user.email !== 'string' || typeof user.display_name !== 'string' || typeof user.email_verified !== 'boolean' || !(user.avatar_url === null || typeof user.avatar_url === 'string')) throw new Error('Invalid account response')
  return { id: user.id, email: user.email, display_name: user.display_name, email_verified: user.email_verified, avatar_url: user.avatar_url }
}
