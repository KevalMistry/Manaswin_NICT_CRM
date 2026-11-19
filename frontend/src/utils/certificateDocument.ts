import axios from 'axios'
import api from '../services/api'
import { apiErrorMessage } from './apiErrors'

/** Fetch an issued certificate or marksheet as a PDF blob. */
export async function fetchCertificatePdf(certificateId: number): Promise<Blob> {
  try {
    const { data } = await api.get<Blob>(
      `/api/certificates/${certificateId}/document`,
      { responseType: 'blob' },
    )
    return data
  } catch (error) {
    // A blob response type also turns FastAPI error JSON into a Blob, so pull
    // the useful message back out before the caller shows a generic error.
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      let detail: string | null = null
      try {
        const payload = JSON.parse(await error.response.data.text()) as {
          detail?: unknown
        }
        if (typeof payload.detail === 'string') detail = payload.detail
      } catch {
        // Not a JSON error body; fall through to the original Axios error.
      }
      if (detail) {
        throw new Error(detail, { cause: error })
      }
    }
    throw error
  }
}

export function certificateFilename(certificateNumber: string): string {
  return `${certificateNumber}.pdf`
}

export function certificateErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return apiErrorMessage(error, fallback)
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1500)
}

export async function downloadCertificateDocument(
  certificateId: number,
  certificateNumber: string,
): Promise<void> {
  const blob = await fetchCertificatePdf(certificateId)
  saveBlob(blob, certificateFilename(certificateNumber))
}
