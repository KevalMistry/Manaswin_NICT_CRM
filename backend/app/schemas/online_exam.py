from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Question banks
# ---------------------------------------------------------------------------

class BankQuestionInput(BaseModel):
    question_text: str = Field(min_length=2)
    option_a: str = Field(min_length=1, max_length=300)
    option_b: str = Field(min_length=1, max_length=300)
    option_c: str = Field(min_length=1, max_length=300)
    option_d: str = Field(min_length=1, max_length=300)
    correct_option: str = Field(pattern=r"^[ABCD]$")
    marks: Decimal = Field(default=Decimal("1"), gt=0, max_digits=6, decimal_places=2)
    difficulty: str = Field(default="medium", pattern=r"^(easy|medium|hard)$")
    explanation: str | None = None
    position: int = Field(default=0, ge=0)


class BankQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    marks: Decimal
    difficulty: str
    explanation: str | None
    position: int


class QuestionBankCreate(BaseModel):
    course_id: int
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None


class QuestionBankUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None


class QuestionBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    description: str | None
    created_at: datetime
    questions: list[BankQuestionResponse] = []


# ---------------------------------------------------------------------------
# Online exams (staff)
# ---------------------------------------------------------------------------

class ExamQuestionInput(BaseModel):
    question_text: str = Field(min_length=2)
    option_a: str = Field(min_length=1, max_length=300)
    option_b: str = Field(min_length=1, max_length=300)
    option_c: str = Field(min_length=1, max_length=300)
    option_d: str = Field(min_length=1, max_length=300)
    correct_option: str = Field(pattern=r"^[ABCD]$")
    marks: Decimal = Field(default=Decimal("1"), gt=0, max_digits=6, decimal_places=2)
    explanation: str | None = None
    position: int = Field(default=0, ge=0)


class ExamQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    marks: Decimal
    explanation: str | None
    position: int


class OnlineExamCreate(BaseModel):
    course_id: int
    batch_id: int | None = None
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None
    instructions: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    duration_minutes: int = Field(default=60, ge=1, le=600)
    pass_percentage: int = Field(default=40, ge=0, le=100)
    max_attempts: int = Field(default=1, ge=1, le=10)
    shuffle_questions: bool = False
    negative_marking: bool = False
    questions: list[ExamQuestionInput] = []
    bank_question_ids: list[int] = []

    @model_validator(mode="after")
    def validate_schedule(self) -> "OnlineExamCreate":
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("The exam end time must be after the start time")
        return self


class OnlineExamUpdate(BaseModel):
    batch_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    instructions: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    pass_percentage: int | None = Field(default=None, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    shuffle_questions: bool | None = None
    negative_marking: bool | None = None


class ExamAttemptSummary(BaseModel):
    id: int
    enrollment_id: int
    student_name: str
    student_code: str
    attempt_number: int
    status: str
    score: Decimal
    total_marks: Decimal
    percentage: float
    passed: bool
    auto_submitted: bool
    started_at: datetime
    submitted_at: datetime | None


class OnlineExamSummary(BaseModel):
    id: int
    course_id: int
    course_name: str
    batch_id: int | None
    title: str
    description: str | None
    start_at: datetime | None
    end_at: datetime | None
    duration_minutes: int
    pass_percentage: int
    max_attempts: int
    shuffle_questions: bool
    negative_marking: bool
    is_published: bool
    results_published: bool
    question_count: int
    total_marks: Decimal
    attempt_count: int


class OnlineExamResponse(OnlineExamSummary):
    instructions: str | None
    created_at: datetime
    questions: list[ExamQuestionResponse] = []
    attempts: list[ExamAttemptSummary] = []


class OnlineExamCourseSummary(BaseModel):
    id: int
    name: str
    code: str
    duration_months: int
    exam_count: int
    bank_count: int
    enrollment_count: int


# ---------------------------------------------------------------------------
# Student exam taking
# ---------------------------------------------------------------------------

class StudentExamQuestion(BaseModel):
    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    marks: Decimal
    position: int


class StudentExamSummary(BaseModel):
    exam_id: int
    enrollment_id: int
    course_name: str
    title: str
    description: str | None
    instructions: str | None
    start_at: datetime | None
    end_at: datetime | None
    duration_minutes: int
    pass_percentage: int
    max_attempts: int
    question_count: int
    total_marks: Decimal
    attempts_used: int
    state: str
    can_start: bool
    in_progress_attempt_id: int | None
    last_attempt_id: int | None
    best_percentage: float | None
    passed: bool
    results_published: bool
    note: str | None = None


class StudentExamAttempt(BaseModel):
    attempt_id: int
    exam_id: int
    title: str
    instructions: str | None
    status: str
    attempt_number: int
    started_at: datetime
    expires_at: datetime | None
    remaining_seconds: int | None
    total_marks: Decimal
    questions: list[StudentExamQuestion]
    answers: dict[int, str] = {}


class ExamAnswerInput(BaseModel):
    question_id: int
    selected_option: str | None = Field(default=None, pattern=r"^[ABCD]$")


class ExamSaveAnswersRequest(BaseModel):
    answers: list[ExamAnswerInput] = Field(max_length=500)


class ExamSubmitRequest(BaseModel):
    answers: list[ExamAnswerInput] = Field(default_factory=list, max_length=500)
    auto: bool = False


class ExamResult(BaseModel):
    attempt_id: int
    exam_id: int
    title: str
    status: str
    score: Decimal | None
    total_marks: Decimal
    percentage: float | None
    passed: bool | None
    correct_answers: int | None
    total_questions: int
    submitted_at: datetime | None
    auto_submitted: bool
    results_published: bool
    note: str | None = None
