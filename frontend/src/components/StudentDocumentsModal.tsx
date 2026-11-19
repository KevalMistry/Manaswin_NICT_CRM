import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { openAuthenticatedFile } from '../utils/files'
import AuthImage from './AuthImage'

export type StudentSummary = {
  id: number
  full_name: string
  student_code: string
  photo_url: string | null
}

type StudentDocument = {
  id: number
  student_id: number
  document_type: string
  title: string
  file_name: string
  file_url: string
  content_type: string | null
  file_size: number
  uploaded_at: string
}

const DOCUMENT_TYPES = [
  { value: 'aadhaar', label: 'Aadhaar Card' },
  { value: 'pan', label: 'PAN Card' },
  { value: 'photo', label: 'Photograph' },
  { value: 'marksheet', label: 'Marksheet' },
  { value: 'certificate', label: 'Certificate' },
  { value: 'id_proof', label: 'ID Proof' },
  { value: 'other', label: 'Other' },
]

function fileSizeLabel(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function StudentDocumentsModal({
  student,
  onClose,
  onStudentUpdated,
}: {
  student: StudentSummary
  onClose: () => void
  onStudentUpdated: (photoUrl: string) => void
}) {
  const [documents, setDocuments] = useState<StudentDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [photoPreview, setPhotoPreview] = useState(student.photo_url ?? '')
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [documentType, setDocumentType] = useState('aadhaar')
  const [title, setTitle] = useState('')
  const [documentFile, setDocumentFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get<StudentDocument[]>(
        `/api/students/${student.id}/documents`,
      )
      setDocuments(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load student documents.'))
    } finally {
      setLoading(false)
    }
  }, [student.id])

  useEffect(() => {
    let cancelled = false
    api
      .get<StudentDocument[]>(`/api/students/${student.id}/documents`)
      .then(({ data }) => {
        if (!cancelled) setDocuments(data)
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(apiErrorMessage(requestError, 'Unable to load student documents.'))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [student.id])

  async function uploadPhoto() {
    if (!photoFile) return
    setUploadingPhoto(true)
    setError('')
    setMessage('')
    const formData = new FormData()
    formData.append('file', photoFile)
    try {
      const { data } = await api.post<{ photo_url: string | null }>(
        `/api/students/${student.id}/photo`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const url = data.photo_url ?? ''
      setPhotoPreview(url)
      setPhotoFile(null)
      onStudentUpdated(url)
      setMessage('Student photo updated.')
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to upload the student photo.'))
    } finally {
      setUploadingPhoto(false)
    }
  }

  async function openDocument(document: StudentDocument) {
    setError('')
    try {
      await openAuthenticatedFile(document.file_url)
    } catch {
      setError('Unable to open this document.')
    }
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!documentFile) {
      setError('Choose a file to upload.')
      return
    }
    setUploading(true)
    setError('')
    setMessage('')
    const formData = new FormData()
    formData.append('file', documentFile)
    formData.append('document_type', documentType)
    formData.append('title', title)
    try {
      await api.post(`/api/students/${student.id}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setDocumentFile(null)
      setTitle('')
      setMessage('Document uploaded.')
      await loadDocuments()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to upload this document.'))
    } finally {
      setUploading(false)
    }
  }

  async function deleteDocument(document: StudentDocument) {
    if (!window.confirm(`Delete ${document.title}?`)) return
    setError('')
    setMessage('')
    try {
      await api.delete(`/api/students/${student.id}/documents/${document.id}`)
      setMessage('Document deleted.')
      await loadDocuments()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to delete this document.'))
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="modal-card student-docs-modal" role="dialog" aria-modal="true">
        <div className="modal-header">
          <div>
            <span className="eyebrow">STUDENT PROFILE &amp; DOCUMENTS</span>
            <h2>{student.full_name}</h2>
            <p className="muted">{student.student_code}</p>
          </div>
          <button className="close-button" onClick={onClose} type="button">
            ×
          </button>
        </div>

        {error && <div className="inline-error">{error}</div>}
        {message && <div className="success-message">{message}</div>}

        <section className="student-docs-photo">
          <div className="student-photo-frame">
            {photoPreview ? (
              <AuthImage path={photoPreview} alt={`${student.full_name} photo`} />
            ) : (
              <span>{student.full_name.slice(0, 1).toUpperCase()}</span>
            )}
          </div>
          <div className="student-photo-actions">
            <strong>Student photo</strong>
            <small>JPG, PNG or WebP up to 3 MB.</small>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => setPhotoFile(event.target.files?.[0] ?? null)}
            />
            {photoFile && (
              <button
                className="secondary-button btn-sm"
                disabled={uploadingPhoto}
                onClick={() => void uploadPhoto()}
                type="button"
              >
                {uploadingPhoto ? 'Uploading…' : 'Upload photo'}
              </button>
            )}
          </div>
        </section>

        <form className="student-doc-upload" onSubmit={uploadDocument}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="doc-type">Document type</label>
              <select
                id="doc-type"
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value)}
              >
                {DOCUMENT_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="doc-title">Title (optional)</label>
              <input
                id="doc-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="e.g. Aadhaar front side"
              />
            </div>
            <div className="field full-field">
              <label htmlFor="doc-file">File</label>
              <input
                id="doc-file"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.zip"
                onChange={(event) => setDocumentFile(event.target.files?.[0] ?? null)}
              />
              <small className="field-hint">
                PDF, image, Word, Excel or ZIP up to 10 MB.
              </small>
            </div>
          </div>
          <div className="modal-actions">
            <button className="primary-button" disabled={uploading} type="submit">
              {uploading ? 'Uploading…' : 'Upload document'}
            </button>
          </div>
        </form>

        <section className="student-doc-list">
          <div className="section-title">
            <div>
              <span className="eyebrow">UPLOADED FILES</span>
              <h2>Documents</h2>
            </div>
            <span className="result-count">{documents.length} files</span>
          </div>
          {loading ? (
            <div className="table-state">Loading documents…</div>
          ) : documents.length === 0 ? (
            <div className="table-state">No documents uploaded yet.</div>
          ) : (
            <div className="table-scroll">
              <table className="student-doc-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Type</th>
                    <th>Size</th>
                    <th>Uploaded</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {documents.map((document) => (
                    <tr key={document.id}>
                      <td>
                        <strong>{document.title}</strong>
                        <small>{document.file_name}</small>
                      </td>
                      <td>{DOCUMENT_TYPES.find((type) => type.value === document.document_type)?.label ?? document.document_type}</td>
                      <td>{fileSizeLabel(document.file_size)}</td>
                      <td>{new Date(document.uploaded_at).toLocaleDateString()}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="row-link"
                            onClick={() => void openDocument(document)}
                            type="button"
                          >
                            Open
                          </button>
                          <button
                            className="danger-action"
                            onClick={() => void deleteDocument(document)}
                            type="button"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export default StudentDocumentsModal
