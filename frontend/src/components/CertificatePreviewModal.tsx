import { useEffect, useRef, useState } from 'react'
import {
  certificateErrorMessage,
  certificateFilename,
  fetchCertificatePdf,
} from '../utils/certificateDocument'

type PreviewCertificate = {
  id: number
  certificate_number: string
  document_type: string
}

type Props = {
  certificate: PreviewCertificate
  onClose: () => void
}

function CertificatePreviewModal({ certificate, onClose }: Props) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    previouslyFocused.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()
    return () => {
      document.body.style.overflow = originalOverflow
      previouslyFocused.current?.focus()
    }
  }, [])

  useEffect(() => {
    let active = true
    let objectUrl = ''

    fetchCertificatePdf(certificate.id)
      .then((blob) => {
        if (!active) return
        const pdfBlob = new Blob([blob], { type: 'application/pdf' })
        objectUrl = URL.createObjectURL(pdfBlob)
        setUrl(objectUrl)
      })
      .catch((requestError) => {
        if (active) {
          setError(
            certificateErrorMessage(
              requestError,
              'Unable to load this document. Please try again.',
            ),
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [certificate.id, attempt])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const label =
    certificate.document_type === 'certificate' ? 'Certificate' : 'Marksheet'
  const filename = certificateFilename(certificate.certificate_number)
  const titleId = 'certificate-preview-title'

  return (
    <div
      className="modal-backdrop certificate-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="modal-card certificate-viewer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
      >
        <div className="modal-header certificate-viewer-head">
          <div>
            <span className="eyebrow">DOCUMENT PREVIEW</span>
            <h2 id={titleId}>
              {label} · {certificate.certificate_number}
            </h2>
          </div>
          <button
            className="close-button"
            onClick={onClose}
            type="button"
            aria-label="Close preview"
            ref={closeButtonRef}
          >
            ×
          </button>
        </div>

        {error && (
          <div className="inline-error certificate-preview-error" role="alert">
            {error}
          </div>
        )}

        <div className="certificate-preview-body" aria-busy={loading}>
          {loading ? (
            <div className="table-state">Preparing your document…</div>
          ) : url ? (
            <iframe
              className="certificate-preview-frame"
              src={url}
              title={`${label} ${certificate.certificate_number}`}
            />
          ) : (
            <div className="table-state">
              <strong>Preview unavailable</strong>
              <p>
                Retry the preview, or download the PDF and open it in your
                viewer.
              </p>
            </div>
          )}
        </div>

        {url && (
          <p className="certificate-preview-hint">
            If the preview stays blank, use “Open in new tab” or download the
            PDF.
          </p>
        )}

        <div className="modal-actions certificate-viewer-actions">
          {error && (
            <button
              className="secondary-button"
              onClick={() => {
                setLoading(true)
                setError('')
                setUrl('')
                setAttempt((value) => value + 1)
              }}
              type="button"
            >
              Retry preview
            </button>
          )}
          {url && (
            <button
              className="secondary-button"
              onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}
              type="button"
            >
              Open in new tab
            </button>
          )}
          {url && (
            <a className="primary-button" href={url} download={filename}>
              Download PDF
            </a>
          )}
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

export default CertificatePreviewModal
