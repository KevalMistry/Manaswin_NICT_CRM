import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import axios from 'axios'
import api from '../services/api'
import { todayInputValue } from '../utils/date'

type Subject = { id: number; name: string; max_marks: number; pass_marks: number }
type Exam = { id: number; name: string; batch_id: number; exam_date: string; is_published: boolean; subjects: Subject[] }
type Batch = { id: number; name: string; code: string; course_id: number; is_active: boolean }
type Enrollment = { id: number; student_id: number; batch_id: number; status: string }
type Student = { id: number; full_name: string; student_code: string }
type Result = { enrollment_id: number; total_obtained: number; total_maximum: number; percentage: number; results: { examination: string; subject: string; marks_obtained: number; max_marks: number; grade: string; remarks: string | null }[] }

function errorMessage(value: unknown, fallback: string) {
  if (axios.isAxiosError(value) && typeof value.response?.data?.detail === 'string') return value.response.data.detail
  return fallback
}

function ExaminationsPage() {
  const [exams, setExams] = useState<Exam[]>([])
  const [batches, setBatches] = useState<Batch[]>([])
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [students, setStudents] = useState<Student[]>([])
  const [examForm, setExamForm] = useState({ name: '', batch_id: '', exam_date: todayInputValue() })
  const [subjects, setSubjects] = useState([{ name: '', max_marks: '100', pass_marks: '40' }])
  const [selectedExam, setSelectedExam] = useState<Exam | null>(null)
  const [marksForm, setMarksForm] = useState({ subject_id: '', enrollment_id: '', marks: '', remarks: '' })
  const [examMarks, setExamMarks] = useState<{ id: number; exam_subject_id: number; enrollment_id: number; marks_obtained: number; grade: string; remarks: string | null }[]>([])
  const [result, setResult] = useState<Result | null>(null)
  const [resultEnrollment, setResultEnrollment] = useState('')
  const [isExamOpen, setIsExamOpen] = useState(false)
  const [isMarksOpen, setIsMarksOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    try {
      const [examResponse, batchResponse, enrollmentResponse, studentResponse] = await Promise.all([
        api.get<Exam[]>('/api/examinations'),
        api.get<Batch[]>('/api/batches'),
        api.get<Enrollment[]>('/api/enrollments'),
        api.get<Student[]>('/api/students'),
      ])
      setExams(examResponse.data)
      setBatches(batchResponse.data)
      setEnrollments(enrollmentResponse.data)
      setStudents(studentResponse.data)
    } catch (requestError) {
      setError(errorMessage(requestError, 'Unable to load examinations.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [])

  async function createExam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/api/examinations', {
        ...examForm,
        batch_id: Number(examForm.batch_id),
        subjects: subjects.map((subject) => ({ ...subject, max_marks: Number(subject.max_marks), pass_marks: Number(subject.pass_marks) })),
      })
      setIsExamOpen(false)
      setExamForm({ name: '', batch_id: '', exam_date: todayInputValue() })
      setSubjects([{ name: '', max_marks: '100', pass_marks: '40' }])
      await load()
    } catch (requestError) {
      setError(errorMessage(requestError, 'Unable to create the examination.'))
    } finally {
      setSaving(false)
    }
  }

  async function publish(exam: Exam) {
    if (!window.confirm(`Publish ${exam.name}? Marks should be checked before publishing.`)) return
    try {
      await api.patch(`/api/examinations/${exam.id}/publish`)
      await load()
    } catch (requestError) {
      setError(errorMessage(requestError, 'Unable to publish this examination.'))
    }
  }

  async function openEnterMarks(exam: Exam) {
    setSelectedExam(exam)
    setMarksForm({ subject_id: '', enrollment_id: '', marks: '', remarks: '' })
    setError('')
    setIsMarksOpen(true)
    try {
      const { data } = await api.get<{ id: number; exam_subject_id: number; enrollment_id: number; marks_obtained: number; grade: string; remarks: string | null }[]>(`/api/examinations/${exam.id}/marks`)
      setExamMarks(data)
    } catch {
      setExamMarks([])
    }
  }

  function onSelectSubject(subjectId: string) {
    const existing = examMarks.find(
      (m) => m.exam_subject_id === Number(subjectId) && m.enrollment_id === Number(marksForm.enrollment_id),
    )
    setMarksForm({
      ...marksForm,
      subject_id: subjectId,
      marks: existing ? String(existing.marks_obtained) : '',
      remarks: existing?.remarks ?? '',
    })
  }

  function onSelectStudent(enrollmentId: string) {
    const existing = examMarks.find(
      (m) => m.exam_subject_id === Number(marksForm.subject_id) && m.enrollment_id === Number(enrollmentId),
    )
    setMarksForm({
      ...marksForm,
      enrollment_id: enrollmentId,
      marks: existing ? String(existing.marks_obtained) : '',
      remarks: existing?.remarks ?? '',
    })
  }

  const currentMark = examMarks.find(
    (m) => m.exam_subject_id === Number(marksForm.subject_id) && m.enrollment_id === Number(marksForm.enrollment_id),
  )

  async function recordMarks(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    try {
      if (currentMark) {
        await api.patch(`/api/examinations/marks/${currentMark.id}`, {
          marks_obtained: Number(marksForm.marks),
          remarks: marksForm.remarks || null,
        })
      } else {
        await api.post('/api/examinations/marks', {
          exam_subject_id: Number(marksForm.subject_id),
          enrollment_id: Number(marksForm.enrollment_id),
          marks_obtained: Number(marksForm.marks),
          remarks: marksForm.remarks || null,
        })
      }
      if (selectedExam) {
        const { data } = await api.get<{ id: number; exam_subject_id: number; enrollment_id: number; marks_obtained: number; grade: string; remarks: string | null }[]>(`/api/examinations/${selectedExam.id}/marks`)
        setExamMarks(data)
      }
      setIsMarksOpen(false)
      setMarksForm({ subject_id: '', enrollment_id: '', marks: '', remarks: '' })
      setError('')
    } catch (requestError) {
      setError(errorMessage(requestError, 'Unable to save these marks.'))
    } finally {
      setSaving(false)
    }
  }

  async function viewResult() {
    if (!resultEnrollment) return
    try {
      const { data } = await api.get<Result>(`/api/examinations/results/${resultEnrollment}`)
      setResult(data)
    } catch (requestError) {
      setError(errorMessage(requestError, 'Unable to load this result.'))
    }
  }

  const batchName = (id: number) => batches.find((batch) => batch.id === id)?.name ?? `Batch #${id}`
  const studentName = (id: number) => students.find((student) => student.id === id)?.full_name ?? `Student #${id}`
  const selectedBatchEnrollments = selectedExam ? enrollments.filter((item) => item.batch_id === selectedExam.batch_id && item.status !== 'cancelled') : []

  return <>
    <div className="page-heading module-heading"><div><span className="eyebrow">ACADEMICS</span><h1>Examinations</h1><p>Create exams, enter marks, publish results, and review performance.</p></div><button className="primary-button" onClick={() => setIsExamOpen(true)} type="button">+ Create examination</button></div>
    {error && <div className="inline-error">{error}</div>}
    <section className="data-panel"><div className="section-title"><div><span className="eyebrow">EXAMINATION LIST</span><h2>Exams and results</h2></div><span className="result-count">{exams.length} examinations</span></div>{loading ? <div className="table-state">Loading examinations…</div> : <div className="table-wrap"><table><thead><tr><th>Examination</th><th>Batch</th><th>Date</th><th>Subjects</th><th>Status</th><th>Actions</th></tr></thead><tbody>{exams.map((exam) => <tr key={exam.id}><td><strong>{exam.name}</strong></td><td>{batchName(exam.batch_id)}</td><td>{exam.exam_date}</td><td>{exam.subjects.length}</td><td><span className={`status-pill ${exam.is_published ? 'active-status' : 'inactive-status'}`}><i />{exam.is_published ? 'Published' : 'Draft'}</span></td><td><div className="row-actions"><button onClick={() => void openEnterMarks(exam)} type="button">Enter marks</button>{!exam.is_published && <button onClick={() => void publish(exam)} type="button">Publish</button>}</div></td></tr>)}</tbody></table>{!exams.length && <div className="table-state">No examinations created yet.</div>}</div>}</section>
    <section className="data-panel responsibility-panel"><div className="section-title"><div><span className="eyebrow">RESULT LOOKUP</span><h2>View published result</h2></div></div><div className="settings-form result-lookup"><div className="field"><label htmlFor="result-enrollment">Student enrollment</label><select id="result-enrollment" value={resultEnrollment} onChange={(event) => setResultEnrollment(event.target.value)}><option value="">Select student</option>{enrollments.filter((item) => item.status !== 'cancelled').map((item) => <option key={item.id} value={item.id}>{studentName(item.student_id)} · {item.id}</option>)}</select></div><button className="primary-button" onClick={() => void viewResult()} type="button">View result</button></div>{result && <div className="result-panel"><strong>{studentName(enrollments.find((item) => item.id === result.enrollment_id)?.student_id ?? 0)}</strong><span>{result.total_obtained} / {result.total_maximum} · {result.percentage}%</span><button className="secondary-button" onClick={() => window.print()} type="button">Print result</button><div className="table-wrap"><table><thead><tr><th>Examination</th><th>Subject</th><th>Marks</th><th>Grade</th><th>Remarks</th></tr></thead><tbody>{result.results.map((row, index) => <tr key={`${row.examination}-${row.subject}-${index}`}><td>{row.examination}</td><td>{row.subject}</td><td>{row.marks_obtained} / {row.max_marks}</td><td>{row.grade}</td><td>{row.remarks || '—'}</td></tr>)}</tbody></table></div></div>}</section>
    {isExamOpen && <div className="modal-backdrop" role="presentation"><div className="modal-card" role="dialog" aria-modal="true"><div className="modal-header"><div><span className="eyebrow">NEW EXAMINATION</span><h2>Create examination</h2></div><button className="close-button" onClick={() => setIsExamOpen(false)} type="button">×</button></div><form className="settings-form" onSubmit={createExam}><div className="field"><label htmlFor="exam-name">Examination name</label><input id="exam-name" value={examForm.name} onChange={(event) => setExamForm({ ...examForm, name: event.target.value })} required /></div><div className="field"><label htmlFor="exam-batch">Batch</label><select id="exam-batch" value={examForm.batch_id} onChange={(event) => setExamForm({ ...examForm, batch_id: event.target.value })} required><option value="">Select batch</option>{batches.filter((batch) => batch.is_active).map((batch) => <option key={batch.id} value={batch.id}>{batch.name} ({batch.code})</option>)}</select></div><div className="field"><label htmlFor="exam-date">Exam date</label><input id="exam-date" type="date" value={examForm.exam_date} onChange={(event) => setExamForm({ ...examForm, exam_date: event.target.value })} required /></div><div className="subject-editor"><div className="section-title"><h2>Subjects</h2><button className="secondary-button" onClick={() => setSubjects([...subjects, { name: '', max_marks: '100', pass_marks: '40' }])} type="button">+ Add subject</button></div>{subjects.map((subject, index) => <div className="form-grid" key={index}><div className="field"><label htmlFor={`subject-name-${index}`}>Subject</label><input id={`subject-name-${index}`} value={subject.name} onChange={(event) => setSubjects(subjects.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} required /></div><div className="field"><label htmlFor={`subject-max-${index}`}>Maximum marks</label><input id={`subject-max-${index}`} type="number" min="1" value={subject.max_marks} onChange={(event) => setSubjects(subjects.map((item, itemIndex) => itemIndex === index ? { ...item, max_marks: event.target.value } : item))} required /></div><div className="field"><label htmlFor={`subject-pass-${index}`}>Pass marks</label><input id={`subject-pass-${index}`} type="number" min="1" value={subject.pass_marks} onChange={(event) => setSubjects(subjects.map((item, itemIndex) => itemIndex === index ? { ...item, pass_marks: event.target.value } : item))} required /></div></div>)}</div><button className="primary-button" disabled={saving} type="submit">{saving ? 'Creating…' : 'Create examination'}</button></form></div></div>}
    {isMarksOpen && selectedExam && <div className="modal-backdrop" role="presentation"><div className="modal-card" role="dialog" aria-modal="true"><div className="modal-header"><div><span className="eyebrow">MARKS · {selectedExam.name}</span><h2>{currentMark ? 'Edit marks' : 'Enter marks'}</h2></div><button className="close-button" onClick={() => setIsMarksOpen(false)} type="button">×</button></div><form className="settings-form" onSubmit={recordMarks}><div className="field"><label htmlFor="marks-subject">Subject</label><select id="marks-subject" value={marksForm.subject_id} onChange={(event) => onSelectSubject(event.target.value)} required><option value="">Select subject</option>{selectedExam.subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name} · max {subject.max_marks}</option>)}</select></div><div className="field"><label htmlFor="marks-student">Student</label><select id="marks-student" value={marksForm.enrollment_id} onChange={(event) => onSelectStudent(event.target.value)} required><option value="">Select student</option>{selectedBatchEnrollments.map((item) => <option key={item.id} value={item.id}>{studentName(item.student_id)}</option>)}</select></div>{currentMark && <div style={{ padding: '8px 12px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '6px', color: '#1e40af', fontSize: '12px' }}>Existing marks entered: <strong>{currentMark.marks_obtained}</strong> (Grade: {currentMark.grade}). You are editing existing marks.</div>}<div className="field"><label htmlFor="marks-value">Marks obtained</label><input id="marks-value" type="number" min="0" step="0.01" value={marksForm.marks} onChange={(event) => setMarksForm({ ...marksForm, marks: event.target.value })} required /></div><div className="field"><label htmlFor="marks-remarks">Remarks</label><input id="marks-remarks" value={marksForm.remarks} onChange={(event) => setMarksForm({ ...marksForm, remarks: event.target.value })} /></div><button className="primary-button" disabled={saving} type="submit">{saving ? 'Saving…' : currentMark ? 'Update marks' : 'Save marks'}</button></form></div></div>}
  </>
}

export default ExaminationsPage
