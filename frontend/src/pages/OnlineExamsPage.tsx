import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser } from '../utils/auth'
import {
  externalFormLabel,
  validateExternalFormUrl,
  type ExternalFormProvider,
} from '../utils/externalForms'

type ExamCourse = {
  id: number
  name: string
  code: string
  duration_months: number
  exam_count: number
  bank_count: number
  enrollment_count: number
}

type Batch = {
  id: number
  name: string
  code: string
  course_id: number
  is_active: boolean
}

type BankQuestion = {
  id: number
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_option: string
  marks: string
  difficulty: string
  explanation: string | null
  position: number
}

type Bank = {
  id: number
  course_id: number
  title: string
  description: string | null
  external_form_url: string | null
  external_form_provider: ExternalFormProvider
  created_at: string
  questions: BankQuestion[]
}

type ExamQuestion = {
  id: number
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_option: string
  marks: string
  explanation: string | null
  position: number
}

type Attempt = {
  id: number
  enrollment_id: number
  student_name: string
  student_code: string
  attempt_number: number
  status: string
  score: string
  total_marks: string
  percentage: number
  passed: boolean
  auto_submitted: boolean
  started_at: string
  submitted_at: string | null
}

type ExamSummary = {
  id: number
  course_id: number
  course_name: string
  batch_id: number | null
  title: string
  description: string | null
  external_form_url: string | null
  external_form_provider: ExternalFormProvider
  start_at: string | null
  end_at: string | null
  duration_minutes: number
  pass_percentage: number
  max_attempts: number
  shuffle_questions: boolean
  negative_marking: boolean
  is_published: boolean
  results_published: boolean
  question_count: number
  total_marks: string
  attempt_count: number
}

type ExamDetail = ExamSummary & {
  instructions: string | null
  created_at: string
  questions: ExamQuestion[]
  attempts: Attempt[]
}

type ExamForm = {
  title: string
  batch_id: string
  description: string
  instructions: string
  delivery_mode: 'crm' | 'external'
  source_bank_id: string
  external_form_provider: ExternalFormProvider
  external_form_url: string
  start_at: string
  end_at: string
  duration_minutes: string
  pass_percentage: string
  max_attempts: string
  shuffle_questions: boolean
  negative_marking: boolean
}

type QuestionForm = {
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_option: string
  marks: string
  difficulty: string
  explanation: string
}

const pad = (value: number) => String(value).padStart(2, '0')

function toLocalInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

function fromLocalInput(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function emptyExamForm(): ExamForm {
  const start = new Date()
  const end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000)
  return {
    title: '',
    batch_id: '',
    description: '',
    instructions: 'Answer every question. The exam submits automatically when the timer ends.',
    delivery_mode: 'crm',
    source_bank_id: '',
    external_form_provider: null,
    external_form_url: '',
    start_at: toLocalInput(start.toISOString()),
    end_at: toLocalInput(end.toISOString()),
    duration_minutes: '60',
    pass_percentage: '40',
    max_attempts: '1',
    shuffle_questions: false,
    negative_marking: false,
  }
}

const emptyQuestion: QuestionForm = {
  question_text: '',
  option_a: '',
  option_b: '',
  option_c: '',
  option_d: '',
  correct_option: 'A',
  marks: '1',
  difficulty: 'medium',
  explanation: '',
}

