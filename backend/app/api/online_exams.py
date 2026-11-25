from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import DatabaseSession, require_module, require_roles
from app.models.batch import Batch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.online_exam import (
    BankQuestion,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    OnlineExam,
    QuestionBank,
)
from app.models.student import Student
from app.models.user import User
from app.services.external_forms import normalize_form_link
from app.schemas.online_exam import (
    BankQuestionInput,
    BankQuestionResponse,
    ExamAnswerInput,
    ExamAttemptSummary,
    ExamQuestionInput,
    ExamQuestionResponse,
    ExamResult,
    ExamSaveAnswersRequest,
    ExamSubmitRequest,
    OnlineExamCourseSummary,
    OnlineExamCreate,
    OnlineExamResponse,
    OnlineExamSummary,
    OnlineExamUpdate,
    QuestionBankCreate,
    QuestionBankResponse,
    QuestionBankUpdate,
    StudentExamAttempt,
    StudentExamQuestion,
    StudentExamSummary,
)


router = APIRouter(prefix="/api/online-exams", tags=["Online Exams"])
StaffUser = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff")
StudentUser = require_roles("Student")
ExamsAccess = require_module("examinations")


# ---------------------------------------------------------------------------
# Time and access helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _external_form_values(
    url: str | None, provider: str | None
) -> tuple[str | None, str | None]:
    """Validate a form link pair and turn API errors into HTTP 400 responses."""
    try:
        return normalize_form_link(url, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _course_scope(db: DatabaseSession, current_user: User):
    """Course ids the user may manage, or ``None`` for Super Admin."""
    if current_user.role.name == "Super Admin":
        return None
    if current_user.role.name == "Faculty":
        return select(Batch.course_id).where(Batch.faculty_id == current_user.id)
    if current_user.branch_id is not None:
        return select(Batch.course_id).where(Batch.branch_id == current_user.branch_id)
    return select(Batch.course_id).where(Batch.id == -1)


def _get_course(db: DatabaseSession, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _assert_course_access(db: DatabaseSession, current_user: User, course_id: int) -> None:
    scope = _course_scope(db, current_user)
    if scope is None:
        return
    if db.scalar(scope.where(Batch.course_id == course_id).limit(1)) is None:
        raise HTTPException(
            status_code=403,
            detail="You can manage exams only for courses assigned to you or your branch.",
        )


def _assert_batch_access(db: DatabaseSession, current_user: User, batch_id: int) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if current_user.role.name != "Super Admin":
        if current_user.branch_id is None or batch.branch_id != current_user.branch_id:
            raise HTTPException(
                status_code=403, detail="You can access only your assigned branch"
            )
        if current_user.role.name == "Faculty" and batch.faculty_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Faculty can manage only exams for assigned batches",
            )
    return batch


def _get_exam(db: DatabaseSession, exam_id: int) -> OnlineExam:
    exam = db.scalar(
        select(OnlineExam)
        .options(joinedload(OnlineExam.questions), joinedload(OnlineExam.course))
        .where(OnlineExam.id == exam_id)
    )
    if exam is None:
        raise HTTPException(status_code=404, detail="Online exam not found")
    return exam


def _total_marks(exam: OnlineExam) -> Decimal:
    return sum((question.marks for question in exam.questions), Decimal("0"))


def _ordered_questions(attempt: ExamAttempt, exam: OnlineExam) -> list[ExamQuestion]:
    by_id = {question.id: question for question in exam.questions}
    if attempt.question_order:
        ordered: list[ExamQuestion] = []
        for raw in attempt.question_order.split(","):
            raw = raw.strip()
            if raw.isdigit() and int(raw) in by_id:
                ordered.append(by_id[int(raw)])
        seen = {question.id for question in ordered}
        ordered.extend(question for question in exam.questions if question.id not in seen)
        return ordered
    return sorted(exam.questions, key=lambda question: (question.position, question.id))


def _attempt_summary(db: DatabaseSession, attempt: ExamAttempt) -> dict:
    row = db.execute(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.id == attempt.enrollment_id)
    ).scalar_one_or_none()
    return {
        "id": attempt.id,
        "enrollment_id": attempt.enrollment_id,
        "student_name": row.full_name if row else "Unknown student",
        "student_code": row.student_code if row else "—",
        "attempt_number": attempt.attempt_number,
        "status": attempt.status,
        "score": attempt.score,
        "total_marks": attempt.total_marks,
        "percentage": attempt.percentage,
        "passed": attempt.passed,
        "auto_submitted": attempt.auto_submitted,
        "started_at": attempt.started_at,
        "submitted_at": attempt.submitted_at,
    }


