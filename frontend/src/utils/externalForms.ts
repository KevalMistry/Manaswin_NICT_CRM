export type ExternalFormProvider = 'google' | 'microsoft' | null

const PROVIDER_LABELS: Record<string, string> = {
  google: 'Google Forms',
  microsoft: 'Microsoft Forms',
}

export function externalFormLabel(provider: ExternalFormProvider): string {
  return provider ? PROVIDER_LABELS[provider] ?? 'External form' : 'External form'
}

export function validateExternalFormUrl(
  value: string,
  provider?: ExternalFormProvider,
): string | null {
  const url = value.trim()
  if (!url) return 'Enter the published form link.'
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return 'Enter a full https link to the published form.'
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    return 'Use a full https link to the published form.'
  }
  const host = parsed.hostname.toLowerCase()
  const detected = host === 'docs.google.com'
    ? 'google'
    : host === 'forms.office.com'
      ? 'microsoft'
      : null
  if (!detected) {
    return 'Only published Google Forms and Microsoft Forms links are supported.'
  }
  if (provider && provider !== detected) {
    return 'The form link does not match the selected provider.'
  }
  if (detected === 'google' && !parsed.pathname.toLowerCase().includes('/forms/')) {
    return 'Enter a published Google Forms link.'
  }
  if (detected === 'microsoft' && !parsed.pathname.replace(/^\/+|\/+$/g, '')) {
    return 'Enter a published Microsoft Forms link.'
  }
  return null
}