function OnlineExamsPage() {
  const [courses, setCourses] = useState<ExamCourse[]>([])
  const [courseId, setCourseId] = useState('')
  const [batches, setBatches] = useState<Batch[]>([])
  const [exams, setExams] = useState<ExamSummary[]>([])
  const [banks, setBanks] = useState<Bank[]>([])
  const [selectedExam, setSelectedExam] = useState<ExamDetail | null>(null)
  const [selectedBankId, setSelectedBankId] = useState<number | null>(null)
  const selectedBankIdRef = useRef<number | null>(null)
  const [tab, setTab] = useState<'exams' | 'banks'>('exams')
  const [showExamForm, setShowExamForm] = useState(false)
  const [showBankForm, setShowBankForm] = useState(false)
  const [showExamQuestionForm, setShowExamQuestionForm] = useState(false)
  const [showBankQuestionForm, setShowBankQuestionForm] = useState(false)
  const [examForm, setExamForm] = useState<ExamForm>(emptyExamForm)
  const [bankForm, setBankForm] = useState({
    title: '',
    description: '',
    external_form_provider: null as ExternalFormProvider,
    external_form_url: '',
  })
  const [detailLinkForm, setDetailLinkForm] = useState({
    external_form_provider: null as ExternalFormProvider,
    external_form_url: '',
  })
  const [questionForm, setQuestionForm] = useState<QuestionForm>(emptyQuestion)
  const [bankQuestionForm, setBankQuestionForm] = useState<QuestionForm>(emptyQuestion)
  const [selectedBankQuestionIds, setSelectedBankQuestionIds] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const roleName = getStoredUser()?.role_name ?? ''
  const canManage = ['Super Admin', 'Branch Admin', 'Faculty', 'Staff'].includes(roleName)

  const courseBatches = useMemo(
    () => batches.filter((batch) => String(batch.course_id) === courseId),
    [batches, courseId],
  )
  const selectedBank = useMemo(
    () => banks.find((bank) => bank.id === selectedBankId) ?? null,
    [banks, selectedBankId],
  )
  const selectedCourse = useMemo(
    () => courses.find((course) => String(course.id) === courseId) ?? null,
    [courses, courseId],
  )

  function selectBank(bank: Bank | null) {
    selectedBankIdRef.current = bank?.id ?? null
    setSelectedBankId(bank?.id ?? null)
    setBankForm((current) => ({
      ...current,
      external_form_provider: bank?.external_form_provider ?? null,
      external_form_url: bank?.external_form_url ?? '',
    }))
  }

  const loadCourses = useCallback(async () => {
    try {
      const [courseResponse, batchResponse] = await Promise.all([
        api.get<ExamCourse[]>('/api/online-exams/courses'),
        api.get<Batch[]>('/api/batches'),
      ])
      setCourses(courseResponse.data)
      setBatches(batchResponse.data)
      setCourseId((current) => current || (courseResponse.data[0] ? String(courseResponse.data[0].id) : ''))
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load courses for online exams.'))
    }
  }, [])

  const loadExams = useCallback(async () => {
    if (!courseId) return
    try {
      const { data } = await api.get<ExamSummary[]>('/api/online-exams', {
        params: { course_id: Number(courseId), include_unpublished: true },
      })
      setExams(data)
      setLoading(false)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load online exams.'))
      setLoading(false)
    }
  }, [courseId])

  const loadBanks = useCallback(async () => {
    if (!courseId) return
    try {
      const { data } = await api.get<Bank[]>('/api/online-exams/banks', {
        params: { course_id: Number(courseId) },
      })
      setBanks(data)
      const nextId =
        selectedBankIdRef.current &&
        data.some((bank) => bank.id === selectedBankIdRef.current)
          ? selectedBankIdRef.current
          : (data[0]?.id ?? null)
      selectedBankIdRef.current = nextId
      setSelectedBankId(nextId)
      const nextBank = data.find((bank) => bank.id === nextId)
      if (nextBank) {
        setBankForm((current) => ({
          ...current,
          external_form_provider: nextBank.external_form_provider ?? null,
          external_form_url: nextBank.external_form_url ?? '',
        }))
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load question banks.'))
    }
  }, [courseId])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCourses(), 0)
    return () => window.clearTimeout(timer)
  }, [loadCourses])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true)
      setSelectedExam(null)
      selectedBankIdRef.current = null
      setSelectedBankId(null)
      void loadExams()
      void loadBanks()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [courseId, loadExams, loadBanks])

  async function loadExamDetail(examId: number) {
    try {
      const { data } = await api.get<ExamDetail>(`/api/online-exams/${examId}`)
      setSelectedExam(data)
      setDetailLinkForm({
        external_form_provider: data.external_form_provider ?? null,
        external_form_url: data.external_form_url ?? '',
      })
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load this exam.'))
    }
  }

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await action()
      setMessage(success)
      await Promise.all([loadExams(), loadBanks()])
      if (selectedExam) await loadExamDetail(selectedExam.id)
      return true
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'That change could not be saved.'))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function createExam(event: FormEvent) {
    event.preventDefault()
    if (!courseId) return
    setBusy(true)
    setError('')
    setMessage('')
    const isExternal = examForm.delivery_mode === 'external'
    if (isExternal) {
      const linkError = validateExternalFormUrl(
        examForm.external_form_url,
        examForm.external_form_provider,
      )
      if (linkError) {
        setError(linkError)
        setBusy(false)
        return
      }
    }
    try {
      const { data } = await api.post<ExamDetail>('/api/online-exams', {
        course_id: Number(courseId),
        batch_id: examForm.batch_id ? Number(examForm.batch_id) : null,
        source_bank_id: examForm.source_bank_id ? Number(examForm.source_bank_id) : null,
        title: examForm.title,
        description: examForm.description || null,
        instructions: examForm.instructions || null,
        external_form_url: isExternal ? examForm.external_form_url.trim() : null,
        external_form_provider: isExternal ? examForm.external_form_provider : null,
        start_at: fromLocalInput(examForm.start_at),
        end_at: fromLocalInput(examForm.end_at),
        duration_minutes: Number(examForm.duration_minutes || 60),
        pass_percentage: Number(examForm.pass_percentage || 40),
        max_attempts: Number(examForm.max_attempts || 1),
        shuffle_questions: examForm.shuffle_questions,
        negative_marking: examForm.negative_marking,
        bank_question_ids: selectedBankQuestionIds,
      })
      setExamForm(emptyExamForm())
      setSelectedBankQuestionIds([])
      setShowExamForm(false)
      setMessage(
        isExternal
          ? 'External form exam created. Publish it to share the form with students.'
          : 'Exam draft created. Add questions, then publish it.',
      )
      setSelectedExam(data)
      setDetailLinkForm({
        external_form_provider: data.external_form_provider ?? null,
        external_form_url: data.external_form_url ?? '',
      })
      await Promise.all([loadExams(), loadBanks()])
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to create the exam.'))
    } finally {
      setBusy(false)
    }
  }

  async function addExamQuestion(event: FormEvent) {
    event.preventDefault()
    if (!selectedExam) return
    const ok = await run(
      () =>
        api.post(`/api/online-exams/${selectedExam.id}/questions`, {
          ...questionForm,
          marks: Number(questionForm.marks || 1),
        }),
      'Question added to the exam.',
    )
    if (ok) {
      setQuestionForm(emptyQuestion)
      setShowExamQuestionForm(false)
    }
  }

  async function createBank(event: FormEvent) {
    event.preventDefault()
    if (!courseId) return
    setBusy(true)
    setError('')
    setMessage('')
    const linkError = bankForm.external_form_url
      ? validateExternalFormUrl(
          bankForm.external_form_url,
          bankForm.external_form_provider,
        )
      : null
    if (linkError) {
      setError(linkError)
      setBusy(false)
      return
    }
    try {
      const { data } = await api.post<Bank>('/api/online-exams/banks', {
        course_id: Number(courseId),
        title: bankForm.title,
        description: bankForm.description || null,
        external_form_url: bankForm.external_form_url.trim() || null,
        external_form_provider: bankForm.external_form_url.trim()
          ? bankForm.external_form_provider
          : null,
      })
      setBankForm({
        title: '',
        description: '',
        external_form_provider: null,
        external_form_url: '',
      })
      setShowBankForm(false)
      selectBank(data)
      setMessage('Question bank created.')
      await loadBanks()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to create the question bank.'))
    } finally {
      setBusy(false)
    }
  }

  async function addBankQuestion(event: FormEvent) {
    event.preventDefault()
    if (!selectedBank) return
    const ok = await run(
      () =>
        api.post(`/api/online-exams/banks/${selectedBank.id}/questions`, {
          ...bankQuestionForm,
          marks: Number(bankQuestionForm.marks || 1),
        }),
      'Question added to the bank.',
    )
    if (ok) {
      setBankQuestionForm(emptyQuestion)
      setShowBankQuestionForm(false)
    }
  }

  async function deleteExam(exam: ExamSummary) {
    if (!window.confirm(`Delete “${exam.title}”? All attempts will be removed.`)) return
    const ok = await run(
      () => api.delete(`/api/online-exams/${exam.id}`),
      'Exam deleted.',
    )
    if (ok && selectedExam?.id === exam.id) setSelectedExam(null)
  }

  async function publishExam(exam: ExamSummary, publish: boolean) {
    const ok = await run(
      () => api.post(`/api/online-exams/${exam.id}/${publish ? 'publish' : 'unpublish'}`),
      publish ? 'Exam published to students.' : 'Exam unpublished.',
    )
    if (ok) await loadExamDetail(exam.id)
  }

  async function publishResults(exam: ExamSummary) {
    if (!window.confirm(`Publish results for “${exam.title}”?`)) return
    const ok = await run(
      () => api.post(`/api/online-exams/${exam.id}/publish-results`),
      'Results published to students.',
    )
    if (ok) await loadExamDetail(exam.id)
  }

  async function saveExamLink(event: FormEvent) {
    event.preventDefault()
    if (!selectedExam) return
    setError('')
    const linkError = detailLinkForm.external_form_url
      ? validateExternalFormUrl(
          detailLinkForm.external_form_url,
          detailLinkForm.external_form_provider,
        )
      : null
    if (linkError) {
      setError(linkError)
      return
    }
    const ok = await run(
      () =>
        api.patch(`/api/online-exams/${selectedExam.id}`, {
          external_form_url: detailLinkForm.external_form_url.trim() || null,
          external_form_provider: detailLinkForm.external_form_url.trim()
            ? detailLinkForm.external_form_provider
            : null,
        }),
      'External form link updated.',
    )
    if (ok) await loadExamDetail(selectedExam.id)
  }

  async function saveBankLink(event: FormEvent) {
    event.preventDefault()
    if (!selectedBank) return
    const linkError = bankForm.external_form_url
      ? validateExternalFormUrl(
          bankForm.external_form_url,
          bankForm.external_form_provider,
        )
      : null
    if (linkError) {
      setError(linkError)
      return
    }
    const ok = await run(
      () =>
        api.patch(`/api/online-exams/banks/${selectedBank.id}`, {
          external_form_url: bankForm.external_form_url.trim() || null,
          external_form_provider: bankForm.external_form_url.trim()
            ? bankForm.external_form_provider
            : null,
        }),
      'Question bank form link updated.',
    )
    if (ok) setSelectedBankId(selectedBank.id)
  }

  async function deleteExamQuestion(questionId: number) {
    if (!selectedExam) return
    if (!window.confirm('Remove this question from the exam?')) return
    await run(
      () => api.delete(`/api/online-exams/${selectedExam.id}/questions/${questionId}`),
      'Question removed.',
    )
  }

  async function deleteBankQuestion(questionId: number) {
    if (!selectedBank) return
    if (!window.confirm('Delete this question from the bank?')) return
    await run(
      () => api.delete(`/api/online-exams/banks/${selectedBank.id}/questions/${questionId}`),
      'Question deleted.',
    )
  }

  async function deleteBank(bank: Bank) {
    if (!window.confirm(`Delete the question bank “${bank.title}”?`)) return
    const ok = await run(
      () => api.delete(`/api/online-exams/banks/${bank.id}`),
      'Question bank deleted.',
    )
    if (ok) selectBank(null)
  }

  function toggleBankQuestion(questionId: number) {
    setSelectedBankQuestionIds((current) =>
      current.includes(questionId)
        ? current.filter((id) => id !== questionId)
        : [...current, questionId],
    )
  }

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">EXAMINATIONS</span>
          <h1>Online Exams</h1>
          <p>
            Build question banks, schedule timed online exams, auto-grade MCQ
            answers and control when results become visible to students.
          </p>
        </div>
        <div className="heading-actions">
          {selectedCourse && (
            <span className="result-count">
              {selectedCourse.exam_count} exams · {selectedCourse.bank_count} banks ·{' '}
              {selectedCourse.enrollment_count} learners
            </span>
          )}
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="module-toolbar">
        <div className="toolbar-controls">
          <div className="field">
            <label htmlFor="exam-course">Course</label>
            <select
              id="exam-course"
              value={courseId}
              onChange={(event) => setCourseId(event.target.value)}
            >
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name} ({course.code})
                </option>
              ))}
            </select>
          </div>
        </div>
        <span className="result-count">
          Timed attempts auto-submit when the timer ends.
        </span>
      </section>

      <nav className="module-tabs" aria-label="Online exam sections">
        <button
          className={tab === 'exams' ? 'active-tab' : ''}
          onClick={() => setTab('exams')}
          type="button"
        >
          Exams <span>{exams.length}</span>
        </button>
        <button
          className={tab === 'banks' ? 'active-tab' : ''}
          onClick={() => setTab('banks')}
          type="button"
        >
          Question banks <span>{banks.length}</span>
        </button>
      </nav>

      {loading && !exams.length && (
        <div className="table-state">Loading online exams…</div>
      )}

      {!courses.length && !loading && (
        <div className="data-panel table-state">
          <strong>No courses available</strong>
          <p>Create a course first, then schedule an online exam.</p>
        </div>
      )}

      {tab === 'exams' && courseId && (
        <>
          {canManage && (
            <section className="module-toolbar">
              <div className="toolbar-controls">
                <button
                  className="primary-button"
                  onClick={() => setShowExamForm((open) => !open)}
                  type="button"
                >
                  + New exam
                </button>
                <button
                  className="secondary-button"
                  onClick={() => {
                    setTab('banks')
                    setShowBankForm(true)
                  }}
                  type="button"
                >
                  + Question bank
                </button>
              </div>
            </section>
          )}

          {showExamForm && (
            <section className="data-panel settings-card lms-form-panel">
              <div className="section-title">
                <div>
                  <span className="eyebrow">NEW EXAM</span>
                  <h2>Schedule an online exam</h2>
                </div>
              </div>
              <form className="form-grid" onSubmit={(event) => void createExam(event)}>
                <div className="field">
                  <label htmlFor="exam-title">Title</label>
                  <input
                    id="exam-title"
                    required
                    value={examForm.title}
                    onChange={(event) =>
                      setExamForm({ ...examForm, title: event.target.value })
                    }
                    placeholder="e.g. Python Certification Exam"
                  />
                </div>
                <div className="field">
                  <label htmlFor="exam-batch">Batch (optional)</label>
                  <select
                    id="exam-batch"
                    value={examForm.batch_id}
                    onChange={(event) =>
                      setExamForm({ ...examForm, batch_id: event.target.value })
                    }
                  >
                    <option value="">All batches in this course</option>
                    {courseBatches.map((batch) => (
                      <option key={batch.id} value={batch.id}>
                        {batch.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field full-field">
                  <label htmlFor="exam-delivery">Exam delivery</label>
                  <select
                    id="exam-delivery"
                    value={examForm.delivery_mode}
                    onChange={(event) =>
                      setExamForm({
                        ...examForm,
                        delivery_mode: event.target.value as 'crm' | 'external',
                      })
                    }
                  >
                    <option value="crm">Questions in the CRM (timed and auto-graded)</option>
                    <option value="external">Google/Microsoft Forms published link</option>
                  </select>
                  <small className="muted">
                    External form exams open the form you published. Responses and grades stay
                    in Google/Microsoft Forms.
                  </small>
                </div>
                {examForm.delivery_mode === 'external' && (
                  <>
                    <div className="field">
                      <label htmlFor="exam-form-provider">Form provider</label>
                      <select
                        id="exam-form-provider"
                        value={examForm.external_form_provider ?? ''}
                        onChange={(event) =>
                          setExamForm({
                            ...examForm,
                            external_form_provider:
                              (event.target.value || null) as ExternalFormProvider,
                          })
                        }
                      >
                        <option value="">Auto-detect from link</option>
                        <option value="google">Google Forms</option>
                        <option value="microsoft">Microsoft Forms</option>
                      </select>
                    </div>
                    <div className="field full-field">
                      <label htmlFor="exam-form-url">Published form link</label>
                      <input
                        id="exam-form-url"
                        type="url"
                        required
                        value={examForm.external_form_url}
                        onChange={(event) =>
                          setExamForm({ ...examForm, external_form_url: event.target.value })
                        }
                        placeholder="https://docs.google.com/forms/d/e/…/viewform"
                      />
                    </div>
                    {banks.some((bank) => bank.external_form_url) && (
                      <div className="field full-field">
                        <label htmlFor="exam-source-bank">Or reuse a bank’s form link</label>
                        <select
                          id="exam-source-bank"
                          value={examForm.source_bank_id}
                          onChange={(event) => {
                            const bank = banks.find(
                              (item) => String(item.id) === event.target.value,
                            )
                            setExamForm({
                              ...examForm,
                              source_bank_id: event.target.value,
                              external_form_url: bank?.external_form_url ?? '',
                              external_form_provider:
                                bank?.external_form_provider ?? null,
                            })
                          }}
                        >
                          <option value="">Choose a bank</option>
                          {banks
                            .filter((bank) => bank.external_form_url)
                            .map((bank) => (
                              <option key={bank.id} value={bank.id}>
                                {bank.title} · {externalFormLabel(bank.external_form_provider)}
                              </option>
                            ))}
                        </select>
                      </div>
                    )}
                  </>
                )}
                <div className="field">
                  <label htmlFor="exam-start">Opens at</label>
                  <input
                    id="exam-start"
                    type="datetime-local"
                    value={examForm.start_at}
                    onChange={(event) =>
                      setExamForm({ ...examForm, start_at: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="exam-end">Closes at</label>
                  <input
                    id="exam-end"
                    type="datetime-local"
                    value={examForm.end_at}
                    onChange={(event) =>
                      setExamForm({ ...examForm, end_at: event.target.value })
                    }
                  />
                </div>
                {examForm.delivery_mode === 'crm' && (
                  <>
                <div className="field">
                  <label htmlFor="exam-duration">Duration (minutes)</label>
                  <input
                    id="exam-duration"
                    type="number"
                    min="1"
                    max="600"
                    value={examForm.duration_minutes}
                    onChange={(event) =>
                      setExamForm({ ...examForm, duration_minutes: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="exam-pass">Pass percentage</label>
                  <input
                    id="exam-pass"
                    type="number"
                    min="0"
                    max="100"
                    value={examForm.pass_percentage}
                    onChange={(event) =>
                      setExamForm({ ...examForm, pass_percentage: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="exam-attempts">Maximum attempts</label>
                  <input
                    id="exam-attempts"
                    type="number"
                    min="1"
                    max="10"
                    value={examForm.max_attempts}
                    onChange={(event) =>
                      setExamForm({ ...examForm, max_attempts: event.target.value })
                    }
                  />
                </div>
                <div className="field exam-toggle-field">
                  <label>
                    <input
                      checked={examForm.shuffle_questions}
                      onChange={(event) =>
                        setExamForm({ ...examForm, shuffle_questions: event.target.checked })
                      }
                      type="checkbox"
                    />
                    Shuffle question order
                  </label>
                  <label>
                    <input
                      checked={examForm.negative_marking}
                      onChange={(event) =>
                        setExamForm({ ...examForm, negative_marking: event.target.checked })
                      }
                      type="checkbox"
                    />
                    Negative marking (−25% per wrong answer)
                  </label>
                </div>
                  </>
                )}
                <div className="field full-field">
                  <label htmlFor="exam-description">Description</label>
                  <textarea
                    id="exam-description"
                    rows={2}
                    value={examForm.description}
                    onChange={(event) =>
                      setExamForm({ ...examForm, description: event.target.value })
                    }
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="exam-instructions">Instructions</label>
                  <textarea
                    id="exam-instructions"
                    rows={2}
                    value={examForm.instructions}
                    onChange={(event) =>
                      setExamForm({ ...examForm, instructions: event.target.value })
                    }
                  />
                </div>
                {examForm.delivery_mode === 'crm' && banks.length > 0 && (
                  <div className="field full-field">
                    <label>Pull questions from question banks</label>
                    <div className="exam-bank-picker">
                      {banks.map((bank) => (
                        <div className="exam-bank-group" key={bank.id}>
                          <strong>{bank.title}</strong>
                          {bank.questions.map((question) => (
                            <label key={question.id}>
                              <input
                                checked={selectedBankQuestionIds.includes(question.id)}
                                onChange={() => toggleBankQuestion(question.id)}
                                type="checkbox"
                              />
                              <span>{question.question_text}</span>
                            </label>
                          ))}
                          {!bank.questions.length && <small>No questions in this bank.</small>}
                        </div>
                      ))}
                    </div>
                    <small className="muted">
                      You can create an empty draft and add questions individually.
                    </small>
                  </div>
                )}
                <div className="full-field modal-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setShowExamForm(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button className="primary-button" disabled={busy} type="submit">
                    {busy ? 'Saving…' : 'Create draft exam'}
                  </button>
                </div>
              </form>
            </section>
          )}

          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">SCHEDULE</span>
                <h2>{selectedCourse?.name ?? 'Course'} online exams</h2>
              </div>
              <span className="result-count">{exams.length} exams</span>
            </div>
            <div className="lms-module-list">
              {exams.map((exam) => (
                <article className="lms-module" key={exam.id}>
                  <header>
                    <div>
                      <strong>{exam.title}</strong>
                      <p>
                        {formatDateTime(exam.start_at)} → {formatDateTime(exam.end_at)} ·{' '}
                        {exam.external_form_url
                          ? `${externalFormLabel(exam.external_form_provider)} exam`
                          : `${exam.duration_minutes} min · ${exam.question_count} questions · ${exam.total_marks} marks`}{' '}
                        · {exam.attempt_count} attempts
                      </p>
                    </div>
                    {canManage && (
                      <div className="row-actions">
                        <button onClick={() => void loadExamDetail(exam.id)} type="button">
                          Manage
                        </button>
                        {exam.is_published ? (
                          <button
                            onClick={() => void publishExam(exam, false)}
                            type="button"
                          >
                            Unpublish
                          </button>
                        ) : (
                          <button
                            onClick={() => void publishExam(exam, true)}
                            type="button"
                          >
                            Publish
                          </button>
                        )}
                        <button
                          disabled={exam.results_published}
                          onClick={() => void publishResults(exam)}
                          type="button"
                        >
                          {exam.results_published ? 'Results live' : 'Publish results'}
                        </button>
                        <button
                          className="danger-action"
                          onClick={() => void deleteExam(exam)}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </header>
                  <div className="exam-chip-row">
                    <span className={exam.is_published ? 'status-pill active-status' : 'status-pill'}>
                      <i />
                      {exam.is_published ? 'Published' : 'Draft'}
                    </span>
                    <span className="exam-chip">
                      Pass {exam.pass_percentage}% · {exam.max_attempts} attempt(s)
                    </span>
                    {exam.external_form_url && (
                      <>
                        <span className="exam-chip">
                          {externalFormLabel(exam.external_form_provider)}
                        </span>
                        <a
                          className="external-form-link"
                          href={exam.external_form_url}
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          Open form ↗
                        </a>
                      </>
                    )}
                    {exam.shuffle_questions && <span className="exam-chip">Shuffled</span>}
                    {exam.negative_marking && (
                      <span className="exam-chip">Negative marking</span>
                    )}
                    {exam.results_published && (
                      <span className="exam-chip">Results published</span>
                    )}
                  </div>
                </article>
              ))}
              {!exams.length && !loading && (
                <div className="table-state">
                  <strong>No online exams yet</strong>
                  <p>Create a draft exam, add questions and publish it when ready.</p>
                </div>
              )}
            </div>
          </section>

          {selectedExam && (
            <section className="data-panel lms-section-gap">
              <div className="section-title">
                <div>
                  <span className="eyebrow">EXAM DETAIL</span>
                  <h2>{selectedExam.title}</h2>
                </div>
                <span className="result-count">
                  {selectedExam.external_form_url
                    ? externalFormLabel(selectedExam.external_form_provider)
                    : `${selectedExam.question_count} questions · ${selectedExam.total_marks} marks`}
                </span>
              </div>
              {selectedExam.instructions && (
                <p className="lms-instructions">{selectedExam.instructions}</p>
              )}
              {selectedExam.external_form_url && (
                <div className="external-form-panel">
                  <div>
                    <strong>
                      {externalFormLabel(selectedExam.external_form_provider)} exam form
                    </strong>
                    <p>
                      Students see an “Open exam form” button during the exam window.
                      Responses and grades stay in the form.
                    </p>
                  </div>
                  <a
                    className="external-form-link"
                    href={selectedExam.external_form_url}
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Open form ↗
                  </a>
                </div>
              )}
              {canManage && selectedExam.external_form_url && (
                <form
                  className="form-grid lms-inline-form"
                  onSubmit={(event) => void saveExamLink(event)}
                >
                  <div className="field">
                    <label htmlFor="detail-form-provider">Form provider</label>
                    <select
                      id="detail-form-provider"
                      value={detailLinkForm.external_form_provider ?? ''}
                      onChange={(event) =>
                        setDetailLinkForm({
                          ...detailLinkForm,
                          external_form_provider:
                            (event.target.value || null) as ExternalFormProvider,
                        })
                      }
                    >
                      <option value="">Auto-detect from link</option>
                      <option value="google">Google Forms</option>
                      <option value="microsoft">Microsoft Forms</option>
                    </select>
                  </div>
                  <div className="field full-field">
                    <label htmlFor="detail-form-url">Published form link</label>
                    <input
                      id="detail-form-url"
                      type="url"
                      value={detailLinkForm.external_form_url}
                      onChange={(event) =>
                        setDetailLinkForm({
                          ...detailLinkForm,
                          external_form_url: event.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="full-field modal-actions">
                    <button className="primary-button" disabled={busy} type="submit">
                      {busy ? 'Saving…' : 'Update form link'}
                    </button>
                  </div>
                </form>
              )}
              {canManage && !selectedExam.is_published && !selectedExam.external_form_url && (
                <div className="toolbar-controls">
                  <button
                    className="secondary-button"
                    onClick={() => setShowExamQuestionForm((open) => !open)}
                    type="button"
                  >
                    + Add question
                  </button>
                </div>
              )}
              {showExamQuestionForm &&
                !selectedExam.is_published &&
                !selectedExam.external_form_url && (
                <form
                  className="form-grid lms-inline-form"
                  onSubmit={(event) => void addExamQuestion(event)}
                >
                  <QuestionFields
                    form={questionForm}
                    onChange={setQuestionForm}
                    showDifficulty={false}
                  />
                  <div className="full-field modal-actions">
                    <button
                      className="secondary-button"
                      onClick={() => setShowExamQuestionForm(false)}
                      type="button"
                    >
                      Cancel
                    </button>
                    <button className="primary-button" disabled={busy} type="submit">
                      {busy ? 'Saving…' : 'Add question'}
                    </button>
                  </div>
                </form>
              )}
              {!selectedExam.external_form_url && (
                <ol className="lms-question-list">
                {selectedExam.questions.map((question) => (
                  <li key={question.id}>
                    <div>
                      <span>{question.question_text}</span>
                      <small>
                        A) {question.option_a} · B) {question.option_b} · C){' '}
                        {question.option_c} · D) {question.option_d}
                      </small>
                      <small className="muted-block">
                        Correct: {question.correct_option} · {question.marks} marks
                      </small>
                    </div>
                    {canManage && !selectedExam.is_published && (
                      <button
                        className="row-link danger-action"
                        onClick={() => void deleteExamQuestion(question.id)}
                        type="button"
                      >
                        Remove
                      </button>
                    )}
                  </li>
                ))}
                {!selectedExam.questions.length && (
                  <li className="muted">No questions yet. Add at least one before publishing.</li>
                )}
                </ol>
              )}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Attempt</th>
                      <th>Status</th>
                      <th>Score</th>
                      <th>Percentage</th>
                      <th>Result</th>
                      <th>Submitted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedExam.attempts.map((attempt) => (
                      <tr key={attempt.id}>
                        <td>
                          <strong>{attempt.student_name}</strong>
                          <small className="muted-block">{attempt.student_code}</small>
                        </td>
                        <td>#{attempt.attempt_number}</td>
                        <td>{attempt.status}</td>
                        <td>
                          {attempt.score} / {attempt.total_marks}
                        </td>
                        <td>{attempt.percentage}%</td>
                        <td>{attempt.passed ? 'Passed' : 'Not passed'}</td>
                        <td>
                          {formatDateTime(attempt.submitted_at)}
                          {attempt.auto_submitted ? ' · auto' : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!selectedExam.attempts.length && (
                  <div className="table-state">No attempts yet.</div>
                )}
              </div>
            </section>
          )}
        </>
      )}

      {tab === 'banks' && courseId && (
        <>
          {canManage && (
            <section className="module-toolbar">
              <div className="toolbar-controls">
                <button
                  className="primary-button"
                  onClick={() => setShowBankForm((open) => !open)}
                  type="button"
                >
                  + New question bank
                </button>
              </div>
            </section>
          )}
          {showBankForm && (
            <section className="data-panel settings-card lms-form-panel">
              <div className="section-title">
                <div>
                  <span className="eyebrow">NEW BANK</span>
                  <h2>Create a question bank</h2>
                </div>
              </div>
              <form className="form-grid" onSubmit={(event) => void createBank(event)}>
                <div className="field">
                  <label htmlFor="bank-title">Title</label>
                  <input
                    id="bank-title"
                    required
                    value={bankForm.title}
                    onChange={(event) =>
                      setBankForm({ ...bankForm, title: event.target.value })
                    }
                    placeholder="e.g. Python Certification Bank"
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="bank-description">Description</label>
                  <textarea
                    id="bank-description"
                    rows={2}
                    value={bankForm.description}
                    onChange={(event) =>
                      setBankForm({ ...bankForm, description: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="bank-form-provider">Form provider (optional)</label>
                  <select
                    id="bank-form-provider"
                    value={bankForm.external_form_provider ?? ''}
                    onChange={(event) =>
                      setBankForm({
                        ...bankForm,
                        external_form_provider:
                          (event.target.value || null) as ExternalFormProvider,
                      })
                    }
                  >
                    <option value="">Auto-detect from link</option>
                    <option value="google">Google Forms</option>
                    <option value="microsoft">Microsoft Forms</option>
                  </select>
                </div>
                <div className="field full-field">
                  <label htmlFor="bank-form-url">Published form link (optional)</label>
                  <input
                    id="bank-form-url"
                    type="url"
                    value={bankForm.external_form_url}
                    onChange={(event) =>
                      setBankForm({ ...bankForm, external_form_url: event.target.value })
                    }
                    placeholder="Paste a published Google or Microsoft Forms link"
                  />
                  <small className="muted">
                    Banks with a form link can be reused when creating external form exams.
                  </small>
                </div>
                <div className="full-field modal-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setShowBankForm(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button className="primary-button" disabled={busy} type="submit">
                    {busy ? 'Saving…' : 'Create bank'}
                  </button>
                </div>
              </form>
            </section>
          )}

          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">QUESTION BANKS</span>
                <h2>{selectedCourse?.name ?? 'Course'} banks</h2>
              </div>
              <span className="result-count">{banks.length} banks</span>
            </div>
            <div className="lms-module-list">
              {banks.map((bank) => (
                <article className="lms-module" key={bank.id}>
                  <header>
                    <div>
                      <strong>{bank.title}</strong>
                      <p>
                        {bank.description ?? 'No description'} · {bank.questions.length}{' '}
                        questions
                        {bank.external_form_url &&
                          ` · ${externalFormLabel(bank.external_form_provider)} link`}
                      </p>
                    </div>
                    <div className="row-actions">
                      <button onClick={() => selectBank(bank)} type="button">
                        Open
                      </button>
                      {canManage && (
                        <button
                          className="danger-action"
                          onClick={() => void deleteBank(bank)}
                          type="button"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </header>
                </article>
              ))}
              {!banks.length && !loading && (
                <div className="table-state">
                  <strong>No question banks yet</strong>
                  <p>Create a bank to reuse questions across timed exams.</p>
                </div>
              )}
            </div>
          </section>

          {selectedBank && (
            <section className="data-panel lms-section-gap">
              <div className="section-title">
                <div>
                  <span className="eyebrow">BANK DETAIL</span>
                  <h2>{selectedBank.title}</h2>
                </div>
                <span className="result-count">{selectedBank.questions.length} questions</span>
              </div>
              {selectedBank.external_form_url && (
                <div className="external-form-panel">
                  <div>
                    <strong>{externalFormLabel(selectedBank.external_form_provider)} link</strong>
                    <p>Use this link when creating an external form exam.</p>
                  </div>
                  <a
                    className="external-form-link"
                    href={selectedBank.external_form_url}
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Open form ↗
                  </a>
                </div>
              )}
              {canManage && (
                <form
                  className="form-grid lms-inline-form"
                  onSubmit={(event) => void saveBankLink(event)}
                >
                  <div className="field">
                    <label htmlFor="bank-detail-provider">Form provider</label>
                    <select
                      id="bank-detail-provider"
                      value={bankForm.external_form_provider ?? ''}
                      onChange={(event) =>
                        setBankForm({
                          ...bankForm,
                          external_form_provider:
                            (event.target.value || null) as ExternalFormProvider,
                        })
                      }
                    >
                      <option value="">Auto-detect from link</option>
                      <option value="google">Google Forms</option>
                      <option value="microsoft">Microsoft Forms</option>
                    </select>
                  </div>
                  <div className="field full-field">
                    <label htmlFor="bank-detail-url">Published form link</label>
                    <input
                      id="bank-detail-url"
                      type="url"
                      value={bankForm.external_form_url}
                      onChange={(event) =>
                        setBankForm({
                          ...bankForm,
                          external_form_url: event.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="full-field modal-actions">
                    <button className="primary-button" disabled={busy} type="submit">
                      {busy ? 'Saving…' : 'Save form link'}
                    </button>
                  </div>
                </form>
              )}
              {canManage && (
                <div className="toolbar-controls">
                  <button
                    className="secondary-button"
                    onClick={() => setShowBankQuestionForm((open) => !open)}
                    type="button"
                  >
                    + Add question
                  </button>
                </div>
              )}
              {showBankQuestionForm && (
                <form
                  className="form-grid lms-inline-form"
                  onSubmit={(event) => void addBankQuestion(event)}
                >
                  <QuestionFields
                    form={bankQuestionForm}
                    onChange={setBankQuestionForm}
                    showDifficulty
                  />
                  <div className="full-field modal-actions">
                    <button
                      className="secondary-button"
                      onClick={() => setShowBankQuestionForm(false)}
                      type="button"
                    >
                      Cancel
                    </button>
                    <button className="primary-button" disabled={busy} type="submit">
                      {busy ? 'Saving…' : 'Add question'}
                    </button>
                  </div>
                </form>
              )}
              <ol className="lms-question-list">
                {selectedBank.questions.map((question) => (
                  <li key={question.id}>
                    <div>
                      <span>{question.question_text}</span>
                      <small>
                        A) {question.option_a} · B) {question.option_b} · C){' '}
                        {question.option_c} · D) {question.option_d}
                      </small>
                      <small className="muted-block">
                        Correct: {question.correct_option} · {question.marks} marks ·{' '}
                        {question.difficulty}
                      </small>
                    </div>
                    {canManage && (
                      <button
                        className="row-link danger-action"
                        onClick={() => void deleteBankQuestion(question.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    )}
                  </li>
                ))}
                {!selectedBank.questions.length && (
                  <li className="muted">No questions in this bank yet.</li>
                )}
              </ol>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function QuestionFields({
  form,
  onChange,
  showDifficulty,
}: {
  form: QuestionForm
  onChange: (form: QuestionForm) => void
  showDifficulty: boolean
}) {
  return (
    <>
      <div className="field full-field">
        <label>Question</label>
        <textarea
          required
          rows={2}
          value={form.question_text}
          onChange={(event) => onChange({ ...form, question_text: event.target.value })}
        />
      </div>
      {(
        [
          ['option_a', 'Option A'],
          ['option_b', 'Option B'],
          ['option_c', 'Option C'],
          ['option_d', 'Option D'],
        ] as const
      ).map(([field, label]) => (
        <div className="field" key={field}>
          <label>{label}</label>
          <input
            required
            value={form[field]}
            onChange={(event) => onChange({ ...form, [field]: event.target.value })}
          />
        </div>
      ))}
      <div className="field">
        <label>Correct option</label>
        <select
          value={form.correct_option}
          onChange={(event) => onChange({ ...form, correct_option: event.target.value })}
        >
          {['A', 'B', 'C', 'D'].map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Marks</label>
        <input
          type="number"
          min="0.5"
          step="0.5"
          value={form.marks}
          onChange={(event) => onChange({ ...form, marks: event.target.value })}
        />
      </div>
      {showDifficulty && (
        <div className="field">
          <label>Difficulty</label>
          <select
            value={form.difficulty}
            onChange={(event) => onChange({ ...form, difficulty: event.target.value })}
          >
            {['easy', 'medium', 'hard'].map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="field full-field">
        <label>Explanation (shown with results)</label>
        <textarea
          rows={2}
          value={form.explanation}
          onChange={(event) => onChange({ ...form, explanation: event.target.value })}
        />
      </div>
    </>
  )
}

export default OnlineExamsPage
