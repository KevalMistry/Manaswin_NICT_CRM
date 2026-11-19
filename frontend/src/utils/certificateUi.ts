/** Shared formatting helpers for certificate and marksheet UI. */

export function formatCertificateDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function formatCertificateResult(
  grade: string | null | undefined,
  percentage: number | null | undefined,
): string {
  const parts: string[] = []
  if (grade) parts.push(grade)
  if (percentage !== null && percentage !== undefined && Number.isFinite(Number(percentage))) {
    parts.push(`${Number(percentage)}%`)
  }
  return parts.length ? parts.join(' · ') : '—'
}

export function countLabel(
  count: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${count} ${count === 1 ? singular : plural}`
}

export function certificateVerificationUrl(code: string): string {
  return `${window.location.origin}/verify-certificate?code=${encodeURIComponent(code.trim())}`
}

export function certificateVerificationPath(code: string): string {
  return `/verify-certificate?code=${encodeURIComponent(code.trim())}`
}

export async function copyText(value: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    if (!document.execCommand('copy')) {
      throw new Error('The browser blocked the copy command.')
    }
  } finally {
    textarea.remove()
  }
}
