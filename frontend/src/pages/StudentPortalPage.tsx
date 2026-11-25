import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import CertificatePreviewModal from '../components/CertificatePreviewModal'
import CopyButton from '../components/CopyButton'
import { apiErrorMessage } from '../utils/apiErrors'
import { externalFormLabel } from '../utils/externalForms'
import { openAuthenticatedFile } from '../utils/files'
import {
  certificateErrorMessage,
  downloadCertificateDocument,
} from '../utils/certificateDocument'
import {
  certificateVerificationPath,
  countLabel,
  formatCertificateDate,
  formatCertificateResult,
} from '../utils/certificateUi'
import AuthImage from '../components/AuthImage'

type Installment = {
  id: number
  installment_number: number
  amount: number
  due_date: string
  status: string
  paid: number
  claimable_amount: number
}
type Enrollment = {
  enrollment_code: string
  batch_name: string
  course_name: string
  status: string
  total_fee: number
  total_paid: number
  balance: number
  upi_id: string | null
  upi_payee_name: string | null
  upi_qr_code_url: string | null
  installments: Installment[]
}
type Attendance = {
  enrollment_code: string
  total: number
  present: number
  late: number
  absent: number
  percentage: number
}
type Result = {
  examination: string
  exam_date: string
  subject: string
  marks_obtained: number
  maximum_marks: number
  grade: string
}
type Certificate = {
  id: number
  certificate_number: string
  verification_code: string
  document_type: string
  issue_date: string
  grade: string | null
  percentage: number | null
  is_valid: boolean
}
type Portal = {
  student_code: string
  full_name: string
  email: string | null
  phone: string | null
  enrollments: Enrollment[]
  attendance: Attendance[]
  results: Result[]
  certificates: Certificate[]
}

type PlacementOpportunity = {
  id: number
  company_name: string
  title: string
  description: string | null
  location: string | null
  employment_type: string
  work_mode: string
  salary_min: string | null
  salary_max: string | null
  vacancies: number
  last_date: string | null
  course_names: string[]
  application_id: number | null
  application_status: string | null
}

type PlacementApplication = {
  id: number
  job_opening_id: number
  opening_title: string
  company_name: string
  status: string
  interview_date: string | null
  interview_mode: string | null
  interview_location: string | null
  feedback: string | null
  offer_salary: string | null
  offer_date: string | null
  joining_date: string | null
  offer_letter_url: string | null
  applied_at: string
}

type LearningLesson = {
  id: number
  title: string
  description: string | null
  lesson_type: string
  content_url: string | null
  content_text: string | null
  duration_minutes: number
  status: string
  time_spent_seconds: number
  completed_at: string | null
}
type LearningModule = {
  id: number
  title: string
  description: string | null
  position: number
  lessons: LearningLesson[]
}
type LearningSubmission = {
  status: string
  marks: string | null
  grade: string | null
  feedback: string | null
  file_url: string | null
  file_name: string | null
  text_answer: string | null
  submitted_at: string
  graded_at: string | null
}
type LearningAssignment = {
  id: number
  module_id: number | null
  title: string
  description: string | null
  instructions: string | null
  due_date: string | null
  max_marks: string
  attachment_url: string | null
  submission: LearningSubmission | null
}
type LearningQuiz = {
  id: number
  module_id: number | null
  title: string
  description: string | null
  quiz_type: string
  pass_percentage: number
  time_limit_minutes: number | null
  question_count: number
  best_percentage: number | null
  passed: boolean
  attempts: number
}
type LearningEnrollment = {
  enrollment_id: number
  enrollment_code: string
  course_id: number
  course_name: string
  batch_name: string
  status: string
  progress_percentage: number
  total_lessons: number
  completed_lessons: number
  time_spent_seconds: number
  modules: LearningModule[]
  assignments: LearningAssignment[]
  quizzes: LearningQuiz[]
}
type QuizTake = {
  id: number
  attempt_id: number
  title: string
  description: string | null
  pass_percentage: number
  time_limit_minutes: number | null
  started_at: string
  expires_at: string | null
  questions: {
    id: number
    question_text: string
    option_a: string
    option_b: string
    option_c: string
    option_d: string
    marks: string
    position: number
  }[]
}
type QuizResult = {
  attempt_id: number
  score: string
  total_marks: string
  percentage: number
  passed: boolean
  correct_answers: number
  total_questions: number
}

type StudentOnlineExam = {
  exam_id: number
  enrollment_id: number
  course_name: string
  title: string
  description: string | null
  instructions: string | null
  external_form: boolean
  external_form_provider: 'google' | 'microsoft' | null
  external_form_url: string | null
  start_at: string | null
  end_at: string | null
  duration_minutes: number
  pass_percentage: number
  max_attempts: number
  question_count: number
  total_marks: string
  attempts_used: number
  state: string
  can_start: boolean
  in_progress_attempt_id: number | null
  last_attempt_id: number | null
  best_percentage: number | null
  passed: boolean
  results_published: boolean
  note: string | null
}

type StudentExamQuestion = {
  id: number
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  marks: string
  position: number
}

type StudentExamAttempt = {
  attempt_id: number
  exam_id: number
  title: string
  instructions: string | null
  status: string
  attempt_number: number
  started_at: string
  expires_at: string | null
  remaining_seconds: number | null
  total_marks: string
  questions: StudentExamQuestion[]
  answers: Record<string, string>
}

type StudentExamResult = {
  attempt_id: number
  exam_id: number
  title: string
  status: string
  score: string | null
  total_marks: string
  percentage: number | null
  passed: boolean | null
  correct_answers: number | null
  total_questions: number
  submitted_at: string | null
  auto_submitted: boolean
  results_published: boolean
  note: string | null
}

const examOptionFields = [
  ['A', 'option_a'],
  ['B', 'option_b'],
  ['C', 'option_c'],
  ['D', 'option_d'],
] as const

function formatExamDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatClock(seconds: number | null): string {
  if (seconds === null) return '—'
  const safe = Math.max(0, seconds)
  const minutes = Math.floor(safe / 60)
  const rest = safe % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function documentLabel(value: string): string {
  return value === 'certificate' ? 'Certificate' : 'Marksheet'
}

function StudentPortalPage() {
  const [portal, setPortal] = useState<Portal | null>(null)
  const [error, setError] = useState('')
  const [searchParams] = useSearchParams()
  const [qrToken, setQrToken] = useState(
    () => searchParams.get('attendance_token') ?? '',
  )
  const [qrMessage, setQrMessage] = useState('')
  const [submittingQr, setSubmittingQr] = useState(false)
  const [paymentInstallment, setPaymentInstallment] = useState<{
    enrollment: Enrollment
    installment: Installment
  } | null>(null)
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentReference, setPaymentReference] = useState('')
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10))
  const [paymentError, setPaymentError] = useState('')
  const [paymentMessage, setPaymentMessage] = useState('')
  const [paymentSubmitting, setPaymentSubmitting] = useState(false)
  const [preview, setPreview] = useState<Certificate | null>(null)
  const [downloadingId, setDownloadingId] = useState<number | null>(null)
  const [documentError, setDocumentError] = useState('')
  const [documentMessage, setDocumentMessage] = useState('')
  const [learning, setLearning] = useState<LearningEnrollment[]>([])
  const [learningLoading, setLearningLoading] = useState(true)
  const [learningError, setLearningError] = useState('')
  const [learningMessage, setLearningMessage] = useState('')
  const [learningBusy, setLearningBusy] = useState('')
  const [placementOpportunities, setPlacementOpportunities] = useState<PlacementOpportunity[]>([])
  const [placementApplications, setPlacementApplications] = useState<PlacementApplication[]>([])
  const [placementLoading, setPlacementLoading] = useState(true)
  const [placementError, setPlacementError] = useState('')
  const [placementMessage, setPlacementMessage] = useState('')
  const [placementBusy, setPlacementBusy] = useState<number | null>(null)
  const [openAssignmentId, setOpenAssignmentId] = useState<number | null>(null)
  const [assignmentText, setAssignmentText] = useState('')
  const [assignmentFile, setAssignmentFile] = useState<File | null>(null)
  const [quizTake, setQuizTake] = useState<QuizTake | null>(null)
  const [quizAnswers, setQuizAnswers] = useState<Record<number, string>>({})
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null)
  const [onlineExams, setOnlineExams] = useState<StudentOnlineExam[]>([])
  const [examLoading, setExamLoading] = useState(true)
  const [examError, setExamError] = useState('')
  const [examMessage, setExamMessage] = useState('')
  const [examBusy, setExamBusy] = useState('')
  const [examTake, setExamTake] = useState<StudentExamAttempt | null>(null)
  const [examAnswers, setExamAnswers] = useState<Record<number, string>>({})
  const [examResult, setExamResult] = useState<StudentExamResult | null>(null)
  const [examRemaining, setExamRemaining] = useState<number | null>(null)
  const [quizRemaining, setQuizRemaining] = useState<number | null>(null)
  const examAnswersRef = useRef<Record<number, string>>({})
  const examSubmitGuard = useRef(false)
  const quizSubmitGuard = useRef(false)

  const loadOnlineExams = useCallback(async () => {
    setExamLoading(true)
    setExamError('')
    try {
      const { data } = await api.get<StudentOnlineExam[]>('/api/online-exams/me/exams')
      setOnlineExams(data)
    } catch (requestError) {
      setExamError(
        apiErrorMessage(requestError, 'Online exams are not available for your account yet.'),
      )
    } finally {
      setExamLoading(false)
    }
  }, [])

  const submitExam = useCallback(
    async (auto = false) => {
      const attempt = examTake
      if (!attempt || attempt.status !== 'in_progress') return
      setExamBusy('exam-submit')
      setExamError('')
      try {
        const { data } = await api.post<StudentExamResult>(
          `/api/online-exams/me/attempts/${attempt.attempt_id}/submit`,
          {
            auto,
            answers: attempt.questions.map((question) => ({
              question_id: question.id,
              selected_option: examAnswersRef.current[question.id] ?? null,
            })),
          },
        )
        setExamResult(data)
        setExamTake(null)
        setExamRemaining(null)
        setExamMessage(
          auto
            ? 'Time is up — your answers were submitted automatically.'
            : 'Your exam was submitted. Results appear once your institute publishes them.',
        )
        await loadOnlineExams()
      } catch (requestError) {
        setExamError(apiErrorMessage(requestError, 'Unable to submit the exam.'))
        await loadOnlineExams()
      } finally {
        setExamBusy('')
      }
    },
    [examTake, loadOnlineExams],
  )

  async function loadLearning() {
    setLearningLoading(true)
    setLearningError('')
    try {
      const { data } = await api.get<{ enrollments: LearningEnrollment[] }>(
        '/api/lms/me/learning',
      )
      setLearning(data.enrollments)
    } catch (requestError) {
      setLearningError(
        certificateErrorMessage(
          requestError,
          'Learning content is not available for your account yet.',
        ),
      )
    } finally {
      setLearningLoading(false)
    }
  }

  const submitQuiz = useCallback(async () => {
    if (!quizTake) return
    setLearningBusy(`quiz-submit-${quizTake.id}`)
    setLearningError('')
    try {
      const { data } = await api.post<QuizResult>(
        `/api/lms/me/quizzes/${quizTake.id}/submit`,
        {
          attempt_id: quizTake.attempt_id,
          answers: quizTake.questions.map((question) => ({
            question_id: question.id,
            selected_option: quizAnswers[question.id] ?? null,
          })),
        },
      )
      setQuizResult(data)
      setQuizRemaining(null)
      await loadLearning()
    } catch (requestError) {
      setLearningError(apiErrorMessage(requestError, 'Unable to submit this quiz.'))
    } finally {
      setLearningBusy('')
    }
  }, [quizTake, quizAnswers])

  async function loadPlacement() {
    setPlacementLoading(true)
    setPlacementError('')
    try {
      const [opportunities, applications] = await Promise.all([
        api.get<PlacementOpportunity[]>('/api/placement-portal/opportunities'),
        api.get<PlacementApplication[]>('/api/placement-portal/applications'),
      ])
      setPlacementOpportunities(opportunities.data)
      setPlacementApplications(applications.data)
    } catch (requestError) {
      setPlacementError(
        apiErrorMessage(requestError, 'Placement opportunities are not available yet.'),
      )
    } finally {
      setPlacementLoading(false)
    }
  }

  async function applyToOpening(opportunity: PlacementOpportunity) {
    const note = window.prompt(
      `Apply to ${opportunity.title} at ${opportunity.company_name}?\n\nOptional cover note:`,
      '',
    )
    if (note === null) return
    setPlacementBusy(opportunity.id)
    setPlacementError('')
    setPlacementMessage('')
    try {
      await api.post(
        `/api/placement-portal/opportunities/${opportunity.id}/apply`,
        { cover_note: note.trim() || null },
      )
      setPlacementMessage(`Application sent to ${opportunity.company_name}.`)
      await loadPlacement()
    } catch (requestError) {
      setPlacementError(apiErrorMessage(requestError, 'Unable to submit your application.'))
    } finally {
      setPlacementBusy(null)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadLearning()
      void loadOnlineExams()
      void loadPlacement()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadOnlineExams])

  useEffect(() => {
    if (!examTake || examTake.status !== 'in_progress') return
    examSubmitGuard.current = false
    const timer = window.setInterval(() => {
      setExamRemaining((current) => {
        if (current === null) return current
        return current <= 1 ? 0 : current - 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [examTake])

  useEffect(() => {
    if (!examTake || examTake.status !== 'in_progress') return
    if (examRemaining !== 0) return
    if (examSubmitGuard.current) return
    examSubmitGuard.current = true
    void submitExam(true)
  }, [examRemaining, examTake, submitExam])

  useEffect(() => {
    if (!quizTake || quizResult) return
    quizSubmitGuard.current = false
    const timer = window.setInterval(() => {
      setQuizRemaining((current) => {
        if (current === null) return current
        return current <= 1 ? 0 : current - 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [quizTake, quizResult])

  useEffect(() => {
    if (!quizTake || quizResult) return
    if (quizRemaining !== 0) return
    if (quizSubmitGuard.current) return
    quizSubmitGuard.current = true
    void submitQuiz()
  }, [quizRemaining, quizTake, quizResult, submitQuiz])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void api
        .get<Portal>('/api/student-portal/me')
        .then(({ data }) => setPortal(data))
        .catch(() =>
          setError(
            'Unable to load your student portal. Please contact the institute administrator.',
          ),
        )
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  function logout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    window.location.assign('/login')
  }

  async function submitQr() {
    setSubmittingQr(true)
    setQrMessage('')
    try {
      await api.post('/api/attendance/sessions/submit', {
        token: qrToken.trim(),
      })
      setQrMessage('Attendance marked successfully.')
      setQrToken('')
    } catch {
      setQrMessage(
        'This QR code is expired, invalid, or attendance was already recorded.',
      )
    } finally {
      setSubmittingQr(false)
    }
  }

  async function submitFeeClaim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!paymentInstallment) return
    const amount = Number(paymentAmount)
    if (!Number.isFinite(amount) || amount <= 0 || amount > Number(paymentInstallment.installment.claimable_amount)) {
      setPaymentError('Enter an amount greater than zero and no more than the outstanding amount.')
      return
    }
    setPaymentSubmitting(true)
    setPaymentError('')
    setPaymentMessage('')
    try {
      await api.post(
        `/api/student-portal/installments/${paymentInstallment.installment.id}/claims`,
        {
          amount,
          upi_reference: paymentReference.trim(),
          paid_on: paymentDate,
        },
      )
      setPaymentMessage('Payment submitted for verification. Your balance will update after institute approval.')
      setPaymentInstallment(null)
      setPaymentAmount('')
      setPaymentReference('')
      const { data } = await api.get<Portal>('/api/student-portal/me')
      setPortal(data)
    } catch (requestError) {
      setPaymentError(apiErrorMessage(requestError, 'Unable to submit this payment.'))
    } finally {
      setPaymentSubmitting(false)
    }
  }

  async function download(certificate: Certificate) {
    setDownloadingId(certificate.id)
    setDocumentError('')
    setDocumentMessage('')
    try {
      await downloadCertificateDocument(
        certificate.id,
        certificate.certificate_number,
      )
      setDocumentMessage(`Downloaded ${certificate.certificate_number}.pdf`)
    } catch (requestError) {
      setDocumentError(
        certificateErrorMessage(
          requestError,
          'Unable to download this document. Please try again.',
        ),
      )
    } finally {
      setDownloadingId(null)
    }
  }

  async function completeLesson(lesson: LearningLesson) {
    setLearningBusy(`lesson-${lesson.id}`)
    setLearningError('')
    setLearningMessage('')
    try {
      await api.post(`/api/lms/me/lessons/${lesson.id}/complete`, {
        time_spent_seconds: Math.max(lesson.duration_minutes, 1) * 60,
      })
      setLearningMessage(`Marked “${lesson.title}” as complete.`)
      await loadLearning()
    } catch (requestError) {
      setLearningError(
        apiErrorMessage(requestError, 'Unable to save your lesson progress.'),
      )
    } finally {
      setLearningBusy('')
    }
  }

  async function openSubmissionFile(path: string) {
    setLearningError('')
    try {
      await openAuthenticatedFile(path)
    } catch {
      setLearningError('Unable to open the submitted file.')
    }
  }

  async function submitAssignment(assignment: LearningAssignment) {
    if (!assignmentText.trim() && !assignmentFile) {
      setLearningError('Add an answer or attach a file before submitting.')
      return
    }
    setLearningBusy(`assignment-${assignment.id}`)
    setLearningError('')
    setLearningMessage('')
    const formData = new FormData()
    formData.append('text_answer', assignmentText.trim())
    if (assignmentFile) formData.append('file', assignmentFile)
    try {
      await api.post(`/api/lms/me/assignments/${assignment.id}/submit`, formData)
      setLearningMessage(`Submitted “${assignment.title}”.`)
      setOpenAssignmentId(null)
      setAssignmentText('')
      setAssignmentFile(null)
      await loadLearning()
    } catch (requestError) {
      setLearningError(
        apiErrorMessage(requestError, 'Unable to submit this assignment.'),
      )
    } finally {
      setLearningBusy('')
    }
  }

  async function openQuiz(quiz: LearningQuiz) {
    setLearningBusy(`quiz-${quiz.id}`)
    setLearningError('')
    setQuizResult(null)
    setQuizAnswers({})
    setQuizRemaining(null)
    quizSubmitGuard.current = false
    try {
      const { data } = await api.get<QuizTake>(`/api/lms/me/quizzes/${quiz.id}`)
      setQuizTake(data)
      if (data.expires_at) {
        const deadline = new Date(
          data.expires_at.endsWith('Z') ? data.expires_at : `${data.expires_at}Z`,
        )
        // eslint-disable-next-line react-hooks/purity
        setQuizRemaining(Math.max(0, Math.floor((deadline.getTime() - Date.now()) / 1000)))
      } else {
        setQuizRemaining(null)
      }
    } catch (requestError) {
      setLearningError(apiErrorMessage(requestError, 'Unable to open this quiz.'))
    } finally {
      setLearningBusy('')
    }
  }


  async function openExam(exam: StudentOnlineExam) {
    setExamBusy(`exam-open-${exam.exam_id}`)
    setExamError('')
    setExamMessage('')
    setExamResult(null)
    try {
      const { data } = exam.in_progress_attempt_id
        ? await api.get<StudentExamAttempt>(
            `/api/online-exams/me/attempts/${exam.in_progress_attempt_id}`,
          )
        : await api.post<StudentExamAttempt>(
            `/api/online-exams/me/exams/${exam.exam_id}/start`,
          )
      if (data.status !== 'in_progress') {
        setExamResult(
          await api
            .get<StudentExamResult>(
              `/api/online-exams/me/attempts/${data.attempt_id}/result`,
            )
            .then((response) => response.data),
        )
        await loadOnlineExams()
        return
      }
      const mapped: Record<number, string> = {}
      Object.entries(data.answers ?? {}).forEach(([questionId, option]) => {
        mapped[Number(questionId)] = option
      })
      examAnswersRef.current = mapped
      setExamAnswers(mapped)
      setExamRemaining(data.remaining_seconds)
      setExamTake(data)
    } catch (requestError) {
      setExamError(apiErrorMessage(requestError, 'Unable to open this exam.'))
      await loadOnlineExams()
    } finally {
      setExamBusy('')
    }
  }

  async function selectExamAnswer(questionId: number, option: string) {
    if (!examTake || examTake.status !== 'in_progress') return
    const next = { ...examAnswersRef.current, [questionId]: option }
    examAnswersRef.current = next
    setExamAnswers(next)
    try {
      await api.put(`/api/online-exams/me/attempts/${examTake.attempt_id}/answers`, {
        answers: [{ question_id: questionId, selected_option: option }],
      })
    } catch (requestError) {
      setExamError(
        apiErrorMessage(requestError, 'Unable to save that answer. Check your connection.'),
      )
    }
  }

  async function openExamResult(exam: StudentOnlineExam) {
    if (!exam.last_attempt_id) return
    setExamBusy(`exam-result-${exam.exam_id}`)
    setExamError('')
    try {
      const { data } = await api.get<StudentExamResult>(
        `/api/online-exams/me/attempts/${exam.last_attempt_id}/result`,
      )
      setExamResult(data)
    } catch (requestError) {
      setExamError(apiErrorMessage(requestError, 'Unable to load this result.'))
    } finally {
      setExamBusy('')
    }
  }

  function closeExamModal() {
    setExamTake(null)
    setExamResult(null)
    setExamRemaining(null)
    examSubmitGuard.current = false
    examAnswersRef.current = {}
    setExamAnswers({})
  }

  if (error) {
    return (
      <main className="student-shell">
        <div className="student-error">{error}</div>
      </main>
    )
  }
  if (!portal) {
    return (
      <main className="student-shell">
        <div className="table-state">Loading your portal…</div>
      </main>
    )
  }

  const paid = portal.enrollments.reduce(
    (sum, enrollment) => sum + Number(enrollment.total_paid),
    0,
  )
  const balance = portal.enrollments.reduce(
    (sum, enrollment) => sum + Number(enrollment.balance),
    0,
  )

  return (
    <main className="student-shell">
      <header className="student-topbar">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <strong>NICT</strong>
            <span>Student Portal</span>
          </div>
        </div>
        <div className="student-account">
          <div className="avatar">{portal.full_name.slice(0, 1).toUpperCase()}</div>
          <div>
            <strong>{portal.full_name}</strong>
            <small>{portal.student_code}</small>
          </div>
          <button className="secondary-button" onClick={logout} type="button">
            Sign out
          </button>
        </div>
      </header>

      <div className="student-content">
        <div className="page-heading module-heading">
          <div>
            <span className="eyebrow">WELCOME BACK</span>
            <h1>{portal.full_name}</h1>
            <p>
              {portal.email ?? 'Student account'}
              {portal.phone ? ` · ${portal.phone}` : ''}
            </p>
          </div>
        </div>

        <section className="data-panel qr-submit-card">
          <div>
            <span className="eyebrow">QR ATTENDANCE</span>
            <h2>Mark today’s attendance</h2>
            <p>
              Scan the QR code shown by your faculty, then paste the token here
              if your camera does not open the portal automatically.
            </p>
          </div>
          <div className="inline-form-row">
            <input
              aria-label="Attendance QR token"
              placeholder="Paste attendance token"
              value={qrToken}
              onChange={(event) => setQrToken(event.target.value)}
            />
            <button
              className="primary-button"
              disabled={!qrToken.trim() || submittingQr}
              onClick={() => void submitQr()}
              type="button"
            >
              {submittingQr ? 'Submitting…' : 'Submit attendance'}
            </button>
          </div>
          {qrMessage && <div className="success-message">{qrMessage}</div>}
        </section>

        <section className="metric-grid fee-metrics">
          <article className="metric-card">
            <div className="metric-label">Enrollments</div>
            <div className="metric-value">{portal.enrollments.length}</div>
            <div className="metric-detail">Courses and batches</div>
          </article>
          <article className="metric-card">
            <div className="metric-label">Fees paid</div>
            <div className="metric-value">₹{paid.toLocaleString('en-IN')}</div>
            <div className="metric-detail">Recorded payments</div>
          </article>
          <article className="metric-card">
            <div className="metric-label">Balance</div>
            <div className="metric-value">₹{balance.toLocaleString('en-IN')}</div>
            <div className="metric-detail">Outstanding fees</div>
          </article>
        </section>

        <section className="data-panel student-section">
          <div className="section-title">
            <div>
              <span className="eyebrow">MY COURSES</span>
              <h2>Enrollment and fees</h2>
            </div>
          </div>
          <div className="student-cards">
            {portal.enrollments.map((enrollment) => (
              <article className="student-card" key={enrollment.enrollment_code}>
                <div>
                  <strong>{enrollment.course_name}</strong>
                  <span>
                    {enrollment.batch_name} · {enrollment.enrollment_code}
                  </span>
                </div>
                <div className="student-fee-line">
                  <span>
                    Paid ₹{Number(enrollment.total_paid).toLocaleString('en-IN')}
                  </span>
                  <span>
                    Balance ₹{Number(enrollment.balance).toLocaleString('en-IN')}
                  </span>
                </div>
                {enrollment.installments.length > 0 && (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Installment</th>
                          <th>Due</th>
                          <th>Amount</th>
                          <th>Paid</th>
                          <th>Status / payment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {enrollment.installments.map((installment) => (
                          <tr key={installment.installment_number}>
                            <td>{installment.installment_number}</td>
                            <td>{installment.due_date}</td>
                            <td>
                              ₹{Number(installment.amount).toLocaleString('en-IN')}
                            </td>
                            <td>
                              ₹{Number(installment.paid).toLocaleString('en-IN')}
                            </td>
                            <td>
                              <span>{installment.status}</span>
                              {Number(installment.claimable_amount) > 0 && (
                                <button
                                  className="text-link"
                                  onClick={() => {
                                    setPaymentInstallment({ enrollment, installment })
                                    setPaymentAmount(String(installment.claimable_amount))
                                    setPaymentDate(new Date().toISOString().slice(0, 10))
                                    setPaymentError('')
                                  }}
                                  type="button"
                                >
                                  Pay fees
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </article>
            ))}
          </div>
          {!portal.enrollments.length && (
            <div className="table-state">
              No enrollments are linked to your account yet.
            </div>
          )}
        </section>

        <section className="data-panel student-section">
          <div className="section-title">
            <div>
              <span className="eyebrow">MY LEARNING</span>
              <h2>Lessons, assignments and quizzes</h2>
            </div>
            <span className="result-count">{learning.length} courses</span>
          </div>
          {learningError && <div className="inline-error">{learningError}</div>}
          {learningMessage && <div className="success-message">{learningMessage}</div>}
          {learningLoading && (
            <div className="table-state">Loading your learning content…</div>
          )}
          {!learningLoading &&
            learning.map((enrollment) => (
              <article
                className="student-card student-learning-card"
                key={enrollment.enrollment_id}
              >
                <div className="student-learning-head">
                  <div>
                    <h3>{enrollment.course_name}</h3>
                    <span>
                      {enrollment.batch_name} · {enrollment.enrollment_code}
                    </span>
                  </div>
                  <div className="student-learning-progress">
                    <div className="lms-progress-track">
                      <span
                        style={{
                          width: `${Math.min(enrollment.progress_percentage, 100)}%`,
                        }}
                      />
                    </div>
                    <strong>{enrollment.progress_percentage}%</strong>
                    <small>
                      {enrollment.completed_lessons}/{enrollment.total_lessons} lessons
                    </small>
                  </div>
                </div>

                <div className="student-learning-grid">
                  <div>
                    {enrollment.modules.map((module) => (
                      <div className="student-module" key={module.id}>
                        <strong>{module.title}</strong>
                        {module.lessons.map((lesson) => (
                          <div className="student-lesson" key={lesson.id}>
                            <div>
                              <strong>{lesson.title}</strong>
                              {lesson.description && <p>{lesson.description}</p>}
                              {lesson.content_text && <p>{lesson.content_text}</p>}
                              <small>
                                {lesson.lesson_type} · {lesson.duration_minutes} min
                              </small>
                              {lesson.content_url && (
                                <a
                                  href={lesson.content_url}
                                  rel="noreferrer"
                                  target="_blank"
                                >
                                  Open resource
                                </a>
                              )}
                            </div>
                            {lesson.status === 'completed' ? (
                              <span className="status-pill active-status">
                                <i />
                                Completed
                              </span>
                            ) : (
                              <button
                                className="secondary-button"
                                disabled={learningBusy === `lesson-${lesson.id}`}
                                onClick={() => void completeLesson(lesson)}
                                type="button"
                              >
                                {learningBusy === `lesson-${lesson.id}`
                                  ? 'Saving…'
                                  : 'Mark complete'}
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                    {!enrollment.modules.length && (
                      <div className="table-state">
                        Course content has not been published yet.
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="student-module">
                      <strong>Assignments</strong>
                      {enrollment.assignments.map((assignment) => (
                        <div className="student-assignment" key={assignment.id}>
                          <strong>{assignment.title}</strong>
                          {assignment.description && <p>{assignment.description}</p>}
                          <small className="muted-block">
                            {assignment.max_marks} marks
                            {assignment.due_date ? ` · due ${assignment.due_date}` : ''}
                          </small>
                          {assignment.submission ? (
                            <div>
                              <span className="status-pill active-status">
                                <i />
                                {assignment.submission.status === 'graded'
                                  ? 'Graded'
                                  : 'Submitted'}
                              </span>
                              {assignment.submission.status === 'graded' && (
                                <p>
                                  {assignment.submission.marks} / {assignment.max_marks} ·{' '}
                                  {assignment.submission.grade}
                                  {assignment.submission.feedback
                                    ? ` — ${assignment.submission.feedback}`
                                    : ''}
                                </p>
                              )}
                              {assignment.submission.file_url && (
                                <button
                                  className="row-link"
                                  onClick={() => {
                                    const fileUrl = assignment.submission?.file_url
                                    if (fileUrl) void openSubmissionFile(fileUrl)
                                  }}
                                  type="button"
                                >
                                  View submitted file
                                </button>
                              )}
                              {assignment.submission.status !== 'graded' && (
                                <button
                                  className="row-link"
                                  onClick={() => {
                                    setOpenAssignmentId(assignment.id)
                                    setAssignmentText(assignment.submission?.text_answer ?? '')
                                    setAssignmentFile(null)
                                  }}
                                  type="button"
                                >
                                  Replace submission
                                </button>
                              )}
                            </div>
                          ) : (
                            <button
                              className="secondary-button"
                              onClick={() => {
                                setOpenAssignmentId(assignment.id)
                                setAssignmentText('')
                                setAssignmentFile(null)
                              }}
                              type="button"
                            >
                              Submit assignment
                            </button>
                          )}
                          {openAssignmentId === assignment.id &&
                            assignment.submission?.status !== 'graded' && (
                              <div>
                                <textarea
                                  aria-label={`Answer for ${assignment.title}`}
                                  rows={4}
                                  placeholder="Type your answer or paste the code here"
                                  value={assignmentText}
                                  onChange={(event) => setAssignmentText(event.target.value)}
                                />
                                <div className="inline-form-row">
                                  <input
                                    aria-label="Assignment file"
                                    onChange={(event) =>
                                      setAssignmentFile(event.target.files?.[0] ?? null)
                                    }
                                    type="file"
                                  />
                                  <button
                                    className="primary-button"
                                    disabled={
                                      learningBusy === `assignment-${assignment.id}`
                                    }
                                    onClick={() => void submitAssignment(assignment)}
                                    type="button"
                                  >
                                    {learningBusy === `assignment-${assignment.id}`
                                      ? 'Submitting…'
                                      : 'Submit'}
                                  </button>
                                  <button
                                    className="secondary-button"
                                    onClick={() => setOpenAssignmentId(null)}
                                    type="button"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            )}
                        </div>
                      ))}
                      {!enrollment.assignments.length && (
                        <p className="muted">No assignments for this course.</p>
                      )}
                    </div>

                    <div className="student-module">
                      <strong>Quizzes</strong>
                      {enrollment.quizzes.map((quiz) => (
                        <div className="student-quiz-row" key={quiz.id}>
                          <div>
                            <strong>{quiz.title}</strong>
                            <small>
                              {quiz.question_count} questions · pass {quiz.pass_percentage}%
                              {quiz.time_limit_minutes
                                ? ` · ${quiz.time_limit_minutes} min`
                                : ''}
                            </small>
                            {quiz.attempts > 0 && (
                              <small>
                                Best {quiz.best_percentage}% ·{' '}
                                {quiz.passed ? 'passed' : 'not passed'} · {quiz.attempts}{' '}
                                attempt(s)
                              </small>
                            )}
                          </div>
                          <button
                            className="secondary-button"
                            disabled={learningBusy === `quiz-${quiz.id}`}
                            onClick={() => void openQuiz(quiz)}
                            type="button"
                          >
                            {learningBusy === `quiz-${quiz.id}`
                              ? 'Opening…'
                              : quiz.attempts > 0
                                ? 'Retake'
                                : 'Start'}
                          </button>
                        </div>
                      ))}
                      {!enrollment.quizzes.length && (
                        <p className="muted">No quizzes for this course.</p>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            ))}
          {!learningLoading && !learning.length && (
            <div className="table-state">
              No learning content is linked to your enrollments yet.
            </div>
          )}
        </section>

        <section className="data-panel student-section">
          <div className="section-title">
            <div>
              <span className="eyebrow">ONLINE EXAMS</span>
              <h2>Timed assessments</h2>
            </div>
            <span className="result-count">{onlineExams.length} exams</span>
          </div>
          {examError && <div className="inline-error">{examError}</div>}
          {examMessage && <div className="success-message">{examMessage}</div>}
          {examLoading && (
            <div className="table-state">Loading your online exams…</div>
          )}
          {!examLoading && onlineExams.length > 0 && (
            <div className="student-exam-list">
              {onlineExams.map((exam) => {
                const stateLabel = exam.external_form
                  ? exam.state === 'closed'
                    ? 'Closed'
                    : exam.state === 'not_started'
                      ? 'Opens later'
                      : exam.external_form_url
                        ? 'Form available'
                        : 'Unavailable'
                  : exam.state === 'in_progress'
                    ? 'In progress'
                    : exam.state === 'completed'
                      ? 'Attempts used'
                      : exam.state === 'closed'
                        ? 'Closed'
                        : exam.state === 'not_started'
                          ? 'Opens later'
                          : exam.can_start
                            ? 'Available'
                            : 'Unavailable'
                const actionLabel = exam.external_form
                  ? 'Open exam form'
                  : exam.state === 'in_progress'
                    ? 'Resume exam'
                    : exam.can_start
                      ? 'Start exam'
                      : 'Not available'
                return (
                  <article className="student-exam-card" key={exam.exam_id}>
                    <div className="student-exam-main">
                      <strong>{exam.title}</strong>
                      <small>
                        {exam.course_name} ·{' '}
                        {exam.external_form
                          ? `${externalFormLabel(exam.external_form_provider)} exam`
                          : `${exam.question_count} questions · ${exam.total_marks} marks · ${exam.duration_minutes} min`}
                      </small>
                      {exam.description && <p>{exam.description}</p>}
                      <small className="muted-block">
                        {formatExamDateTime(exam.start_at)} →{' '}
                        {formatExamDateTime(exam.end_at)} · pass {exam.pass_percentage}%
                      </small>
                      <div className="exam-chip-row">
                        <span className="exam-chip">{stateLabel}</span>
                        {exam.external_form ? (
                          <span className="exam-chip">
                            {externalFormLabel(exam.external_form_provider)}
                          </span>
                        ) : (
                          <span className="exam-chip">
                            {exam.attempts_used} of {exam.max_attempts} attempt(s)
                          </span>
                        )}
                        {exam.results_published && exam.best_percentage !== null && (
                          <span className="exam-chip">
                            Best {exam.best_percentage}% ·{' '}
                            {exam.passed ? 'passed' : 'not passed'}
                          </span>
                        )}
                        {!exam.results_published && exam.attempts_used > 0 && (
                          <span className="exam-chip">Results pending</span>
                        )}
                      </div>
                      {exam.note && <small className="muted-block">{exam.note}</small>}
                    </div>
                    <div className="student-exam-actions">
                      {exam.external_form ? (
                        exam.external_form_url ? (
                          <a
                            className="primary-button external-form-button"
                            href={exam.external_form_url}
                            rel="noopener noreferrer"
                            target="_blank"
                          >
                            {actionLabel} ↗
                          </a>
                        ) : (
                          <button className="primary-button" disabled type="button">
                            {actionLabel}
                          </button>
                        )
                      ) : (
                        <button
                          className="primary-button"
                          disabled={
                            (!exam.can_start && exam.state !== 'in_progress') ||
                            examBusy === `exam-open-${exam.exam_id}`
                          }
                          onClick={() => void openExam(exam)}
                          type="button"
                        >
                          {examBusy === `exam-open-${exam.exam_id}`
                            ? 'Opening…'
                            : actionLabel}
                        </button>
                      )}
                      {exam.results_published && exam.last_attempt_id && (
                        <button
                          className="secondary-button"
                          disabled={examBusy === `exam-result-${exam.exam_id}`}
                          onClick={() => void openExamResult(exam)}
                          type="button"
                        >
                          {examBusy === `exam-result-${exam.exam_id}`
                            ? 'Loading…'
                            : 'View result'}
                        </button>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          )}
          {!examLoading && !onlineExams.length && (
            <div className="table-state">
              No online exams have been scheduled for your courses yet.
            </div>
          )}
        </section>

        <section className="student-grid">
          <section className="data-panel student-section">
            <div className="section-title">
              <div>
                <span className="eyebrow">ATTENDANCE</span>
                <h2>My attendance</h2>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Enrollment</th>
                    <th>Total</th>
                    <th>Present</th>
                    <th>Late</th>
                    <th>Percentage</th>
                  </tr>
                </thead>
                <tbody>
                  {portal.attendance.map((item) => (
                    <tr key={item.enrollment_code}>
                      <td>{item.enrollment_code}</td>
                      <td>{item.total}</td>
                      <td>{item.present}</td>
                      <td>{item.late}</td>
                      <td>{item.percentage}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!portal.attendance.length && (
                <div className="table-state">No attendance records yet.</div>
              )}
            </div>
          </section>

          <section className="data-panel student-section">
            <div className="section-title">
              <div>
                <span className="eyebrow">RESULTS</span>
                <h2>Published results</h2>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Exam</th>
                    <th>Subject</th>
                    <th>Marks</th>
                    <th>Grade</th>
                  </tr>
                </thead>
                <tbody>
                  {portal.results.map((item, index) => (
                    <tr key={`${item.examination}-${item.subject}-${index}`}>
                      <td>{item.examination}</td>
                      <td>{item.subject}</td>
                      <td>
                        {item.marks_obtained} / {item.maximum_marks}
                      </td>
                      <td>{item.grade}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!portal.results.length && (
                <div className="table-state">No published results yet.</div>
              )}
            </div>
          </section>
        </section>

        <section className="data-panel student-section">
          <div className="section-title">
            <div>
              <span className="eyebrow">CERTIFICATES</span>
              <h2>My documents</h2>
            </div>
            <span className="result-count">
              {countLabel(portal.certificates.length, 'document')}
            </span>
          </div>
          {documentError && <div className="inline-error" role="alert">{documentError}</div>}
          {documentMessage && (
            <div className="success-message" role="status">{documentMessage}</div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Type</th>
                  <th scope="col">Issue date</th>
                  <th scope="col">Result</th>
                  <th scope="col">Verification</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {portal.certificates.map((certificate) => {
                  const downloading = downloadingId === certificate.id
                  return (
                    <tr key={certificate.id}>
                      <td>
                        <strong>{certificate.certificate_number}</strong>
                        {!certificate.is_valid && (
                          <span className="revoked-label">Revoked</span>
                        )}
                      </td>
                      <td>{documentLabel(certificate.document_type)}</td>
                      <td>{formatCertificateDate(certificate.issue_date)}</td>
                      <td>
                        {formatCertificateResult(
                          certificate.grade,
                          certificate.percentage,
                        )}
                      </td>
                      <td>
                        <div className="certificate-code-block">
                          <span className="code-pill">
                            {certificate.verification_code}
                          </span>
                          <div className="certificate-code-actions">
                            <CopyButton value={certificate.verification_code} label="Copy" />
                            <a
                              href={certificateVerificationPath(
                                certificate.verification_code,
                              )}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Verify
                            </a>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="row-actions document-row-actions">
                          <button
                            onClick={() => setPreview(certificate)}
                            type="button"
                          >
                            View
                          </button>
                          <button
                            disabled={downloading}
                            onClick={() => void download(certificate)}
                            type="button"
                          >
                            {downloading ? 'Preparing…' : 'Download'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!portal.certificates.length && (
              <div className="table-state">
                No certificates issued yet. Your certificate will appear here
                once the institute publishes it.
              </div>
            )}
          </div>
        </section>

        <section className="data-panel student-section">
          <div className="section-title">
            <div>
              <span className="eyebrow">PLACEMENT CELL</span>
              <h2>Placement opportunities</h2>
            </div>
            <span className="result-count">
              {placementOpportunities.length} opening
              {placementOpportunities.length === 1 ? '' : 's'}
            </span>
          </div>
          {placementError && <div className="inline-error">{placementError}</div>}
          {placementMessage && (
            <div className="success-message">{placementMessage}</div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Role</th>
                  <th>Location</th>
                  <th>Salary</th>
                  <th>Last date</th>
                  <th>Eligibility</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {placementOpportunities.map((opportunity) => (
                  <tr key={opportunity.id}>
                    <td>
                      <strong>{opportunity.company_name}</strong>
                      <small className="muted-block">
                        {opportunity.employment_type} · {opportunity.work_mode}
                      </small>
                    </td>
                    <td>
                      {opportunity.title}
                      <small className="muted-block">
                        {opportunity.vacancies} vacanc
                        {opportunity.vacancies === 1 ? 'y' : 'ies'}
                      </small>
                    </td>
                    <td>{opportunity.location ?? '—'}</td>
                    <td>
                      {opportunity.salary_min
                        ? `₹${Number(opportunity.salary_min).toLocaleString('en-IN')}`
                        : '—'}
                      {opportunity.salary_max
                        ? ` – ₹${Number(opportunity.salary_max).toLocaleString('en-IN')}`
                        : ''}
                    </td>
                    <td>{opportunity.last_date ?? 'Open'}</td>
                    <td>
                      {opportunity.course_names.length
                        ? opportunity.course_names.join(', ')
                        : 'All courses'}
                    </td>
                    <td>
                      {opportunity.application_status ? (
                        <span className="status-pill active-status">
                          <i />
                          Applied
                        </span>
                      ) : (
                        <button
                          disabled={placementBusy === opportunity.id}
                          onClick={() => void applyToOpening(opportunity)}
                          type="button"
                        >
                          {placementBusy === opportunity.id ? 'Applying…' : 'Apply'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!placementOpportunities.length && (
              <div className="table-state">
                {placementLoading
                  ? 'Loading placement opportunities…'
                  : 'No placement openings are available for your course right now.'}
              </div>
            )}
          </div>
        </section>

        {placementApplications.length > 0 && (
          <section className="data-panel student-section">
            <div className="section-title">
              <div>
                <span className="eyebrow">MY APPLICATIONS</span>
                <h2>Interview and offer tracker</h2>
              </div>
              <span className="result-count">
                {placementApplications.length} application
                {placementApplications.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Interview</th>
                    <th>Offer</th>
                    <th>Feedback</th>
                  </tr>
                </thead>
                <tbody>
                  {placementApplications.map((application) => (
                    <tr key={application.id}>
                      <td>{application.company_name}</td>
                      <td>{application.opening_title}</td>
                      <td>
                        <span className="exam-chip">
                          {application.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td>
                        {application.interview_date
                          ? `${application.interview_date.slice(0, 16).replace('T', ' ')} · ${
                              application.interview_mode ?? 'TBD'
                            }`
                          : '—'}
                        {application.interview_location && (
                          <small className="muted-block">
                            {application.interview_location}
                          </small>
                        )}
                      </td>
                      <td>
                        {application.offer_salary
                          ? `₹${Number(application.offer_salary).toLocaleString('en-IN')}`
                          : '—'}
                        {application.joining_date && (
                          <small className="muted-block">
                            Joins {application.joining_date}
                          </small>
                        )}
                        {application.offer_letter_url && (
                          <a
                            className="muted-block"
                            href={application.offer_letter_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            Offer letter
                          </a>
                        )}
                      </td>
                      <td>{application.feedback ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      {quizTake && (
        <div className="modal-backdrop" onClick={() => setQuizTake(null)}>
          <div
            className="modal-card quiz-take-card"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">QUIZ</span>
                <h2>{quizTake.title}</h2>
                {quizTake.description && <p>{quizTake.description}</p>}
              </div>
              <div className="exam-header-actions">
                {!quizResult && quizRemaining !== null && (
                  <span
                    className={
                      quizRemaining <= 60 ? 'exam-timer exam-timer-low' : 'exam-timer'
                    }
                  >
                    {formatClock(quizRemaining)}
                  </span>
                )}
                <button
                  className="close-button"
                  onClick={() => setQuizTake(null)}
                  type="button"
                >
                  ×
                </button>
              </div>
            </div>
            {quizResult ? (
              <div>
                <div className="quiz-result">
                  <strong>
                    {quizResult.percentage}% · {quizResult.passed ? 'Passed' : 'Not passed'}
                  </strong>
                  <span>
                    {quizResult.correct_answers} of {quizResult.total_questions} correct ·{' '}
                    {quizResult.score} / {quizResult.total_marks} marks
                  </span>
                </div>
                <div className="modal-actions">
                  <button
                    className="primary-button"
                    onClick={() => {
                      setQuizTake(null)
                      setQuizResult(null)
                    }}
                    type="button"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void submitQuiz()
                }}
              >
                {quizTake.questions.map((question) => (
                  <div className="quiz-question" key={question.id}>
                    <p>{question.question_text}</p>
                    <div className="quiz-options">
                      {(
                        [
                          ['A', 'option_a'],
                          ['B', 'option_b'],
                          ['C', 'option_c'],
                          ['D', 'option_d'],
                        ] as const
                      ).map(([key, field]) => (
                        <label key={key}>
                          <input
                            checked={quizAnswers[question.id] === key}
                            name={`question-${question.id}`}
                            onChange={() =>
                              setQuizAnswers({ ...quizAnswers, [question.id]: key })
                            }
                            type="radio"
                          />
                          <span>
                            <strong>{key}.</strong> {question[field]}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                <div className="modal-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setQuizTake(null)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button
                    className="primary-button"
                    disabled={learningBusy === `quiz-submit-${quizTake.id}`}
                    type="submit"
                  >
                    {learningBusy === `quiz-submit-${quizTake.id}`
                      ? 'Submitting…'
                      : 'Submit answers'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {(examTake || examResult) && (
        <div className="modal-backdrop" onClick={closeExamModal}>
          <div
            className="modal-card quiz-take-card exam-take-card"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">
                  {examResult ? 'EXAM RESULT' : 'ONLINE EXAM'}
                </span>
                <h2>{examResult ? examResult.title : examTake?.title}</h2>
                {!examResult && examTake && (
                  <p>
                    Attempt #{examTake.attempt_number} · {examTake.questions.length}{' '}
                    questions · {examTake.total_marks} marks
                  </p>
                )}
              </div>
              <div className="exam-header-actions">
                {!examResult && examTake && (
                  <span
                    className={
                      examRemaining !== null && examRemaining <= 60
                        ? 'exam-timer exam-timer-low'
                        : 'exam-timer'
                    }
                  >
                    {formatClock(examRemaining)}
                  </span>
                )}
                <button className="close-button" onClick={closeExamModal} type="button">
                  ×
                </button>
              </div>
            </div>

            {examResult ? (
              <div>
                <div className="quiz-result">
                  {examResult.results_published ? (
                    <>
                      <strong>
                        {examResult.percentage}% ·{' '}
                        {examResult.passed ? 'Passed' : 'Not passed'}
                      </strong>
                      <span>
                        {examResult.correct_answers} of {examResult.total_questions}{' '}
                        correct · {examResult.score} / {examResult.total_marks} marks
                      </span>
                      {examResult.auto_submitted && (
                        <small>Submitted automatically when the timer ended.</small>
                      )}
                    </>
                  ) : (
                    <>
                      <strong>Answers submitted</strong>
                      <span>
                        {examResult.note ??
                          'Results will appear once your institute publishes them.'}
                      </span>
                    </>
                  )}
                </div>
                <div className="modal-actions">
                  <button className="primary-button" onClick={closeExamModal} type="button">
                    Done
                  </button>
                </div>
              </div>
            ) : examTake ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  if (
                    window.confirm(
                      'Submit this exam now? You cannot change your answers after submitting.',
                    )
                  ) {
                    void submitExam(false)
                  }
                }}
              >
                {examTake.instructions && (
                  <p className="lms-instructions">{examTake.instructions}</p>
                )}
                {examTake.questions.map((question) => (
                  <div className="quiz-question" key={question.id}>
                    <p>
                      <strong>Q{question.position}.</strong> {question.question_text}{' '}
                      <small className="muted">({question.marks} marks)</small>
                    </p>
                    <div className="quiz-options">
                      {examOptionFields.map(([key, field]) => (
                        <label key={key}>
                          <input
                            checked={examAnswers[question.id] === key}
                            name={`exam-question-${question.id}`}
                            onChange={() => void selectExamAnswer(question.id, key)}
                            type="radio"
                          />
                          <span>
                            <strong>{key}.</strong> {question[field]}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                <div className="exam-save-note">
                  Answers save automatically as you select them. The exam submits
                  itself when the timer reaches 00:00.
                </div>
                <div className="modal-actions">
                  <button
                    className="secondary-button"
                    onClick={closeExamModal}
                    type="button"
                  >
                    Close (attempt stays open)
                  </button>
                  <button
                    className="primary-button"
                    disabled={examBusy === 'exam-submit'}
                    type="submit"
                  >
                    {examBusy === 'exam-submit' ? 'Submitting…' : 'Submit exam'}
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        </div>
      )}

      {paymentMessage && <div className="success-message">{paymentMessage}</div>}

      {paymentInstallment && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setPaymentInstallment(null)
        }}>
          <div className="modal-card" role="dialog" aria-modal="true">
            <div className="modal-header">
              <div>
                <span className="eyebrow">FEE PAYMENT · UPI</span>
                <h2>Pay your fees</h2>
              </div>
              <button className="close-button" onClick={() => setPaymentInstallment(null)} type="button">×</button>
            </div>
            <p>
              Pay <strong>₹{Number(paymentInstallment.installment.claimable_amount).toLocaleString('en-IN')}</strong> to{' '}
              {paymentInstallment.enrollment.upi_payee_name || 'the institute'} using UPI, then submit the transaction reference.
            </p>
            {paymentInstallment.enrollment.upi_qr_code_url ? (
              <AuthImage
                alt="Institution UPI QR code"
                className="payment-qr-image"
                path={paymentInstallment.enrollment.upi_qr_code_url}
              />
            ) : (
              <div className="table-state">
                The institution has not configured a payment QR code. Use the UPI ID below to pay manually.
              </div>
            )}
            {paymentInstallment.enrollment.upi_id && <p><strong>UPI ID:</strong> {paymentInstallment.enrollment.upi_id}</p>}
            {paymentError && <div className="inline-error">{paymentError}</div>}
            <form onSubmit={submitFeeClaim} className="settings-form">
              <div className="field">
                <label htmlFor="payment-amount">Amount to pay</label>
                <input id="payment-amount" type="number" min="1" max={paymentInstallment.installment.claimable_amount} step="0.01" value={paymentAmount} onChange={(event) => setPaymentAmount(event.target.value)} required />
              </div>
              <div className="field">
                <label htmlFor="payment-reference">UPI transaction reference</label>
                <input id="payment-reference" value={paymentReference} onChange={(event) => setPaymentReference(event.target.value)} minLength={6} maxLength={60} required />
              </div>
              <div className="field">
                <label htmlFor="payment-date">Payment date</label>
                <input id="payment-date" type="date" value={paymentDate} max={new Date().toISOString().slice(0, 10)} onChange={(event) => setPaymentDate(event.target.value)} required />
              </div>
              <div className="modal-actions">
                <button className="secondary-button" onClick={() => setPaymentInstallment(null)} type="button">Cancel</button>
                <button className="primary-button" disabled={paymentSubmitting || (!paymentInstallment.enrollment.upi_qr_code_url && !paymentInstallment.enrollment.upi_id)} type="submit">{paymentSubmitting ? 'Submitting…' : 'Submit payment for verification'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {preview && (
        <CertificatePreviewModal
          key={preview.id}
          certificate={preview}
          onClose={() => setPreview(null)}
        />
      )}
    </main>
  )
}

export default StudentPortalPage
