from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


LESSON_TYPES = ("video", "pdf", "ppt", "file", "link", "text")
QUIZ_TYPES = ("quiz", "mock_test", "practice")


class LessonBase(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    lesson_type: str = Field(default="video", pattern=r"^(video|pdf|ppt|file|link|text)$")
    content_url: str | None = Field(default=None, max_length=500)
    content_text: str | None = None
    duration_minutes: int = Field(default=0, ge=0, le=10000)
    position: int = Field(default=0, ge=0)
    is_published: bool = True


class LessonCreate(LessonBase):
    pass


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    lesson_type: str | None = Field(default=None, pattern=r"^(video|pdf|ppt|file|link|text)$")
    content_url: str | None = Field(default=None, max_length=500)
    content_text: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10000)
    position: int | None = Field(default=None, ge=0)
    is_published: bool | None = None


class LessonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_id: int
    title: str
    description: str | None
    lesson_type: str
    content_url: str | None
    content_text: str | None
    duration_minutes: int
    position: int
    is_published: bool
    created_at: datetime


class ModuleCreate(BaseModel):
    course_id: int
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    position: int = Field(default=0, ge=0)
    is_published: bool = True


class ModuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    position: int | None = Field(default=None, ge=0)
    is_published: bool | None = None


class ModuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    description: str | None
    position: int
    is_published: bool
    created_at: datetime
    lessons: list[LessonResponse] = []


class AssignmentCreate(BaseModel):
    course_id: int
    module_id: int | None = None
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    instructions: str | None = None
    due_date: date | None = None
    max_marks: Decimal = Field(default=Decimal("100"), gt=0, max_digits=6, decimal_places=2)
    attachment_url: str | None = Field(default=None, max_length=500)
    is_published: bool = True


class AssignmentUpdate(BaseModel):
    module_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    instructions: str | None = None
    due_date: date | None = None
    max_marks: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    attachment_url: str | None = Field(default=None, max_length=500)
    is_published: bool | None = None


class AssignmentSubmissionSummary(BaseModel):
    id: int
    enrollment_id: int
    student_name: str
    student_code: str
    status: str
    marks: Decimal | None
    grade: str | None
    feedback: str | None
    file_url: str | None
    file_name: str | None
    text_answer: str | None
    submitted_at: datetime
    graded_at: datetime | None


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    module_id: int | None
    title: str
    description: str | None
    instructions: str | None
    due_date: date | None
    max_marks: Decimal
    attachment_url: str | None
    is_published: bool
    created_at: datetime
    submissions: list[AssignmentSubmissionSummary] = []


class AssignmentGradeRequest(BaseModel):
    marks: Decimal = Field(ge=0)
    grade: str | None = Field(default=None, max_length=5)
    feedback: str | None = None


class QuizQuestionCreate(BaseModel):
    question_text: str = Field(min_length=2)
    option_a: str = Field(min_length=1, max_length=300)
    option_b: str = Field(min_length=1, max_length=300)
    option_c: str = Field(min_length=1, max_length=300)
    option_d: str = Field(min_length=1, max_length=300)
    correct_option: str = Field(pattern=r"^[ABCD]$")
    marks: Decimal = Field(default=Decimal("1"), gt=0, max_digits=6, decimal_places=2)
    position: int = Field(default=0, ge=0)


class QuizCreate(BaseModel):
    course_id: int
    module_id: int | None = None
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    quiz_type: str = Field(default="quiz", pattern=r"^(quiz|mock_test|practice)$")
    pass_percentage: int = Field(default=40, ge=0, le=100)
    time_limit_minutes: int | None = Field(default=None, ge=1, le=600)
    is_published: bool = True
    questions: list[QuizQuestionCreate] = []


class QuizUpdate(BaseModel):
    module_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    quiz_type: str | None = Field(default=None, pattern=r"^(quiz|mock_test|practice)$")
    pass_percentage: int | None = Field(default=None, ge=0, le=100)
    time_limit_minutes: int | None = Field(default=None, ge=1, le=600)
    is_published: bool | None = None


class QuizQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    marks: Decimal
    position: int


class QuizAttemptSummary(BaseModel):
    id: int
    enrollment_id: int
    student_name: str | None = None
    score: Decimal
    total_marks: Decimal
    percentage: float
    passed: bool
    submitted_at: datetime | None


class QuizResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    module_id: int | None
    title: str
    description: str | None
    quiz_type: str
    pass_percentage: int
    time_limit_minutes: int | None
    is_published: bool
    created_at: datetime
    questions: list[QuizQuestionResponse] = []
    attempts: list[QuizAttemptSummary] = []


class CourseContentResponse(BaseModel):
    course_id: int
    course_name: str
    course_code: str
    duration_months: int
    modules: list[ModuleResponse]
    assignments: list[AssignmentResponse]
    quizzes: list[QuizResponse]


class LmsCourseSummary(BaseModel):
    id: int
    name: str
    code: str
    duration_months: int
    is_active: bool
    module_count: int
    lesson_count: int
    assignment_count: int
    quiz_count: int
    enrollment_count: int


class EnrollmentProgressRow(BaseModel):
    enrollment_id: int
    student_id: int
    student_name: str
    student_code: str
    batch_name: str
    status: str
    total_lessons: int
    completed_lessons: int
    progress_percentage: float
    time_spent_seconds: int
    assignments_submitted: int
    assignments_graded: int
    average_quiz_percentage: float | None


class ProgressResponse(BaseModel):
    course_id: int
    course_name: str
    total_lessons: int
    rows: list[EnrollmentProgressRow]


# ---------------------------------------------------------------------------
# Student-facing learning views
# ---------------------------------------------------------------------------

class StudentLesson(BaseModel):
    id: int
    title: str
    description: str | None
    lesson_type: str
    content_url: str | None
    content_text: str | None
    duration_minutes: int
    status: str
    time_spent_seconds: int
    completed_at: datetime | None


class StudentModule(BaseModel):
    id: int
    title: str
    description: str | None
    position: int
    lessons: list[StudentLesson]


class StudentSubmission(BaseModel):
    status: str
    marks: Decimal | None
    grade: str | None
    feedback: str | None
    file_url: str | None
    file_name: str | None
    text_answer: str | None
    submitted_at: datetime
    graded_at: datetime | None


class StudentAssignment(BaseModel):
    id: int
    module_id: int | None
    title: str
    description: str | None
    instructions: str | None
    due_date: date | None
    max_marks: Decimal
    attachment_url: str | None
    submission: StudentSubmission | None


class StudentQuizSummary(BaseModel):
    id: int
    module_id: int | None
    title: str
    description: str | None
    quiz_type: str
    pass_percentage: int
    time_limit_minutes: int | None
    question_count: int
    best_percentage: float | None
    passed: bool
    attempts: int


class StudentLearningEnrollment(BaseModel):
    enrollment_id: int
    enrollment_code: str
    course_id: int
    course_name: str
    batch_name: str
    status: str
    progress_percentage: float
    total_lessons: int
    completed_lessons: int
    time_spent_seconds: int
    modules: list[StudentModule]
    assignments: list[StudentAssignment]
    quizzes: list[StudentQuizSummary]


class StudentLearningResponse(BaseModel):
    enrollments: list[StudentLearningEnrollment]


class StudentQuizQuestion(BaseModel):
    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    marks: Decimal
    position: int


class StudentQuizTake(BaseModel):
    id: int
    attempt_id: int
    title: str
    description: str | None
    pass_percentage: int
    time_limit_minutes: int | None
    started_at: datetime
    expires_at: datetime | None
    questions: list[StudentQuizQuestion]


class QuizAnswerCreate(BaseModel):
    question_id: int
    selected_option: str | None = Field(default=None, pattern=r"^[ABCD]$")


class QuizSubmitRequest(BaseModel):
    attempt_id: int | None = None
    answers: list[QuizAnswerCreate]


class QuizSubmitResponse(BaseModel):
    attempt_id: int
    score: Decimal
    total_marks: Decimal
    percentage: float
    passed: bool
    correct_answers: int
    total_questions: int


class LessonProgressUpdate(BaseModel):
    time_spent_seconds: int = Field(default=0, ge=0, le=86400)


class LessonProgressResponse(BaseModel):
    lesson_id: int
    enrollment_id: int
    status: str
    time_spent_seconds: int
    completed_at: datetime | None