def _exam_summary(db: DatabaseSession, exam: OnlineExam) -> dict:
    attempt_count = int(
        db.scalar(
            select(func.count(ExamAttempt.id)).where(ExamAttempt.exam_id == exam.id)
        )
        or 0
    )
    return {
        "id": exam.id,
        "course_id": exam.course_id,
        "course_name": exam.course.name,
        "batch_id": exam.batch_id,
        "title": exam.title,
        "description": exam.description,
        "external_form_url": exam.external_form_url,
        "external_form_provider": exam.external_form_provider,
        "start_at": exam.start_at,
        "end_at": exam.end_at,
        "duration_minutes": exam.duration_minutes,
        "pass_percentage": exam.pass_percentage,
        "max_attempts": exam.max_attempts,
        "shuffle_questions": exam.shuffle_questions,
        "negative_marking": exam.negative_marking,
        "is_published": exam.is_published,
        "results_published": exam.results_published,
        "question_count": len(exam.questions),
        "total_marks": _total_marks(exam),
        "attempt_count": attempt_count,
    }


def _exam_response(db: DatabaseSession, exam: OnlineExam) -> OnlineExamResponse:
    attempts = db.scalars(
        select(ExamAttempt)
        .where(ExamAttempt.exam_id == exam.id)
        .order_by(ExamAttempt.id.desc())
    ).all()
    return OnlineExamResponse(
        **_exam_summary(db, exam),
        instructions=exam.instructions,
        created_at=exam.created_at,
        questions=[
            ExamQuestionResponse.model_validate(question) for question in exam.questions
        ],
        attempts=[_attempt_summary(db, attempt) for attempt in attempts],
    )


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def _apply_answers(
    db: DatabaseSession, attempt: ExamAttempt, exam: OnlineExam, answers: list[ExamAnswerInput]
) -> None:
    valid_ids = {question.id for question in exam.questions}
    existing = {
        answer.question_id: answer
        for answer in db.scalars(
            select(ExamAnswer).where(ExamAnswer.attempt_id == attempt.id)
        ).all()
    }
    for item in answers:
        if item.question_id not in valid_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Question {item.question_id} does not belong to this exam",
            )
        answer = existing.get(item.question_id)
        if answer is None:
            answer = ExamAnswer(attempt_id=attempt.id, question_id=item.question_id)
            db.add(answer)
            existing[item.question_id] = answer
        answer.selected_option = item.selected_option
    db.flush()


def _grade_attempt(
    db: DatabaseSession, attempt: ExamAttempt, exam: OnlineExam, *, auto: bool
) -> int:
    now = _now()
    answers = {
        answer.question_id: answer
        for answer in db.scalars(
            select(ExamAnswer).where(ExamAnswer.attempt_id == attempt.id)
        ).all()
    }
    score = Decimal("0")
    total = Decimal("0")
    correct = 0
    for question in exam.questions:
        total += question.marks
        answer = answers.get(question.id)
        selected = answer.selected_option if answer else None
        is_correct = selected is not None and selected == question.correct_option
        awarded = question.marks if is_correct else Decimal("0")
        if selected is not None and not is_correct and exam.negative_marking:
            awarded = -(question.marks * Decimal("0.25"))
        if answer is None:
            answer = ExamAnswer(attempt_id=attempt.id, question_id=question.id)
            db.add(answer)
        answer.selected_option = selected
        answer.is_correct = is_correct
        answer.marks_awarded = awarded.quantize(Decimal("0.01"))
        score += awarded
        if is_correct:
            correct += 1
    score = max(score, Decimal("0"))
    percentage = float((score / total) * 100) if total else 0.0
    attempt.total_marks = total
    attempt.score = score.quantize(Decimal("0.01"))
    attempt.percentage = round(percentage, 2)
    attempt.passed = percentage >= exam.pass_percentage
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.auto_submitted = auto
    db.flush()
    return correct


def _auto_submit_if_expired(
    db: DatabaseSession, attempt: ExamAttempt, exam: OnlineExam
) -> bool:
    if (
        attempt.status == "in_progress"
        and attempt.expires_at is not None
        and _now() >= attempt.expires_at
    ):
        _grade_attempt(db, attempt, exam, auto=True)
        db.commit()
        db.refresh(attempt)
        return True
    return False


