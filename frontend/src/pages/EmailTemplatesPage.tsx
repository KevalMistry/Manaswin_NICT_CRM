import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import api from '../services/api'

type EmailTemplate = {
  template_key: string
  name: string
  branch_id: number | null
  branch_name: string | null
  subject_template: string
  html_body: string
  text_body: string | null
  is_active: boolean
  source: string
  editable: boolean
  can_reset: boolean
  variables: string[]
  required_variables: string[]
  updated_at: string | null
  updated_by_name: string | null
}

type Branch = { id: number; name: string; is_active: boolean }

type Preview = { subject: string; html: string; text: string; warnings: string[] }

function EmailTemplatesPage() {
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [branches, setBranches] = useState<Branch[]>([])
  const [scope, setScope] = useState('global')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)

  const [form, setForm] = useState({
    subject_template: '',
    html_body: '',
    text_body: '',
    is_active: true,
  })

  const subjectRef = useRef<HTMLInputElement | null>(null)
  const htmlRef = useRef<HTMLTextAreaElement | null>(null)
  const [focusField, setFocusField] = useState<'subject' | 'html' | 'text'>('html')

  const isSuperAdmin = (() => {
    try {
      return JSON.parse(localStorage.getItem('current_user') ?? '{}')?.role_name === 'Super Admin'
    } catch {
      return false
    }
  })()

  const loadBranches = useCallback(async () => {
    if (!isSuperAdmin) return
    try {
      const { data } = await api.get<Branch[]>('/api/branches', { params: { limit: 100 } })
      setBranches(data)
    } catch {
      setBranches([])
    }
  }, [isSuperAdmin])

  const loadTemplates = useCallback(async (scopeValue: string) => {
    setLoading(true)
    setError('')
    try {
      const params = scopeValue === 'global' ? {} : { branch_id: Number(scopeValue) }
      const { data } = await api.get<EmailTemplate[]>('/api/email-templates', { params })
      setTemplates(data)
      if (!selectedKey && data.length) setSelectedKey(data[0].template_key)
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Failed to load email templates.')
      }
    } finally {
      setLoading(false)
    }
  }, [selectedKey])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadBranches()
      void loadTemplates('global')
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadBranches, loadTemplates])

  useEffect(() => {
    const current = templates.find((t) => t.template_key === selectedKey)
    if (!current) return
    const timer = window.setTimeout(() => {
      setForm({
        subject_template: current.subject_template,
        html_body: current.html_body,
        text_body: current.text_body ?? '',
        is_active: current.is_active,
      })
      setPreview(null)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [selectedKey, templates])

  async function changeScope(next: string) {
    if (next === scope) return
    setScope(next)
    setSelectedKey(null)
    await loadTemplates(next)
    setSuccess('')
  }

  function insertToken(token: string, wrap = false) {
    const field = focusField === 'subject' ? 'subject_template' : focusField === 'html' ? 'html_body' : 'text_body'
    const ref = focusField === 'subject' ? subjectRef.current : focusField === 'html' ? htmlRef.current : null
    const value = form[field]
    const snippet = wrap ? `{{${token}}}` : `{{${token}}}`
    if (ref && ref.selectionStart !== undefined) {
      const start = ref.selectionStart ?? value.length
      const end = ref.selectionEnd ?? value.length
      const next = value.slice(0, start) + snippet + value.slice(end)
      setForm((f) => ({ ...f, [field]: next }))
      requestAnimationFrame(() => {
        try {
          const el = ref
          el.selectionStart = start + snippet.length
          el.selectionEnd = start + snippet.length
          ref.focus()
        } catch {
          /* ignore */
        }
      })
    } else {
      setForm((f) => ({ ...f, [field]: value + snippet }))
    }
  }

  function wrapSelection(prefix: string, suffix: string) {
    const field = focusField === 'subject' ? 'subject_template' : focusField === 'html' ? 'html_body' : 'text_body'
    const ref = focusField === 'subject' ? subjectRef.current : focusField === 'html' ? htmlRef.current : null
    const value = form[field]
    if (ref && ref.selectionStart !== undefined) {
      const start = ref.selectionStart ?? value.length
      const end = ref.selectionEnd ?? value.length
      const selected = value.slice(start, end) || 'text'
      const next = value.slice(0, start) + prefix + selected + suffix + value.slice(end)
      setForm((f) => ({ ...f, [field]: next }))
      requestAnimationFrame(() => {
        try {
          const el = ref
          el.selectionStart = start + prefix.length
          el.selectionEnd = start + prefix.length + selected.length
          ref.focus()
        } catch {
          /* ignore */
        }
      })
    } else {
      setForm((f) => ({ ...f, [field]: value + prefix + 'text' + suffix }))
    }
  }
  async function save() {
    if (!selectedKey) return
    setError('')
    setSuccess('')
    try {
      const params = scope === 'global' ? {} : { branch_id: Number(scope) }
      const { data } = await api.put<EmailTemplate>(
        `/api/email-templates/${selectedKey}`,
        {
          branch_id: scope === 'global' ? null : Number(scope),
          subject_template: form.subject_template,
          html_body: form.html_body,
          text_body: form.text_body || null,
          is_active: form.is_active,
        },
        { params },
      )
      setTemplates((prev) => prev.map((t) => (t.template_key === selectedKey ? data : t)))
      setSuccess(`Saved "${data.name}" (${data.source} scope).`)
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Failed to save template.')
      }
    } finally {
      setSaving(false)
    }
  }

  async function resetOverride() {
    if (!selectedKey) return
    if (!window.confirm('Remove this branch override and inherit the global template?')) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const params = scope === 'global' ? {} : { branch_id: Number(scope) }
      const { data } = await api.delete<EmailTemplate>(
        `/api/email-templates/${selectedKey}`,
        { params },
      )
      setTemplates((prev) => prev.map((t) => (t.template_key === selectedKey ? data : t)))
      setSuccess(`Reset "${data.name}" to the inherited template.`)
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Failed to reset template.')
      }
    } finally {
      setSaving(false)
    }
  }

  async function handlePreview() {
    if (!selectedKey) return
    setPreviewing(true)
    setError('')
    try {
      const { data } = await api.post<Preview>(
        `/api/email-templates/${selectedKey}/preview`,
        {
          branch_id: scope === 'global' ? null : Number(scope),
          subject_template: form.subject_template,
          html_body: form.html_body,
          text_body: form.text_body || null,
        },
      )
      setPreview(data)
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setError(err.response.data.detail)
      } else {
        setError('Preview failed.')
      }
    } finally {
      setPreviewing(false)
    }
  }

  const current = templates.find((t) => t.template_key === selectedKey) ?? null

  if (loading && !templates.length) {
    return <div className="page-content"><div className="table-state">Loading email templates…</div></div>
  }

  return (
    <>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">COMMUNICATIONS</span>
          <h1>Email templates</h1>
          <p>
            Customize the subject, HTML body and plain-text body of every outbound email. Use
            <code> {'{{variable}}'} </code> placeholders; the available variables are listed per
            template. Branch overrides win over the global default for that branch only.
          </p>
        </div>
        <div className="heading-actions">
          {isSuperAdmin ? (
            <select value={scope} onChange={(e) => void changeScope(e.target.value)} aria-label="Template scope">
              <option value="global">Global default</option>
              {branches.map((b) => (
                <option key={b.id} value={String(b.id)}>{b.name}</option>
              ))}
            </select>
          ) : (
            <span className="role-scope-badge">Branch scope</span>
          )}
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      <section className="data-panel">
        <div className="section-title">
          <div>
            <span className="eyebrow">TEMPLATES</span>
            <h2>Outbound email formats</h2>
          </div>
          <span className="result-count">{templates.length} templates</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 0 }}>
          <div style={{ borderRight: '1px solid var(--line)', padding: 12 }}>
            {templates.map((t) => (
              <button
                key={t.template_key}
                type="button"
                onClick={() => setSelectedKey(t.template_key)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '10px 12px',
                  border: 0,
                  background: selectedKey === t.template_key ? '#eef3fb' : 'transparent',
                  borderRadius: 6,
                  cursor: 'pointer',
                  marginBottom: 4,
                }}
              >
                <strong style={{ display: 'block', fontSize: 13 }}>{t.name}</strong>
                <small style={{ color: '#8b98aa', fontSize: 10 }}>
                  {t.source} · {t.is_active ? 'active' : 'disabled'}
                </small>
              </button>
            ))}
          </div>

          <div style={{ padding: 20 }}>
            {current?.editable && (
              <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: '#8b98aa' }}>Insert into {focusField}:</span>
                <button type="button" className="secondary-button btn-sm" onClick={() => wrapSelection('<strong>', '</strong>')} disabled={saving}>Bold</button>
                <button type="button" className="secondary-button btn-sm" onClick={() => wrapSelection('<em>', '</em>')} disabled={saving}>Italic</button>
                <button type="button" className="secondary-button btn-sm" onClick={() => wrapSelection('<p>', '</p>')} disabled={saving}>Paragraph</button>
                <button type="button" className="secondary-button btn-sm" onClick={() => wrapSelection('<a href="https://">', '</a>')} disabled={saving}>Link</button>
                <button type="button" className="secondary-button btn-sm" onClick={() => wrapSelection('<br />', '')} disabled={saving}>Line break</button>
              </div>
            )}
            {current ? (
              <>
                <div className="field">
                  <label>Subject template</label>
                  <input
                    ref={subjectRef}
                    value={form.subject_template}
                    onFocus={() => setFocusField('subject')}
                    onChange={(e) => setForm((f) => ({ ...f, subject_template: e.target.value }))}
                    disabled={!current.editable || saving}
                  />
                </div>
                <div className="field">
                  <label>HTML body</label>
                  <textarea
                    ref={htmlRef}
                    rows={12}
                    value={form.html_body}
                    onFocus={() => setFocusField('html')}
                    onChange={(e) => setForm((f) => ({ ...f, html_body: e.target.value }))}
                    disabled={!current.editable || saving}
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  />
                </div>
                <div className="field">
                  <label>Plain-text body (optional)</label>
                  <textarea
                    rows={6}
                    value={form.text_body}
                    onFocus={() => setFocusField('text')}
                    onChange={(e) => setForm((f) => ({ ...f, text_body: e.target.value }))}
                    disabled={!current.editable || saving}
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  />
                </div>
                <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    id="template-active"
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                    disabled={!current.editable || saving}
                  />
                  <label htmlFor="template-active" style={{ margin: 0 }}>Active</label>
                </div>

                <details style={{ marginBottom: 12 }}>
                  <summary style={{ cursor: 'pointer', fontSize: 12, color: '#3978e8' }}>
                    Need help writing HTML? Copy an AI prompt
                  </summary>
                  <div style={{ marginTop: 8 }}>
                    <textarea
                      readOnly
                      rows={8}
                      value={`You are an email designer for an educational institute. Write a responsive, mobile-friendly HTML email template.

Template name: ${current.name}
Purpose: ${current.name}

Use ONLY these placeholders (do not change spelling): ${current.variables.map((v) => '{{' + v + '}}').join(', ')}.
Required placeholders that must appear: ${current.required_variables.map((v) => '{{' + v + '}}').join(', ') || 'none'}.

Design rules:
- Max width 620px, centered, inline CSS only.
- Brand color #3978e8 for headings/buttons, neutral grays for text.
- Include a greeting, a details table, a call-to-action button, and a footer.
- Keep it accessible (alt text, readable font sizes >= 14px).
- Return ONLY the HTML body (no markdown fences) and a plain-text version after it.

Start with: <!doctype html>`}
                      style={{ width: '100%', fontFamily: 'monospace', fontSize: 11, padding: 8, border: '1px solid var(--line)', borderRadius: 6 }}
                    />
                    <button
                      type="button"
                      className="secondary-button btn-sm"
                      style={{ marginTop: 6 }}
                      onClick={() => {
                        const prompt = `You are an email designer for an educational institute. Write a responsive, mobile-friendly HTML email template.\n\nTemplate name: ${current.name}\n\nUse ONLY these placeholders (do not change spelling): ${current.variables.map((v) => '{{' + v + '}}').join(', ')}.\nRequired placeholders that must appear: ${current.required_variables.map((v) => '{{' + v + '}}').join(', ') || 'none'}.\n\nDesign rules:\n- Max width 620px, centered, inline CSS only.\n- Brand color #3978e8 for headings/buttons, neutral grays for text.\n- Include a greeting, a details table, a call-to-action button, and a footer.\n- Keep it accessible (alt text, readable font sizes >= 14px).\n- Return ONLY the HTML body (no markdown fences) and a plain-text version after it.\n\nStart with: <!doctype html>`
                        navigator.clipboard?.writeText(prompt).then(() => setSuccess('Prompt copied. Paste it into ChatGPT.'))
                      }}
                    >
                      Copy prompt
                    </button>
                  </div>
                </details>

                <div style={{ marginBottom: 12 }}>
                  <strong style={{ fontSize: 12 }}>Available variables:</strong>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                    {current.variables.map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => insertToken(v)}
                        disabled={!current.editable || saving}
                        style={{
                          fontSize: 11,
                          background: '#f1f4f8',
                          padding: '2px 6px',
                          borderRadius: 4,
                          border: 0,
                          cursor: current.editable ? 'pointer' : 'default',
                          fontFamily: 'monospace',
                        }}
                      >
                        {'{{' + v + '}}'}
                      </button>
                    ))}
                  </div>
                  {current.required_variables.length > 0 && (
                    <small style={{ display: 'block', marginTop: 6, color: '#8b98aa' }}>
                      Required: {current.required_variables.map((v) => '{{' + v + '}}').join(', ')}
                    </small>
                  )}
                </div>

                <div className="modal-actions">
                  <button className="secondary-button" type="button" onClick={() => void handlePreview()} disabled={previewing || saving}>
                    {previewing ? 'Previewing…' : 'Preview'}
                  </button>
                  {current.can_reset && (
                    <button className="secondary-button" type="button" onClick={() => void resetOverride()} disabled={saving}>
                      Reset override
                    </button>
                  )}
                  {current?.editable && (
                    <button className="primary-button" type="button" onClick={() => void save()} disabled={saving}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                  )}
                </div>

                {preview && (
                  <div style={{ marginTop: 20, border: '1px solid var(--line)', borderRadius: 8, padding: 12 }}>
                    <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>Preview</h3>
                    <p style={{ margin: '0 0 6px', fontSize: 12 }}><strong>Subject:</strong> {preview.subject}</p>
                    {preview.warnings.length > 0 && (
                      <div className="inline-error" style={{ marginBottom: 8 }}>
                        {preview.warnings.join(' ')}
                      </div>
                    )}
                    <div style={{ background: '#f7f9fc', padding: 10, borderRadius: 6, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                      {preview.text}
                    </div>
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ cursor: 'pointer', fontSize: 12 }}>HTML</summary>
                      <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, background: '#f7f9fc', padding: 10, borderRadius: 6, overflow: 'auto' }}>
                        {preview.html}
                      </pre>
                    </details>
                  </div>
                )}
              </>
            ) : (
              <div className="table-state">Select a template to edit.</div>
            )}
          </div>
        </div>
      </section>
    </>
  )
}

export default EmailTemplatesPage
