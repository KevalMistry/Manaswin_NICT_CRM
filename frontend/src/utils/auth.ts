import type { User } from '../types'

export const USER_UPDATED_EVENT = 'nict:user-updated'

export function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem('current_user')
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function storeUser(user: User): void {
  localStorage.setItem('current_user', JSON.stringify(user))
  window.dispatchEvent(new Event(USER_UPDATED_EVENT))
}

export function hasModuleAccess(user: User | null, moduleKey: string): boolean {
  if (!user) return false
  if (user.role_name === 'Super Admin') return true
  return (user.allowed_modules ?? []).includes(moduleKey)
}
