import axios from 'axios'

/** Extract a human-readable message from a FastAPI/axios error response. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)))
        .filter(Boolean)
      if (messages.length) return messages.join(', ')
    }
    if (!error.response) return 'The API is unreachable. Check that the backend is running.'
  }
  return fallback
}
