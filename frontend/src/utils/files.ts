import api from '../services/api'

/**
 * Map a stored upload path to the authenticated media endpoint.
 *
 * Database rows keep the historical `/uploads/...` value, but that public
 * static mount no longer exists. Protected files are served from
 * `/api/media/...` after an authorization check.
 */
export function mediaRequestPath(path: string): string {
  const normalised = path.startsWith('/') ? path : `/${path}`
  if (normalised.startsWith('/uploads/')) {
    return `/api/media/${normalised.slice('/uploads/'.length)}`
  }
  return normalised
}

/**
 * Download an API-protected file and open it in a new tab.
 *
 * Uploaded documents are served only to authenticated callers, so a bare
 * anchor cannot be used. The blob URL is revoked after the new tab has had
 * time to load it.
 */
export async function openAuthenticatedFile(path: string): Promise<void> {
  const response = await api.get(mediaRequestPath(path), { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(response.data)
  window.open(objectUrl, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
}