def _result_payload(
    db: DatabaseSession, attempt: ExamAttempt, exam: OnlineExam
) -> ExamResult:
    total_questions = len(exam.questions)
    correct = int(
        db.scalar(
            select(func.count(ExamAnswer.id)).where(
                ExamAnswer.attempt_id == attempt.id, ExamAnswer.is_correct.is_(True)
            )
        )
        or 0
    )
    if attempt.status != "submitted":
        return ExamResult(
            attempt_id=attempt.id,
            exam_id=exam.id,
            title=exam.title,
            status=attempt.status,
            score=None,
            total_marks=attempt.total_marks,
            percentage=None,
            passed=None,
            correct_answers=None,
            total_questions=total_questions,
            submitted_at=attempt.submitted_at,
            auto_submitted=attempt.auto_submitted,
            results_published=exam.results_published,
            note="This attempt is still in progress.",
        )
    if not exam.results_published:
        return ExamResult(
            attempt_id=attempt.id,
            exam_id=exam.id,
            title=exam.title,
            status=attempt.status,
            score=None,
            total_marks=attempt.total_marks,
            percentage=None,
            passed=None,
            correct_answers=None,
            total_questions=total_questions,
            submitted_at=attempt.submitted_at,
            auto_submitted=attempt.auto_submitted,
            results_published=False,
            note="Your answers were submitted. Results will be published by your institute.",
        )
    return ExamResult(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        status=attempt.status,
        score=attempt.score,
        total_marks=attempt.total_marks,
        percentage=attempt.percentage,
        passed=attempt.passed,
        correct_answers=correct,
        total_questions=total_questions,
        submitted_at=attempt.submitted_at,
        auto_submitted=attempt.auto_submitted,
        results_published=True,
    )


# ---------------------------------------------------------------------------
# Staff: accessible courses and question banks
# ---------------------------------------------------------------------------

