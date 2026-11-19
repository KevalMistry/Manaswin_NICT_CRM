import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import api from '../services/api'
import { apiErrorMessage } from '../utils/apiErrors'
import { getStoredUser } from '../utils/auth'

type CourseSummary = {
  id: number
  name: string
  code: string
  duration_months: number
  is_active: boolean
  module_count: number
  lesson_count: number
  assignment_count: number
  quiz_count: number
  enrollment_count: number
}

type Lesson = {
  id: number
  module_id: number
  title: string
  description: string | null
  lesson_type: string
  content_url: string | null
  content_text: string | null
  duration_minutes: number
  position: number
  is_published: boolean
}

type Module = {
  id: number
  course_id: number
  title: string
  description: string | null
  position: number
  is_published: boolean
  lessons: Lesson[]
}

type Submission = {
  id: number
  enrollment_id: number
  student_name: string
  student_code: string
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

type Assignment = {
  id: number
  course_id: number
  module_id: number | null
  title: string
  description: string | null
  instructions: string | null
  due_date: string | null
  max_marks: string
  attachment_url: string | null
  is_published: boolean
  submissions: Submission[]
}

type QuizQuestion = {
  id: number
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_option: string
  marks: string
  position: number
}

type QuizAttempt = {
  id: number
  enrollment_id: number
  student_name: string | null
  score: string
  total_marks: string
  percentage: number
  passed: boolean
  submitted_at: string | null
}

type Quiz = {
  id: number
  course_id: number
  module_id: number | null
  title: string
  description: string | null
  quiz_type: string
  pass_percentage: number
  time_limit_minutes: number | null
  is_published: boolean
  questions: QuizQuestion[]
  attempts: QuizAttempt[]
}

type CourseContent = {
  course_id: number
  course_name: string
  course_code: string
  duration_months: number
  modules: Module[]
  assignments: Assignment[]
  quizzes: Quiz[]
}

type ProgressRow = {
  enrollment_id: number
  student_id: number
  student_name: string
  student_code: string
  batch_name: string
  status: string
  total_lessons: number
  completed_lessons: number
  progress_percentage: number
  time_spent_seconds: number
  assignments_submitted: number
  assignments_graded: number
  average_quiz_percentage: number | null
}

type Progress = {
  course_id: number
  course_name: string
  total_lessons: number
  rows: ProgressRow[]
}

type ModuleForm = { title: string; description: string; position: string; is_published: boolean }
type LessonForm = {
  title: string
  description: string
  lesson_type: string
  content_url: string
  content_text: string
  duration_minutes: string
  position: string
  is_published: boolean
}
type AssignmentForm = {
  module_id: string
  title: string
  description: string
  instructions: string
  due_date: string
  max_marks: string
  is_published: boolean
}
type QuizForm = {
  module_id: string
  title: string
  description: string
  quiz_type: string
  pass_percentage: string
  time_limit_minutes: string
  is_published: boolean
}
type QuestionForm = {
  question_text: string
  option_a: string
  option_b: string
  option_c: string
  option_d: string
  correct_option: string
  marks: string
}

const emptyModule: ModuleForm = { title: '', description: '', position: '0', is_published: true }
const emptyLesson: LessonForm = {
  title: '',
  description: '',
  lesson_type: 'video',
  content_url: '',
  content_text: '',
  duration_minutes: '0',
  position: '0',
  is_published: true,
}
const emptyAssignment: AssignmentForm = {
  module_id: '',
  title: '',
  description: '',
  instructions: '',
  due_date: '',
  max_marks: '100',
  is_published: true,
}
const emptyQuiz: QuizForm = {
  module_id: '',
  title: '',
  description: '',
  quiz_type: 'quiz',
  pass_percentage: '40',
  time_limit_minutes: '',
  is_published: true,
}
const emptyQuestion: QuestionForm = {
  question_text: '',
  option_a: '',
  option_b: '',
  option_c: '',
  option_d: '',
  correct_option: 'A',
  marks: '1',
}

function LmsPage() {
  const [courses, setCourses] = useState<CourseSummary[]>([])
  const [courseId, setCourseId] = useState('')
  const [content, setContent] = useState<CourseContent | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [tab, setTab] = useState<'content' | 'progress'>('content')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [moduleForm, setModuleForm] = useState<ModuleForm>(emptyModule)
  const [showModuleForm, setShowModuleForm] = useState(false)
  const [lessonModuleId, setLessonModuleId] = useState<number | null>(null)
  const [lessonForm, setLessonForm] = useState<LessonForm>(emptyLesson)
  const [lessonFile, setLessonFile] = useState<File | null>(null)
  const [showAssignmentForm, setShowAssignmentForm] = useState(false)
  const [assignmentForm, setAssignmentForm] = useState<AssignmentForm>(emptyAssignment)
  const [showQuizForm, setShowQuizForm] = useState(false)
  const [quizForm, setQuizForm] = useState<QuizForm>(emptyQuiz)
  const [questionQuizId, setQuestionQuizId] = useState<number | null>(null)
  const [questionForm, setQuestionForm] = useState<QuestionForm>(emptyQuestion)
  const [gradingId, setGradingId] = useState<number | null>(null)
  const [gradeForm, setGradeForm] = useState({ marks: '', feedback: '' })

  const roleName = getStoredUser()?.role_name ?? ''
  const canManage = ['Super Admin', 'Branch Admin', 'Faculty', 'Staff'].includes(roleName)

  const selectedCourse = useMemo(
    () => courses.find((course) => String(course.id) === courseId) ?? null,
    [courses, courseId],
  )

  const loadCourses = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const { data } = await api.get<CourseSummary[]>('/api/lms/courses', {
        params: { include_inactive: true },
      })
      setCourses(data)
      setCourseId((current) => current || (data[0] ? String(data[0].id) : ''))
      if (!data.length) setIsLoading(false)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load courses for the LMS.'))
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCourses(), 0)
    return () => window.clearTimeout(timer)
  }, [loadCourses])

  const loadContent = useCallback(async () => {
    if (!courseId) return
    setIsLoading(true)
    setError('')
    try {
      const { data } = await api.get<CourseContent>(`/api/lms/courses/${courseId}/content`)
      setContent(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load course content.'))
    } finally {
      setIsLoading(false)
    }
  }, [courseId])

  const loadProgress = useCallback(async () => {
    if (!courseId) return
    try {
      const { data } = await api.get<Progress>(`/api/lms/courses/${courseId}/progress`)
      setProgress(data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Unable to load learner progress.'))
    }
  }, [courseId])

  useEffect(() => {
    if (!courseId) return
    const timer = window.setTimeout(() => {
      setContent(null)
      setProgress(null)
      void loadContent()
      void loadProgress()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [courseId, loadContent, loadProgress])

  async function run(action: () => Promise<unknown>, success: string) {
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      await action()
      setMessage(success)
      await loadContent()
      await loadProgress()
      await loadCourses()
      return true
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'That change could not be saved.'))
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function createModule(event: FormEvent) {
    event.preventDefault()
    if (!courseId) return
    const ok = await run(
      () =>
        api.post('/api/lms/modules', {
          course_id: Number(courseId),
          title: moduleForm.title,
          description: moduleForm.description || null,
          position: Number(moduleForm.position || 0),
          is_published: moduleForm.is_published,
        }),
      'Module added.',
    )
    if (ok) {
      setModuleForm(emptyModule)
      setShowModuleForm(false)
    }
  }

  async function createLesson(event: FormEvent, moduleId: number) {
    event.preventDefault()
    if (!lessonForm.title.trim()) return
    const ok = await run(
      async () => {
        const { data } = await api.post<Lesson>(`/api/lms/modules/${moduleId}/lessons`, {
          title: lessonForm.title,
          description: lessonForm.description || null,
          lesson_type: lessonForm.lesson_type,
          content_url: lessonForm.content_url || null,
          content_text: lessonForm.content_text || null,
          duration_minutes: Number(lessonForm.duration_minutes || 0),
          position: Number(lessonForm.position || 0),
          is_published: lessonForm.is_published,
        })
        if (lessonFile) {
          const body = new FormData()
          body.append('file', lessonFile)
          await api.post(`/api/lms/lessons/${data.id}/file`, body, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        }
      },
      'Lesson added.',
    )
    if (ok) {
      setLessonForm(emptyLesson)
      setLessonFile(null)
      setLessonModuleId(null)
    }
  }

  async function createAssignment(event: FormEvent) {
    event.preventDefault()
    if (!courseId) return
    const ok = await run(
      () =>
        api.post('/api/lms/assignments', {
          course_id: Number(courseId),
          module_id: assignmentForm.module_id ? Number(assignmentForm.module_id) : null,
          title: assignmentForm.title,
          description: assignmentForm.description || null,
          instructions: assignmentForm.instructions || null,
          due_date: assignmentForm.due_date || null,
          max_marks: Number(assignmentForm.max_marks || 100),
          is_published: assignmentForm.is_published,
        }),
      'Assignment created.',
    )
    if (ok) {
      setAssignmentForm(emptyAssignment)
      setShowAssignmentForm(false)
    }
  }

  async function createQuiz(event: FormEvent) {
    event.preventDefault()
    if (!courseId) return
    const ok = await run(
      () =>
        api.post('/api/lms/quizzes', {
          course_id: Number(courseId),
          module_id: quizForm.module_id ? Number(quizForm.module_id) : null,
          title: quizForm.title,
          description: quizForm.description || null,
          quiz_type: quizForm.quiz_type,
          pass_percentage: Number(quizForm.pass_percentage || 40),
          time_limit_minutes: quizForm.time_limit_minutes
            ? Number(quizForm.time_limit_minutes)
            : null,
          is_published: quizForm.is_published,
          questions: [],
        }),
      'Quiz created. Add its questions next.',
    )
    if (ok) {
      setQuizForm(emptyQuiz)
      setShowQuizForm(false)
    }
  }

  async function addQuestion(event: FormEvent, quizId: number) {
    event.preventDefault()
    const ok = await run(
      () =>
        api.post(`/api/lms/quizzes/${quizId}/questions`, {
          ...questionForm,
          marks: Number(questionForm.marks || 1),
          position: 0,
        }),
      'Question added.',
    )
    if (ok) {
      setQuestionForm(emptyQuestion)
      setQuestionQuizId(null)
    }
  }

  async function gradeSubmission(event: FormEvent, assignment: Assignment, submission: Submission) {
    event.preventDefault()
    const marks = Number(gradeForm.marks)
    if (Number.isNaN(marks) || marks < 0 || marks > Number(assignment.max_marks)) {
      setError(`Marks must be between 0 and ${assignment.max_marks}.`)
      return
    }
    const ok = await run(
      () =>
        api.post(`/api/lms/assignments/${assignment.id}/submissions/${submission.id}/grade`, {
          marks,
          feedback: gradeForm.feedback || null,
        }),
      `Graded ${submission.student_name}.`,
    )
    if (ok) {
      setGradingId(null)
      setGradeForm({ marks: '', feedback: '' })
    }
  }

  async function remove(path: string, label: string) {
    if (!window.confirm(`Delete this ${label}?`)) return
    await run(() => api.delete(path), `${label[0].toUpperCase()}${label.slice(1)} deleted.`)
  }

  const moduleOptions = content?.modules ?? []

  return (
    <div>
      <div className="page-heading module-heading">
        <div>
          <span className="eyebrow">LEARNING</span>
          <h1>Courses &amp; Learning</h1>
          <p>
            Publish modules, lessons, assignments and MCQ quizzes. Students see
            this content in their portal and progress feeds certificate
            eligibility.
          </p>
        </div>
        <div className="heading-actions">
          {selectedCourse && (
            <span className="result-count">
              {selectedCourse.enrollment_count} active learners ·{' '}
              {selectedCourse.duration_months} month course
            </span>
          )}
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <div className="success-message">{message}</div>}

      <section className="module-toolbar">
        <div className="toolbar-controls">
          <div className="field">
            <label htmlFor="lms-course">Course</label>
            <select
              id="lms-course"
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
        {selectedCourse && (
          <span className="result-count">
            {selectedCourse.module_count} modules · {selectedCourse.lesson_count} lessons ·{' '}
            {selectedCourse.assignment_count} assignments · {selectedCourse.quiz_count} quizzes
          </span>
        )}
      </section>

      <nav className="module-tabs" aria-label="LMS sections">
        <button
          className={tab === 'content' ? 'active-tab' : ''}
          onClick={() => setTab('content')}
          type="button"
        >
          Course content
        </button>
        <button
          className={tab === 'progress' ? 'active-tab' : ''}
          onClick={() => setTab('progress')}
          type="button"
        >
          Learner progress <span>{progress?.rows.length ?? 0}</span>
        </button>
      </nav>

      {isLoading && !content && <div className="table-state">Loading course content…</div>}

      {!courses.length && !isLoading && (
        <div className="data-panel table-state">
          <strong>No courses available</strong>
          <p>Create a course first, then return here to build its learning content.</p>
        </div>
      )}

      {tab === 'content' && content && (
        <>
          {canManage && (
            <section className="module-toolbar">
              <div className="toolbar-controls">
                <button
                  className="primary-button"
                  onClick={() => {
                    setShowModuleForm((open) => !open)
                    setShowAssignmentForm(false)
                    setShowQuizForm(false)
                  }}
                  type="button"
                >
                  + Module
                </button>
                <button
                  className="secondary-button"
                  onClick={() => {
                    setShowAssignmentForm((open) => !open)
                    setShowModuleForm(false)
                    setShowQuizForm(false)
                  }}
                  type="button"
                >
                  + Assignment
                </button>
                <button
                  className="secondary-button"
                  onClick={() => {
                    setShowQuizForm((open) => !open)
                    setShowModuleForm(false)
                    setShowAssignmentForm(false)
                  }}
                  type="button"
                >
                  + Quiz
                </button>
              </div>
              <span className="result-count">Changes publish to students immediately.</span>
            </section>
          )}

          {showModuleForm && (
            <section className="data-panel settings-card lms-form-panel">
              <div className="section-title">
                <div>
                  <span className="eyebrow">NEW MODULE</span>
                  <h2>Add a module</h2>
                </div>
              </div>
              <form className="form-grid" onSubmit={(event) => void createModule(event)}>
                <div className="field">
                  <label htmlFor="module-title">Title</label>
                  <input
                    id="module-title"
                    required
                    value={moduleForm.title}
                    onChange={(event) => setModuleForm({ ...moduleForm, title: event.target.value })}
                    placeholder="e.g. Python Foundations"
                  />
                </div>
                <div className="field">
                  <label htmlFor="module-position">Position</label>
                  <input
                    id="module-position"
                    type="number"
                    min="0"
                    value={moduleForm.position}
                    onChange={(event) =>
                      setModuleForm({ ...moduleForm, position: event.target.value })
                    }
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="module-description">Description</label>
                  <textarea
                    id="module-description"
                    rows={2}
                    value={moduleForm.description}
                    onChange={(event) =>
                      setModuleForm({ ...moduleForm, description: event.target.value })
                    }
                  />
                </div>
                <div className="full-field modal-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setShowModuleForm(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button className="primary-button" disabled={isSaving} type="submit">
                    {isSaving ? 'Saving…' : 'Add module'}
                  </button>
                </div>
              </form>
            </section>
          )}

          {showAssignmentForm && (
            <section className="data-panel settings-card lms-form-panel">
              <div className="section-title">
                <div>
                  <span className="eyebrow">NEW ASSIGNMENT</span>
                  <h2>Create an assignment</h2>
                </div>
              </div>
              <form className="form-grid" onSubmit={(event) => void createAssignment(event)}>
                <div className="field">
                  <label htmlFor="assignment-title">Title</label>
                  <input
                    id="assignment-title"
                    required
                    value={assignmentForm.title}
                    onChange={(event) =>
                      setAssignmentForm({ ...assignmentForm, title: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="assignment-module">Module</label>
                  <select
                    id="assignment-module"
                    value={assignmentForm.module_id}
                    onChange={(event) =>
                      setAssignmentForm({ ...assignmentForm, module_id: event.target.value })
                    }
                  >
                    <option value="">Course level</option>
                    {moduleOptions.map((module) => (
                      <option key={module.id} value={module.id}>
                        {module.title}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="assignment-due">Due date</label>
                  <input
                    id="assignment-due"
                    type="date"
                    value={assignmentForm.due_date}
                    onChange={(event) =>
                      setAssignmentForm({ ...assignmentForm, due_date: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="assignment-marks">Maximum marks</label>
                  <input
                    id="assignment-marks"
                    type="number"
                    min="1"
                    value={assignmentForm.max_marks}
                    onChange={(event) =>
                      setAssignmentForm({ ...assignmentForm, max_marks: event.target.value })
                    }
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="assignment-description">Description</label>
                  <textarea
                    id="assignment-description"
                    rows={2}
                    value={assignmentForm.description}
                    onChange={(event) =>
                      setAssignmentForm({ ...assignmentForm, description: event.target.value })
                    }
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="assignment-instructions">Instructions</label>
                  <textarea
                    id="assignment-instructions"
                    rows={3}
                    value={assignmentForm.instructions}
                    onChange={(event) =>
                      setAssignmentForm({ ...assignmentForm, instructions: event.target.value })
                    }
                  />
                </div>
                <div className="full-field modal-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setShowAssignmentForm(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button className="primary-button" disabled={isSaving} type="submit">
                    {isSaving ? 'Saving…' : 'Create assignment'}
                  </button>
                </div>
              </form>
            </section>
          )}

          {showQuizForm && (
            <section className="data-panel settings-card lms-form-panel">
              <div className="section-title">
                <div>
                  <span className="eyebrow">NEW QUIZ</span>
                  <h2>Create a quiz</h2>
                </div>
              </div>
              <form className="form-grid" onSubmit={(event) => void createQuiz(event)}>
                <div className="field">
                  <label htmlFor="quiz-title">Title</label>
                  <input
                    id="quiz-title"
                    required
                    value={quizForm.title}
                    onChange={(event) => setQuizForm({ ...quizForm, title: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="quiz-module">Module</label>
                  <select
                    id="quiz-module"
                    value={quizForm.module_id}
                    onChange={(event) =>
                      setQuizForm({ ...quizForm, module_id: event.target.value })
                    }
                  >
                    <option value="">Course level</option>
                    {moduleOptions.map((module) => (
                      <option key={module.id} value={module.id}>
                        {module.title}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="quiz-type">Type</label>
                  <select
                    id="quiz-type"
                    value={quizForm.quiz_type}
                    onChange={(event) =>
                      setQuizForm({ ...quizForm, quiz_type: event.target.value })
                    }
                  >
                    <option value="quiz">Quiz</option>
                    <option value="mock_test">Mock test</option>
                    <option value="practice">Practice</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="quiz-pass">Pass percentage</label>
                  <input
                    id="quiz-pass"
                    type="number"
                    min="0"
                    max="100"
                    value={quizForm.pass_percentage}
                    onChange={(event) =>
                      setQuizForm({ ...quizForm, pass_percentage: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="quiz-time">Time limit (minutes)</label>
                  <input
                    id="quiz-time"
                    type="number"
                    min="1"
                    value={quizForm.time_limit_minutes}
                    onChange={(event) =>
                      setQuizForm({ ...quizForm, time_limit_minutes: event.target.value })
                    }
                    placeholder="No limit"
                  />
                </div>
                <div className="field full-field">
                  <label htmlFor="quiz-description">Description</label>
                  <textarea
                    id="quiz-description"
                    rows={2}
                    value={quizForm.description}
                    onChange={(event) =>
                      setQuizForm({ ...quizForm, description: event.target.value })
                    }
                  />
                </div>
                <div className="full-field modal-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setShowQuizForm(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button className="primary-button" disabled={isSaving} type="submit">
                    {isSaving ? 'Saving…' : 'Create quiz'}
                  </button>
                </div>
              </form>
            </section>
          )}

          <section className="data-panel">
            <div className="section-title">
              <div>
                <span className="eyebrow">CURRICULUM</span>
                <h2>{content.course_name} modules</h2>
              </div>
              <span className="result-count">{content.modules.length} modules</span>
            </div>
            <div className="lms-module-list">
              {content.modules.map((module) => (
                <article className="lms-module" key={module.id}>
                  <header>
                    <div>
                      <strong>{module.title}</strong>
                      {module.description && <p>{module.description}</p>}
                    </div>
                    {canManage && (
                      <div className="row-actions">
                        <button
                          onClick={() => {
                            setLessonModuleId(module.id)
                            setLessonForm(emptyLesson)
                          }}
                          type="button"
                        >
                          + Lesson
                        </button>
                        <button
                          className="danger-action"
                          onClick={() => void remove(`/api/lms/modules/${module.id}`, 'module')}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </header>
                  <ul className="lms-lesson-list">
                    {module.lessons.map((lesson) => (
                      <li key={lesson.id}>
                        <div>
                          <strong>{lesson.title}</strong>
                          <small>
                            {lesson.lesson_type} · {lesson.duration_minutes} min
                            {lesson.content_url ? ` · ${lesson.content_url}` : ''}
                          </small>
                        </div>
                        {canManage && (
                          <div className="row-actions">
                            <button
                              className="danger-action"
                              onClick={() => void remove(`/api/lms/lessons/${lesson.id}`, 'lesson')}
                              type="button"
                            >
                              Remove
                            </button>
                          </div>
                        )}
                      </li>
                    ))}
                    {!module.lessons.length && (
                      <li className="muted">No lessons yet.</li>
                    )}
                  </ul>
                  {lessonModuleId === module.id && (
                    <form
                      className="form-grid lms-inline-form"
                      onSubmit={(event) => void createLesson(event, module.id)}
                    >
                      <div className="field">
                        <label>Lesson title</label>
                        <input
                          required
                          value={lessonForm.title}
                          onChange={(event) =>
                            setLessonForm({ ...lessonForm, title: event.target.value })
                          }
                        />
                      </div>
                      <div className="field">
                        <label>Type</label>
                        <select
                          value={lessonForm.lesson_type}
                          onChange={(event) =>
                            setLessonForm({ ...lessonForm, lesson_type: event.target.value })
                          }
                        >
                          {['video', 'pdf', 'ppt', 'file', 'link', 'text'].map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="field">
                        <label>Content URL</label>
                        <input
                          value={lessonForm.content_url}
                          onChange={(event) =>
                            setLessonForm({ ...lessonForm, content_url: event.target.value })
                          }
                          placeholder="https://…"
                        />
                      </div>
                      <div className="field">
                        <label>PDF or JPEG file</label>
                        <input
                          type="file"
                          accept="application/pdf,image/jpeg"
                          onChange={(event) => setLessonFile(event.target.files?.[0] ?? null)}
                        />
                        <small className="field-hint">Upload a course handout or image (up to 10 MB).</small>
                      </div>
                      <div className="field">
                        <label>Duration (minutes)</label>
                        <input
                          type="number"
                          min="0"
                          value={lessonForm.duration_minutes}
                          onChange={(event) =>
                            setLessonForm({ ...lessonForm, duration_minutes: event.target.value })
                          }
                        />
                      </div>
                      <div className="field full-field">
                        <label>Notes / text content</label>
                        <textarea
                          rows={3}
                          value={lessonForm.content_text}
                          onChange={(event) =>
                            setLessonForm({ ...lessonForm, content_text: event.target.value })
                          }
                        />
                      </div>
                      <div className="full-field modal-actions">
                        <button
                          className="secondary-button"
                          onClick={() => setLessonModuleId(null)}
                          type="button"
                        >
                          Cancel
                        </button>
                        <button className="primary-button" disabled={isSaving} type="submit">
                          {isSaving ? 'Saving…' : 'Add lesson'}
                        </button>
                      </div>
                    </form>
                  )}
                </article>
              ))}
              {!content.modules.length && (
                <div className="table-state">
                  <strong>No modules yet</strong>
                  <p>Add the first module to start building this course.</p>
                </div>
              )}
            </div>
          </section>

          <section className="data-panel lms-section-gap">
            <div className="section-title">
              <div>
                <span className="eyebrow">ASSIGNMENTS</span>
                <h2>Submissions and grading</h2>
              </div>
              <span className="result-count">
                {content.assignments.reduce(
                  (sum, assignment) => sum + assignment.submissions.length,
                  0,
                )}{' '}
                submissions
              </span>
            </div>
            <div className="lms-module-list">
              {content.assignments.map((assignment) => (
                <article className="lms-module" key={assignment.id}>
                  <header>
                    <div>
                      <strong>{assignment.title}</strong>
                      <p>
                        {assignment.max_marks} marks
                        {assignment.due_date ? ` · due ${assignment.due_date}` : ''}
                      </p>
                    </div>
                    {canManage && (
                      <div className="row-actions">
                        <button
                          className="danger-action"
                          onClick={() =>
                            void remove(`/api/lms/assignments/${assignment.id}`, 'assignment')
                          }
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </header>
                  {assignment.instructions && (
                    <p className="lms-instructions">{assignment.instructions}</p>
                  )}
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Student</th>
                          <th>Submitted</th>
                          <th>Status</th>
                          <th>Marks</th>
                          <th>Feedback</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {assignment.submissions.map((submission) => (
                          <tr key={submission.id}>
                            <td>
                              <strong>{submission.student_name}</strong>
                              <small className="muted-block">{submission.student_code}</small>
                            </td>
                            <td>{new Date(submission.submitted_at).toLocaleString()}</td>
                            <td>{submission.status}</td>
                            <td>
                              {submission.marks ?? '—'}
                              {submission.grade ? ` · ${submission.grade}` : ''}
                            </td>
                            <td>{submission.feedback ?? '—'}</td>
                            <td>
                              {submission.status !== 'graded' && (
                                <button
                                  className="row-link"
                                  onClick={() => {
                                    setGradingId(submission.id)
                                    setGradeForm({ marks: '', feedback: '' })
                                  }}
                                  type="button"
                                >
                                  Grade
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!assignment.submissions.length && (
                      <div className="table-state">No submissions yet.</div>
                    )}
                  </div>
                  {gradingId !== null &&
                    assignment.submissions.some((submission) => submission.id === gradingId) && (
                      <form
                        className="inline-form-row lms-grade-form"
                        onSubmit={(event) => {
                          const submission = assignment.submissions.find(
                            (item) => item.id === gradingId,
                          )
                          if (submission) void gradeSubmission(event, assignment, submission)
                        }}
                      >
                        <div className="field">
                          <label>Marks</label>
                          <input
                            type="number"
                            min="0"
                            max={Number(assignment.max_marks)}
                            required
                            value={gradeForm.marks}
                            onChange={(event) =>
                              setGradeForm({ ...gradeForm, marks: event.target.value })
                            }
                          />
                        </div>
                        <div className="field">
                          <label>Feedback</label>
                          <input
                            value={gradeForm.feedback}
                            onChange={(event) =>
                              setGradeForm({ ...gradeForm, feedback: event.target.value })
                            }
                          />
                        </div>
                        <button className="primary-button" disabled={isSaving} type="submit">
                          {isSaving ? 'Saving…' : 'Save grade'}
                        </button>
                        <button
                          className="secondary-button"
                          onClick={() => setGradingId(null)}
                          type="button"
                        >
                          Cancel
                        </button>
                      </form>
                    )}
                </article>
              ))}
              {!content.assignments.length && (
                <div className="table-state">
                  <strong>No assignments yet</strong>
                  <p>Assignments are checked before a certificate is issued.</p>
                </div>
              )}
            </div>
          </section>

          <section className="data-panel lms-section-gap">
            <div className="section-title">
              <div>
                <span className="eyebrow">QUIZZES</span>
                <h2>MCQ quizzes and attempts</h2>
              </div>
              <span className="result-count">{content.quizzes.length} quizzes</span>
            </div>
            <div className="lms-module-list">
              {content.quizzes.map((quiz) => (
                <article className="lms-module" key={quiz.id}>
                  <header>
                    <div>
                      <strong>{quiz.title}</strong>
                      <p>
                        {quiz.quiz_type} · pass {quiz.pass_percentage}% ·{' '}
                        {quiz.questions.length} questions
                        {quiz.time_limit_minutes ? ` · ${quiz.time_limit_minutes} min` : ''}
                      </p>
                    </div>
                    {canManage && (
                      <div className="row-actions">
                        <button
                          onClick={() => {
                            setQuestionQuizId(quiz.id)
                            setQuestionForm(emptyQuestion)
                          }}
                          type="button"
                        >
                          + Question
                        </button>
                        <button
                          className="danger-action"
                          onClick={() => void remove(`/api/lms/quizzes/${quiz.id}`, 'quiz')}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </header>
                  <ol className="lms-question-list">
                    {quiz.questions.map((question) => (
                      <li key={question.id}>
                        <div>
                          <span>{question.question_text}</span>
                          <small>
                            A) {question.option_a} · B) {question.option_b} · C) {question.option_c} · D){' '}
                            {question.option_d}
                          </small>
                          <small className="muted-block">
                            Correct: {question.correct_option} · {question.marks} marks
                          </small>
                        </div>
                        {canManage && (
                          <button
                            className="row-link danger-action"
                            onClick={() =>
                              void remove(
                                `/api/lms/quizzes/${quiz.id}/questions/${question.id}`,
                                'question',
                              )
                            }
                            type="button"
                          >
                            Remove
                          </button>
                        )}
                      </li>
                    ))}
                    {!quiz.questions.length && (
                      <li className="muted">No questions added yet.</li>
                    )}
                  </ol>
                  {questionQuizId === quiz.id && (
                    <form
                      className="form-grid lms-inline-form"
                      onSubmit={(event) => void addQuestion(event, quiz.id)}
                    >
                      <div className="field full-field">
                        <label>Question</label>
                        <textarea
                          required
                          rows={2}
                          value={questionForm.question_text}
                          onChange={(event) =>
                            setQuestionForm({ ...questionForm, question_text: event.target.value })
                          }
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
                            value={questionForm[field]}
                            onChange={(event) =>
                              setQuestionForm({
                                ...questionForm,
                                [field]: event.target.value,
                              })
                            }
                          />
                        </div>
                      ))}
                      <div className="field">
                        <label>Correct option</label>
                        <select
                          value={questionForm.correct_option}
                          onChange={(event) =>
                            setQuestionForm({ ...questionForm, correct_option: event.target.value })
                          }
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
                          value={questionForm.marks}
                          onChange={(event) =>
                            setQuestionForm({ ...questionForm, marks: event.target.value })
                          }
                        />
                      </div>
                      <div className="full-field modal-actions">
                        <button
                          className="secondary-button"
                          onClick={() => setQuestionQuizId(null)}
                          type="button"
                        >
                          Cancel
                        </button>
                        <button className="primary-button" disabled={isSaving} type="submit">
                          {isSaving ? 'Saving…' : 'Add question'}
                        </button>
                      </div>
                    </form>
                  )}
                  {quiz.attempts.length > 0 && (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Student</th>
                            <th>Score</th>
                            <th>Percentage</th>
                            <th>Result</th>
                            <th>Submitted</th>
                          </tr>
                        </thead>
                        <tbody>
                          {quiz.attempts.map((attempt) => (
                            <tr key={attempt.id}>
                              <td>{attempt.student_name ?? `Enrollment #${attempt.enrollment_id}`}</td>
                              <td>
                                {attempt.score} / {attempt.total_marks}
                              </td>
                              <td>{attempt.percentage}%</td>
                              <td>{attempt.passed ? 'Passed' : 'Not passed'}</td>
                              <td>
                                {attempt.submitted_at
                                  ? new Date(attempt.submitted_at).toLocaleString()
                                  : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </article>
              ))}
              {!content.quizzes.length && (
                <div className="table-state">
                  <strong>No quizzes yet</strong>
                  <p>Add an MCQ quiz to auto-grade student practice tests.</p>
                </div>
              )}
            </div>
          </section>
        </>
      )}

      {tab === 'progress' && (
        <section className="data-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">LEARNER PROGRESS</span>
              <h2>{progress?.course_name ?? 'Course'} progress</h2>
            </div>
            <span className="result-count">{progress?.total_lessons ?? 0} lessons published</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Batch</th>
                  <th>Lessons</th>
                  <th>Progress</th>
                  <th>Time spent</th>
                  <th>Assignments</th>
                  <th>Quiz average</th>
                  <th>Enrollment</th>
                </tr>
              </thead>
              <tbody>
                {(progress?.rows ?? []).map((row) => (
                  <tr key={row.enrollment_id}>
                    <td>
                      <strong>{row.student_name}</strong>
                      <small className="muted-block">{row.student_code}</small>
                    </td>
                    <td>{row.batch_name}</td>
                    <td>
                      {row.completed_lessons} / {row.total_lessons}
                    </td>
                    <td>
                      <div className="lms-progress-cell">
                        <div className="lms-progress-track">
                          <span style={{ width: `${Math.min(row.progress_percentage, 100)}%` }} />
                        </div>
                        <small>{row.progress_percentage}%</small>
                      </div>
                    </td>
                    <td>{Math.round(row.time_spent_seconds / 60)} min</td>
                    <td>
                      {row.assignments_submitted} submitted · {row.assignments_graded} graded
                    </td>
                    <td>
                      {row.average_quiz_percentage === null
                        ? '—'
                        : `${row.average_quiz_percentage}%`}
                    </td>
                    <td>
                      <span className="status-pill active-status">
                        <i />
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!progress?.rows.length && (
              <div className="table-state">
                <strong>No active learners</strong>
                <p>Students appear here once they are enrolled in this course.</p>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  )
}

export default LmsPage
