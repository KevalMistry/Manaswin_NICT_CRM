import { useEffect, useState } from 'react'
import api from '../services/api'
import { mediaRequestPath } from '../utils/files'

type AuthImageProps = {
  path: string | null | undefined
  alt?: string
  className?: string
}

function isDirectSource(value: string) {
  return /^(https?:|blob:|data:)/i.test(value)
}

/**
 * Render an uploaded image that is protected by the API.
 *
 * Uploaded photos are no longer served by a public static mount, so a plain
 * `<img src>` would get a 401. The image is fetched with the bearer token and
 * exposed through a short-lived object URL instead.
 */
function AuthImage({ path, alt = '', className }: AuthImageProps) {
  const directSource = path && isDirectSource(path) ? path : null
  const [loaded, setLoaded] = useState<{ path: string; src: string } | null>(null)

  useEffect(() => {
    if (!path || isDirectSource(path)) return
    let cancelled = false
    let objectUrl: string | null = null
    api
      .get(mediaRequestPath(path), { responseType: 'blob' })
      .then((response) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(response.data)
        setLoaded({ path, src: objectUrl })
      })
      .catch(() => {
        if (!cancelled) setLoaded(null)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  const src = directSource ?? (loaded && loaded.path === path ? loaded.src : null)
  if (!path || !src) return null
  return <img alt={alt} className={className} src={src} />
}

export default AuthImage