@router.get(
    "/courses",
    response_model=list[OnlineExamCourseSummary],
    dependencies=[Depends(ExamsAccess)],
)
def list_exam_courses(
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> list[OnlineExamCourseSummary]:
    query = select(Course).order_by(Course.name)
    scope = _course_scope(db, current_user)
    if scope is not None:
        query = query.where(Course.id.in_(scope))
    summaries: list[OnlineExamCourseSummary] = []
    for course in db.scalars(query).all():
        exam_count = int(
            db.scalar(
                select(func.count(OnlineExam.id)).where(OnlineExam.course_id == course.id)
            )
            or 0
        )
        bank_count = int(
            db.scalar(
                select(func.count(QuestionBank.id)).where(
                    QuestionBank.course_id == course.id
                )
            )
            or 0
        )
        enrollment_count = int(
            db.scalar(
                select(func.count(Enrollment.id))
                .join(Batch, Enrollment.batch_id == Batch.id)
                .where(
                    Batch.course_id == course.id,
                    Enrollment.status.in_(("active", "completed")),
                )
            )
            or 0
        )
        summaries.append(
            OnlineExamCourseSummary(
                id=course.id,
                name=course.name,
                code=course.code,
                duration_months=course.duration_months,
                exam_count=exam_count,
                bank_count=bank_count,
                enrollment_count=enrollment_count,
            )
        )
    return summaries


@router.get(
    "/banks",
    response_model=list[QuestionBankResponse],
    dependencies=[Depends(ExamsAccess)],
)
def list_question_banks(
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
    course_id: int = Query(...),
) -> list[QuestionBankResponse]:
    _get_course(db, course_id)
    _assert_course_access(db, current_user, course_id)
    banks = db.scalars(
        select(QuestionBank)
        .options(joinedload(QuestionBank.questions))
        .where(QuestionBank.course_id == course_id)
        .order_by(QuestionBank.title)
    ).unique().all()
    return [QuestionBankResponse.model_validate(bank) for bank in banks]


@router.post(
    "/banks",
    response_model=QuestionBankResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ExamsAccess)],
)
def create_question_bank(
    payload: QuestionBankCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuestionBankResponse:
    _get_course(db, payload.course_id)
    _assert_course_access(db, current_user, payload.course_id)
    data = payload.model_dump()
    url, provider = _external_form_values(
        data.pop("external_form_url", None), data.pop("external_form_provider", None)
    )
    data["external_form_url"] = url
    data["external_form_provider"] = provider
    bank = QuestionBank(**data, created_by_id=current_user.id)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return QuestionBankResponse.model_validate(bank)


@router.patch(
    "/banks/{bank_id}",
    response_model=QuestionBankResponse,
    dependencies=[Depends(ExamsAccess)],
)
def update_question_bank(
    bank_id: int,
    payload: QuestionBankUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuestionBankResponse:
    bank = db.get(QuestionBank, bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="Question bank not found")
    _assert_course_access(db, current_user, bank.course_id)
    data = payload.model_dump(exclude_unset=True)
    if "external_form_url" in data or "external_form_provider" in data:
        url, provider = _external_form_values(
            data.get("external_form_url", bank.external_form_url),
            data.get("external_form_provider", bank.external_form_provider),
        )
        data["external_form_url"] = url
        data["external_form_provider"] = provider
    for field, value in data.items():
        setattr(bank, field, value)
    db.commit()
    db.refresh(bank)
    return QuestionBankResponse.model_validate(bank)


@router.delete("/banks/{bank_id}", dependencies=[Depends(ExamsAccess)])
def delete_question_bank(
    bank_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    bank = db.get(QuestionBank, bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="Question bank not found")
    _assert_course_access(db, current_user, bank.course_id)
    db.delete(bank)
    db.commit()
    return {"message": "Question bank deleted"}


@router.post(
    "/banks/{bank_id}/questions",
    response_model=QuestionBankResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ExamsAccess)],
)
def add_bank_question(
    bank_id: int,
    payload: BankQuestionInput,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuestionBankResponse:
    bank = db.get(QuestionBank, bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="Question bank not found")
    _assert_course_access(db, current_user, bank.course_id)
    db.add(BankQuestion(bank_id=bank.id, **payload.model_dump()))
    db.commit()
    db.refresh(bank)
    return QuestionBankResponse.model_validate(bank)


@router.patch(
    "/banks/{bank_id}/questions/{question_id}",
    response_model=QuestionBankResponse,
    dependencies=[Depends(ExamsAccess)],
)
def update_bank_question(
    bank_id: int,
    question_id: int,
    payload: BankQuestionInput,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuestionBankResponse:
    bank = db.get(QuestionBank, bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="Question bank not found")
    _assert_course_access(db, current_user, bank.course_id)
    question = db.get(BankQuestion, question_id)
    if question is None or question.bank_id != bank_id:
        raise HTTPException(status_code=404, detail="Question not found")
    for field, value in payload.model_dump().items():
        setattr(question, field, value)
    db.commit()
    db.refresh(bank)
    return QuestionBankResponse.model_validate(bank)


@router.delete(
    "/banks/{bank_id}/questions/{question_id}",
    dependencies=[Depends(ExamsAccess)],
)
def delete_bank_question(
    bank_id: int,
    question_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    bank = db.get(QuestionBank, bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="Question bank not found")
    _assert_course_access(db, current_user, bank.course_id)
    question = db.get(BankQuestion, question_id)
    if question is None or question.bank_id != bank_id:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()
    return {"message": "Question deleted"}


# ---------------------------------------------------------------------------
# Staff: exams
# ---------------------------------------------------------------------------

def _validate_exam_batch(
    db: DatabaseSession, current_user: User, course_id: int, batch_id: int | None
) -> None:
    if batch_id is None:
        return
    batch = _assert_batch_access(db, current_user, batch_id)
    if batch.course_id != course_id:
        raise HTTPException(
            status_code=400, detail="The selected batch does not belong to this course"
        )


@router.get(
    "",
    response_model=list[OnlineExamSummary],
    dependencies=[Depends(ExamsAccess)],
)
def list_online_exams(
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
    course_id: int | None = Query(default=None),
    include_unpublished: bool = Query(default=True),
) -> list[OnlineExamSummary]:
    query = (
        select(OnlineExam)
        .options(joinedload(OnlineExam.course), joinedload(OnlineExam.questions))
        .order_by(OnlineExam.created_at.desc(), OnlineExam.id.desc())
    )
    scope = _course_scope(db, current_user)
    if scope is not None:
        query = query.where(OnlineExam.course_id.in_(scope))
    if course_id is not None:
        _get_course(db, course_id)
        _assert_course_access(db, current_user, course_id)
        query = query.where(OnlineExam.course_id == course_id)
    if not include_unpublished:
        query = query.where(OnlineExam.is_published.is_(True))
    return [
        OnlineExamSummary(**_exam_summary(db, exam))
        for exam in db.scalars(query).unique().all()
    ]


@router.post(
    "",
    response_model=OnlineExamResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ExamsAccess)],
)
def create_online_exam(
    payload: OnlineExamCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    _get_course(db, payload.course_id)
    _assert_course_access(db, current_user, payload.course_id)
    _validate_exam_batch(db, current_user, payload.course_id, payload.batch_id)

    source_bank: QuestionBank | None = None
    if payload.source_bank_id is not None:
        source_bank = db.get(QuestionBank, payload.source_bank_id)
        if source_bank is None or source_bank.course_id != payload.course_id:
            raise HTTPException(
                status_code=400,
                detail="The selected question bank is not available for this course",
            )

    bank_questions: list[BankQuestion] = []
    if payload.bank_question_ids:
        ordered_ids: list[int] = []
        seen: set[int] = set()
        for question_id in payload.bank_question_ids:
            if question_id not in seen:
                seen.add(question_id)
                ordered_ids.append(question_id)
        bank_questions = list(
            db.scalars(
                select(BankQuestion)
                .join(QuestionBank, BankQuestion.bank_id == QuestionBank.id)
                .where(
                    BankQuestion.id.in_(ordered_ids),
                    QuestionBank.course_id == payload.course_id,
                )
            ).all()
        )
        found = {question.id for question in bank_questions}
        missing = [question_id for question_id in ordered_ids if question_id not in found]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Question(s) {missing} are not in a bank for this course",
            )
        by_id = {question.id: question for question in bank_questions}
        bank_questions = [by_id[question_id] for question_id in ordered_ids]

    data = payload.model_dump(
        exclude={"questions", "bank_question_ids", "source_bank_id"}
    )
    form_url, form_provider = _external_form_values(
        payload.external_form_url, payload.external_form_provider
    )
    if (
        "external_form_url" not in payload.model_fields_set
        and source_bank is not None
        and source_bank.external_form_url
    ):
        form_url = source_bank.external_form_url
        form_provider = source_bank.external_form_provider
    data["external_form_url"] = form_url
    data["external_form_provider"] = form_provider
    data["start_at"] = _naive_utc(payload.start_at)
    data["end_at"] = _naive_utc(payload.end_at)
    exam = OnlineExam(**data, created_by_id=current_user.id)
    db.add(exam)
    db.flush()

    position = 0
    for question in payload.questions:
        db.add(
            ExamQuestion(
                exam_id=exam.id,
                position=question.position if question.position else position,
                **question.model_dump(exclude={"position"}),
            )
        )
        position += 1
    for question in bank_questions:
        db.add(
            ExamQuestion(
                exam_id=exam.id,
                source_question_id=question.id,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                correct_option=question.correct_option,
                marks=question.marks,
                explanation=question.explanation,
                position=position,
            )
        )
        position += 1
    db.commit()
    db.refresh(exam)
    return _exam_response(db, _get_exam(db, exam.id))


@router.get(
    "/{exam_id}",
    response_model=OnlineExamResponse,
    dependencies=[Depends(ExamsAccess)],
)
def get_online_exam(
    exam_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    return _exam_response(db, exam)


@router.patch(
    "/{exam_id}",
    response_model=OnlineExamResponse,
    dependencies=[Depends(ExamsAccess)],
)
def update_online_exam(
    exam_id: int,
    payload: OnlineExamUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    data = payload.model_dump(exclude_unset=True)
    if "batch_id" in data:
        _validate_exam_batch(db, current_user, exam.course_id, data["batch_id"])
    if "external_form_url" in data or "external_form_provider" in data:
        data["external_form_url"], data["external_form_provider"] = _external_form_values(
            data.get("external_form_url", exam.external_form_url),
            data.get("external_form_provider", exam.external_form_provider),
        )
    if "start_at" in data:
        data["start_at"] = _naive_utc(data["start_at"])
    if "end_at" in data:
        data["end_at"] = _naive_utc(data["end_at"])
    new_start = data.get("start_at", exam.start_at)
    new_end = data.get("end_at", exam.end_at)
    if new_start and new_end and new_end <= new_start:
        raise HTTPException(
            status_code=400, detail="The exam end time must be after the start time"
        )
    for field, value in data.items():
        setattr(exam, field, value)
    db.commit()
    return _exam_response(db, _get_exam(db, exam_id))


@router.delete("/{exam_id}", dependencies=[Depends(ExamsAccess)])
def delete_online_exam(
    exam_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    db.delete(exam)
    db.commit()
    return {"message": "Online exam deleted"}


@router.post(
    "/{exam_id}/publish",
    response_model=OnlineExamResponse,
    dependencies=[Depends(ExamsAccess)],
)
def publish_online_exam(
    exam_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    if not exam.questions and not exam.external_form_url:
        raise HTTPException(
            status_code=400,
            detail="Add at least one question or a published form link before publishing",
        )
    if exam.start_at and exam.end_at and exam.end_at <= exam.start_at:
        raise HTTPException(
            status_code=400, detail="The exam end time must be after the start time"
        )
    exam.is_published = True
    db.commit()
    return _exam_response(db, _get_exam(db, exam_id))


@router.post(
    "/{exam_id}/unpublish",
    response_model=OnlineExamResponse,
    dependencies=[Depends(ExamsAccess)],
)
def unpublish_online_exam(
    exam_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    if db.scalar(
        select(ExamAttempt.id).where(
            ExamAttempt.exam_id == exam.id, ExamAttempt.status == "in_progress"
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Students are currently taking this exam. Wait for them to submit.",
        )
    exam.is_published = False
    db.commit()
    return _exam_response(db, _get_exam(db, exam_id))


@router.post(
    "/{exam_id}/publish-results",
    response_model=OnlineExamResponse,
    dependencies=[Depends(ExamsAccess)],
)
def publish_exam_results(
    exam_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    exam.results_published = True
    db.commit()
    return _exam_response(db, _get_exam(db, exam_id))


@router.post(
    "/{exam_id}/questions",
    response_model=OnlineExamResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ExamsAccess)],
)
def add_exam_question(
    exam_id: int,
    payload: ExamQuestionInput,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    if exam.is_published:
        raise HTTPException(
            status_code=409,
            detail="Unpublish the exam before changing its questions.",
        )
    position = payload.position or (len(exam.questions))
    db.add(
        ExamQuestion(
            exam_id=exam.id,
            position=position,
            **payload.model_dump(exclude={"position"}),
        )
    )
    db.commit()
    return _exam_response(db, _get_exam(db, exam_id))


@router.delete(
    "/{exam_id}/questions/{question_id}",
    response_model=OnlineExamResponse,
    dependencies=[Depends(ExamsAccess)],
)
def delete_exam_question(
    exam_id: int,
    question_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> OnlineExamResponse:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    if exam.is_published:
        raise HTTPException(
            status_code=409,
            detail="Unpublish the exam before changing its questions.",
        )
    question = db.get(ExamQuestion, question_id)
    if question is None or question.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()
    return _exam_response(db, _get_exam(db, exam_id))


@router.get(
    "/{exam_id}/attempts",
    response_model=list[ExamAttemptSummary],
    dependencies=[Depends(ExamsAccess)],
)
def list_exam_attempts(
    exam_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> list[ExamAttemptSummary]:
    exam = _get_exam(db, exam_id)
    _assert_course_access(db, current_user, exam.course_id)
    attempts = db.scalars(
        select(ExamAttempt)
        .where(ExamAttempt.exam_id == exam.id)
        .order_by(ExamAttempt.id.desc())
    ).all()
    return [ExamAttemptSummary(**_attempt_summary(db, attempt)) for attempt in attempts]


# ---------------------------------------------------------------------------
# Student-facing exam taking
# ---------------------------------------------------------------------------

def _student_enrollments(
    db: DatabaseSession, current_user: User
) -> tuple[Student, list[Enrollment]]:
    student = db.scalar(
        select(Student).where(
            Student.user_id == current_user.id, Student.is_active.is_(True)
        )
    )
    if student is None:
        raise HTTPException(
            status_code=403, detail="No active student profile is linked to this account"
        )
    enrollments = db.scalars(
        select(Enrollment)
        .options(joinedload(Enrollment.batch).joinedload(Batch.course))
        .where(
            Enrollment.student_id == student.id,
            Enrollment.status.in_(("active", "completed")),
        )
        .order_by(Enrollment.admission_date.desc())
    ).unique().all()
    return student, list(enrollments)


def _enrollment_for_exam(
    enrollments: list[Enrollment], exam: OnlineExam
) -> Enrollment:
    matches = [
        enrollment
        for enrollment in enrollments
        if enrollment.batch.course_id == exam.course_id
        and (exam.batch_id is None or enrollment.batch_id == exam.batch_id)
    ]
    if not matches:
        raise HTTPException(
            status_code=403, detail="This exam is not available for your enrollment"
        )
    active = [enrollment for enrollment in matches if enrollment.status == "active"]
    return active[0] if active else matches[0]


def _exam_state(
    db: DatabaseSession,
    exam: OnlineExam,
    enrollment: Enrollment,
    now: datetime,
) -> tuple[dict, ExamAttempt | None]:
    attempts = db.scalars(
        select(ExamAttempt)
        .where(
            ExamAttempt.exam_id == exam.id,
            ExamAttempt.enrollment_id == enrollment.id,
        )
        .order_by(ExamAttempt.attempt_number)
    ).all()
    in_progress = next(
        (attempt for attempt in attempts if attempt.status == "in_progress"), None
    )
    if in_progress is not None:
        _auto_submit_if_expired(db, in_progress, exam)
        if in_progress.status == "submitted":
            in_progress = None
    used = len(attempts)
    submitted = [attempt for attempt in attempts if attempt.status == "submitted"]
    best = max((attempt.percentage for attempt in submitted), default=None)
    passed = any(attempt.passed for attempt in submitted)

    external_form = bool(exam.external_form_url)
    form_open = not (
        (exam.start_at and now < exam.start_at)
        or (exam.end_at and now > exam.end_at)
    )
    state = "available"
    note = None
    can_start = True
    if exam.start_at and now < exam.start_at:
        state = "not_started"
        can_start = False
        note = "This exam opens later."
    elif exam.end_at and now > exam.end_at:
        state = "closed"
        can_start = False
        note = "The exam window has closed."
    elif external_form:
        note = "Open the exam form to attempt."
    if in_progress is not None:
        state = "in_progress"
        can_start = False
        note = "You have an attempt in progress."
    elif used >= exam.max_attempts:
        state = "completed"
        can_start = False
        note = "You have used all available attempts."

    if external_form:
        can_start = False

    return (
        {
            "exam_id": exam.id,
            "enrollment_id": enrollment.id,
            "course_name": enrollment.batch.course.name,
            "title": exam.title,
            "description": exam.description,
            "instructions": exam.instructions,
            "external_form": external_form,
            "external_form_provider": exam.external_form_provider,
            "external_form_url": exam.external_form_url if external_form and form_open else None,
            "start_at": exam.start_at,
            "end_at": exam.end_at,
            "duration_minutes": exam.duration_minutes,
            "pass_percentage": exam.pass_percentage,
            "max_attempts": exam.max_attempts,
            "question_count": len(exam.questions),
            "total_marks": _total_marks(exam),
            "attempts_used": used,
            "state": state,
            "can_start": can_start,
            "in_progress_attempt_id": in_progress.id if in_progress else None,
            "last_attempt_id": attempts[-1].id if attempts else None,
            "best_percentage": round(best, 2) if best is not None and exam.results_published else None,
            "passed": passed if exam.results_published else False,
            "results_published": exam.results_published,
            "note": note,
        },
        in_progress,
    )


def _attempt_payload(
    db: DatabaseSession, attempt: ExamAttempt, exam: OnlineExam
) -> StudentExamAttempt:
    questions = _ordered_questions(attempt, exam)
    answers = {
        answer.question_id: answer.selected_option
        for answer in db.scalars(
            select(ExamAnswer).where(ExamAnswer.attempt_id == attempt.id)
        ).all()
        if answer.selected_option
    }
    now = _now()
    remaining = None
    if attempt.expires_at is not None:
        remaining = max(0, int((attempt.expires_at - now).total_seconds()))
    return StudentExamAttempt(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        instructions=exam.instructions,
        status=attempt.status,
        attempt_number=attempt.attempt_number,
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        remaining_seconds=remaining,
        total_marks=_total_marks(exam),
        questions=[
            StudentExamQuestion(
                id=question.id,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                marks=question.marks,
                position=index + 1,
            )
            for index, question in enumerate(questions)
        ]
        if attempt.status == "in_progress"
        else [],
        answers=answers,
    )


@router.get("/me/exams", response_model=list[StudentExamSummary])
def list_my_exams(
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> list[StudentExamSummary]:
    _student, enrollments = _student_enrollments(db, current_user)
    if not enrollments:
        return []
    now = _now()
    courses = {enrollment.batch.course_id for enrollment in enrollments}
    exams = db.scalars(
        select(OnlineExam)
        .options(joinedload(OnlineExam.questions))
        .where(
            OnlineExam.is_published.is_(True),
            OnlineExam.course_id.in_(courses),
        )
        .order_by(OnlineExam.start_at.is_(None), OnlineExam.start_at, OnlineExam.id)
    ).unique().all()
    summaries: list[StudentExamSummary] = []
    for exam in exams:
        try:
            enrollment = _enrollment_for_exam(enrollments, exam)
        except HTTPException:
            continue
        payload, _attempt = _exam_state(db, exam, enrollment, now)
        summaries.append(StudentExamSummary(**payload))
    return summaries


@router.post("/me/exams/{exam_id}/start", response_model=StudentExamAttempt)
def start_exam(
    exam_id: int,
    request: Request,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> StudentExamAttempt:
    exam = _get_exam(db, exam_id)
    if not exam.is_published:
        raise HTTPException(status_code=404, detail="Online exam not found")
    if exam.external_form_url:
        raise HTTPException(
            status_code=400,
            detail="This exam uses an external form. Open it from your exam list.",
        )
    if not exam.questions:
        raise HTTPException(status_code=400, detail="This exam has no questions yet")
    _student, enrollments = _student_enrollments(db, current_user)
    enrollment = _enrollment_for_exam(enrollments, exam)
    now = _now()
    if exam.start_at and now < exam.start_at:
        raise HTTPException(status_code=409, detail="This exam has not opened yet")
    if exam.end_at and now > exam.end_at:
        raise HTTPException(status_code=409, detail="The exam window has closed")

    attempts = list(
        db.scalars(
            select(ExamAttempt)
            .where(
                ExamAttempt.exam_id == exam.id,
                ExamAttempt.enrollment_id == enrollment.id,
            )
            .order_by(ExamAttempt.attempt_number)
        ).all()
    )
    existing = next(
        (attempt for attempt in attempts if attempt.status == "in_progress"), None
    )
    if existing is not None:
        if _auto_submit_if_expired(db, existing, exam):
            existing = None
        else:
            return _attempt_payload(db, existing, exam)
    if len(attempts) >= exam.max_attempts:
        raise HTTPException(
            status_code=409,
            detail="You have used all available attempts for this exam",
        )

    questions = list(exam.questions)
    if exam.shuffle_questions:
        random.shuffle(questions)
    else:
        questions.sort(key=lambda question: (question.position, question.id))
    expires_at = now + timedelta(minutes=exam.duration_minutes)
    if exam.end_at is not None and exam.end_at < expires_at:
        expires_at = exam.end_at
    attempt = ExamAttempt(
        exam_id=exam.id,
        enrollment_id=enrollment.id,
        attempt_number=len(attempts) + 1,
        status="in_progress",
        question_order=",".join(str(question.id) for question in questions),
        started_at=now,
        expires_at=expires_at,
        total_marks=_total_marks(exam),
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return _attempt_payload(db, attempt, exam)


def _owned_attempt(
    db: DatabaseSession, attempt_id: int, current_user: User
) -> tuple[ExamAttempt, OnlineExam, Enrollment]:
    attempt = db.get(ExamAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    exam = _get_exam(db, attempt.exam_id)
    _student, enrollments = _student_enrollments(db, current_user)
    enrollment = next(
        (
            item
            for item in enrollments
            if item.id == attempt.enrollment_id
        ),
        None,
    )
    if enrollment is None:
        raise HTTPException(status_code=403, detail="This attempt does not belong to you")
    return attempt, exam, enrollment


@router.get("/me/attempts/{attempt_id}", response_model=StudentExamAttempt)
def get_my_attempt(
    attempt_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> StudentExamAttempt:
    attempt, exam, _enrollment = _owned_attempt(db, attempt_id, current_user)
    _auto_submit_if_expired(db, attempt, exam)
    if attempt.status == "in_progress" and exam.end_at and _now() > exam.end_at:
        _grade_attempt(db, attempt, exam, auto=True)
        db.commit()
        db.refresh(attempt)
    return _attempt_payload(db, attempt, exam)


@router.put("/me/attempts/{attempt_id}/answers")
def save_my_answers(
    attempt_id: int,
    payload: ExamSaveAnswersRequest,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> dict[str, int | str]:
    attempt, exam, _enrollment = _owned_attempt(db, attempt_id, current_user)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=409, detail="This attempt has already been submitted")
    if _auto_submit_if_expired(db, attempt, exam):
        raise HTTPException(status_code=409, detail="The exam time has expired")
    _apply_answers(db, attempt, exam, payload.answers)
    db.commit()
    return {"message": "Answers saved", "saved": len(payload.answers)}


@router.post("/me/attempts/{attempt_id}/submit", response_model=ExamResult)
def submit_my_attempt(
    attempt_id: int,
    payload: ExamSubmitRequest,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> ExamResult:
    attempt, exam, _enrollment = _owned_attempt(db, attempt_id, current_user)
    if attempt.status == "submitted":
        return _result_payload(db, attempt, exam)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=409, detail="This attempt is not in progress")
    if _auto_submit_if_expired(db, attempt, exam):
        # The timer ran out first. Grade the answers that were already saved
        # and ignore anything in this late payload.
        return _result_payload(db, attempt, exam)
    _apply_answers(db, attempt, exam, payload.answers)
    _grade_attempt(db, attempt, exam, auto=payload.auto)
    db.commit()
    db.refresh(attempt)
    return _result_payload(db, attempt, exam)


@router.get("/me/attempts/{attempt_id}/result", response_model=ExamResult)
def get_my_result(
    attempt_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> ExamResult:
    attempt, exam, _enrollment = _owned_attempt(db, attempt_id, current_user)
    _auto_submit_if_expired(db, attempt, exam)
    return _result_payload(db, attempt, exam)
