from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import DatabaseSession, require_module, require_roles
from app.models.batch import Batch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.lms import (
    Assignment,
    AssignmentSubmission,
    CourseModule,
    Lesson,
    LessonProgress,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
)
from app.models.student import Student
from app.models.user import User
from app.schemas.lms import (
    AssignmentCreate,
    AssignmentGradeRequest,
    AssignmentResponse,
    AssignmentSubmissionSummary,
    AssignmentUpdate,
    CourseContentResponse,
    EnrollmentProgressRow,
    LessonCreate,
    LessonProgressResponse,
    LessonProgressUpdate,
    LessonResponse,
    LessonUpdate,
    LmsCourseSummary,
    ModuleCreate,
    ModuleResponse,
    ModuleUpdate,
    ProgressResponse,
    QuizAnswerCreate,
    QuizAttemptSummary,
    QuizCreate,
    QuizQuestionCreate,
    QuizQuestionResponse,
    QuizResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuizUpdate,
    StudentAssignment,
    StudentLearningEnrollment,
    StudentLearningResponse,
    StudentLesson,
    StudentModule,
    StudentQuizQuestion,
    StudentQuizSummary,
    StudentQuizTake,
    StudentSubmission,
)


router = APIRouter(prefix="/api/lms", tags=["LMS"])
LmsAccess = require_module("lms")
StaffUser = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff")
StudentUser = require_roles("Student")

ASSIGNMENT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "lms" / "assignments"
LESSON_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "lms" / "lessons"
MAX_SUBMISSION_SIZE = 10 * 1024 * 1024
SUBMISSION_EXTENSIONS = {
    ".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".txt", ".csv", ".dwg", ".dxf", ".py", ".js", ".sql",
}
LESSON_UPLOAD_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/jpg": ".jpg"}
MAX_LESSON_UPLOAD_SIZE = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def _course_query_for_user(db: DatabaseSession, current_user: User):
    """Return course ids the user may manage or view through the LMS."""
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
    scope = _course_query_for_user(db, current_user)
    if scope is None:
        return
    if db.scalar(scope.where(Batch.course_id == course_id).limit(1)) is None:
        raise HTTPException(
            status_code=403,
            detail="You can manage content only for courses assigned to you or your branch.",
        )


def _assert_student_enrollment(
    db: DatabaseSession, current_user: User, course_id: int
) -> tuple[Student, Enrollment]:
    student = db.scalar(
        select(Student).where(Student.user_id == current_user.id, Student.is_active.is_(True))
    )
    if student is None:
        raise HTTPException(status_code=403, detail="No active student profile is linked to this account")
    enrollment = db.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.batch).joinedload(Batch.course))
        .where(
            Enrollment.student_id == student.id,
            Enrollment.status.in_(("active", "completed")),
        )
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Batch.course_id == course_id)
        .order_by(Enrollment.admission_date.desc())
    )
    if enrollment is None:
        raise HTTPException(status_code=403, detail="You are not enrolled in this course")
    return student, enrollment


def _module_response(module: CourseModule) -> ModuleResponse:
    return ModuleResponse(
        id=module.id,
        course_id=module.course_id,
        title=module.title,
        description=module.description,
        position=module.position,
        is_published=module.is_published,
        created_at=module.created_at,
        lessons=[LessonResponse.model_validate(lesson) for lesson in module.lessons],
    )


def _assignment_response(db: DatabaseSession, assignment: Assignment) -> AssignmentResponse:
    rows = db.execute(
        select(AssignmentSubmission, Enrollment, Student)
        .join(Enrollment, AssignmentSubmission.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .where(AssignmentSubmission.assignment_id == assignment.id)
        .order_by(Student.full_name)
    ).all()
    submissions = [
        AssignmentSubmissionSummary(
            id=submission.id,
            enrollment_id=submission.enrollment_id,
            student_name=student.full_name,
            student_code=student.student_code,
            status=submission.status,
            marks=submission.marks,
            grade=submission.grade,
            feedback=submission.feedback,
            file_url=submission.file_url,
            file_name=submission.file_name,
            text_answer=submission.text_answer,
            submitted_at=submission.submitted_at,
            graded_at=submission.graded_at,
        )
        for submission, _enrollment, student in rows
    ]
    return AssignmentResponse(
        id=assignment.id,
        course_id=assignment.course_id,
        module_id=assignment.module_id,
        title=assignment.title,
        description=assignment.description,
        instructions=assignment.instructions,
        due_date=assignment.due_date,
        max_marks=assignment.max_marks,
        attachment_url=assignment.attachment_url,
        is_published=assignment.is_published,
        created_at=assignment.created_at,
        submissions=submissions,
    )


def _quiz_response(db: DatabaseSession, quiz: Quiz) -> QuizResponse:
    rows = db.execute(
        select(QuizAttempt, Student)
        .join(Enrollment, QuizAttempt.enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
        .where(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.submitted_at.is_not(None),
        )
        .order_by(QuizAttempt.id.desc())
    ).all()
    return QuizResponse(
        id=quiz.id,
        course_id=quiz.course_id,
        module_id=quiz.module_id,
        title=quiz.title,
        description=quiz.description,
        quiz_type=quiz.quiz_type,
        pass_percentage=quiz.pass_percentage,
        time_limit_minutes=quiz.time_limit_minutes,
        is_published=quiz.is_published,
        created_at=quiz.created_at,
        questions=[QuizQuestionResponse.model_validate(question) for question in quiz.questions],
        attempts=[
            QuizAttemptSummary(
                id=attempt.id,
                enrollment_id=attempt.enrollment_id,
                student_name=student.full_name,
                score=attempt.score,
                total_marks=attempt.total_marks,
                percentage=attempt.percentage,
                passed=attempt.passed,
                submitted_at=attempt.submitted_at,
            )
            for attempt, student in rows
        ],
    )


# ---------------------------------------------------------------------------
# Course content management
# ---------------------------------------------------------------------------

@router.get("/courses", response_model=list[LmsCourseSummary], dependencies=[Depends(LmsAccess)])
def list_lms_courses(
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
    include_inactive: bool = Query(default=False),
) -> list[LmsCourseSummary]:
    query = select(Course).order_by(Course.name)
    scope = _course_query_for_user(db, current_user)
    if scope is not None:
        query = query.where(Course.id.in_(scope))
    if not include_inactive:
        query = query.where(Course.is_active.is_(True))
    courses = db.scalars(query).all()
    summaries: list[LmsCourseSummary] = []
    for course in courses:
        module_ids = select(CourseModule.id).where(CourseModule.course_id == course.id)
        module_count = db.scalar(
            select(func.count(CourseModule.id)).where(CourseModule.course_id == course.id)
        ) or 0
        lesson_count = db.scalar(
            select(func.count(Lesson.id)).where(Lesson.module_id.in_(module_ids))
        ) or 0
        assignment_count = db.scalar(
            select(func.count(Assignment.id)).where(Assignment.course_id == course.id)
        ) or 0
        quiz_count = db.scalar(
            select(func.count(Quiz.id)).where(Quiz.course_id == course.id)
        ) or 0
        enrollment_count = db.scalar(
            select(func.count(Enrollment.id))
            .join(Batch, Enrollment.batch_id == Batch.id)
            .where(Batch.course_id == course.id, Enrollment.status.in_(("active", "completed")))
        ) or 0
        summaries.append(
            LmsCourseSummary(
                id=course.id,
                name=course.name,
                code=course.code,
                duration_months=course.duration_months,
                is_active=course.is_active,
                module_count=module_count,
                lesson_count=lesson_count,
                assignment_count=assignment_count,
                quiz_count=quiz_count,
                enrollment_count=enrollment_count,
            )
        )
    return summaries


@router.get(
    "/courses/{course_id}/content",
    response_model=CourseContentResponse,
    dependencies=[Depends(LmsAccess)],
)
def get_course_content(
    course_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> CourseContentResponse:
    course = _get_course(db, course_id)
    _assert_course_access(db, current_user, course_id)
    modules = db.scalars(
        select(CourseModule)
        .options(joinedload(CourseModule.lessons))
        .where(CourseModule.course_id == course_id)
        .order_by(CourseModule.position, CourseModule.id)
    ).unique().all()
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.course_id == course_id)
        .order_by(Assignment.created_at.desc())
    ).all()
    quizzes = db.scalars(
        select(Quiz)
        .options(joinedload(Quiz.questions))
        .where(Quiz.course_id == course_id)
        .order_by(Quiz.created_at.desc())
    ).unique().all()
    return CourseContentResponse(
        course_id=course.id,
        course_name=course.name,
        course_code=course.code,
        duration_months=course.duration_months,
        modules=[_module_response(module) for module in modules],
        assignments=[_assignment_response(db, assignment) for assignment in assignments],
        quizzes=[_quiz_response(db, quiz) for quiz in quizzes],
    )


@router.get(
    "/courses/{course_id}/progress",
    response_model=ProgressResponse,
    dependencies=[Depends(LmsAccess)],
)
def get_course_progress(
    course_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> ProgressResponse:
    course = _get_course(db, course_id)
    _assert_course_access(db, current_user, course_id)
    module_ids = select(CourseModule.id).where(
        CourseModule.course_id == course_id, CourseModule.is_published.is_(True)
    )
    lesson_ids = select(Lesson.id).where(
        Lesson.module_id.in_(module_ids), Lesson.is_published.is_(True)
    )
    total_lessons = int(db.scalar(select(func.count(Lesson.id)).where(Lesson.id.in_(lesson_ids))) or 0)
    assignment_ids = select(Assignment.id).where(
        Assignment.course_id == course_id, Assignment.is_published.is_(True)
    )
    rows = db.execute(
        select(Enrollment, Student, Batch)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Batch.course_id == course_id, Enrollment.status.in_(("active", "completed")))
        .order_by(Student.full_name)
    ).all()
    result: list[EnrollmentProgressRow] = []
    for enrollment, student, batch in rows:
        completed, seconds = db.execute(
            select(
                func.count(LessonProgress.id),
                func.coalesce(func.sum(LessonProgress.time_spent_seconds), 0),
            ).where(
                LessonProgress.enrollment_id == enrollment.id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.status == "completed",
            )
        ).one()
        submitted = int(
            db.scalar(
                select(func.count(AssignmentSubmission.id)).where(
                    AssignmentSubmission.enrollment_id == enrollment.id,
                    AssignmentSubmission.assignment_id.in_(assignment_ids),
                )
            )
            or 0
        )
        graded = int(
            db.scalar(
                select(func.count(AssignmentSubmission.id)).where(
                    AssignmentSubmission.enrollment_id == enrollment.id,
                    AssignmentSubmission.assignment_id.in_(assignment_ids),
                    AssignmentSubmission.status == "graded",
                )
            )
            or 0
        )
        average_quiz = db.scalar(
            select(func.avg(QuizAttempt.percentage))
            .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
            .where(
                QuizAttempt.enrollment_id == enrollment.id,
                QuizAttempt.submitted_at.is_not(None),
                Quiz.course_id == course_id,
            )
        )
        completed_count = int(completed or 0)
        result.append(
            EnrollmentProgressRow(
                enrollment_id=enrollment.id,
                student_id=student.id,
                student_name=student.full_name,
                student_code=student.student_code,
                batch_name=batch.name,
                status=enrollment.status,
                total_lessons=total_lessons,
                completed_lessons=completed_count,
                progress_percentage=round((completed_count / total_lessons) * 100, 2) if total_lessons else 0.0,
                time_spent_seconds=int(seconds or 0),
                assignments_submitted=submitted,
                assignments_graded=graded,
                average_quiz_percentage=round(float(average_quiz), 2) if average_quiz is not None else None,
            )
        )
    return ProgressResponse(
        course_id=course.id,
        course_name=course.name,
        total_lessons=total_lessons,
        rows=result,
    )


@router.post(
    "/modules",
    response_model=ModuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(LmsAccess)],
)
def create_module(
    payload: ModuleCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> ModuleResponse:
    _assert_course_access(db, current_user, payload.course_id)
    module = CourseModule(**payload.model_dump())
    db.add(module)
    db.commit()
    db.refresh(module)
    return _module_response(module)


@router.patch("/modules/{module_id}", response_model=ModuleResponse, dependencies=[Depends(LmsAccess)])
def update_module(
    module_id: int,
    payload: ModuleUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> ModuleResponse:
    module = db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    _assert_course_access(db, current_user, module.course_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(module, field, value)
    db.commit()
    db.refresh(module)
    return _module_response(module)


@router.delete("/modules/{module_id}", dependencies=[Depends(LmsAccess)])
def delete_module(
    module_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    module = db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    _assert_course_access(db, current_user, module.course_id)
    db.delete(module)
    db.commit()
    return {"message": "Module deleted"}


@router.post(
    "/modules/{module_id}/lessons",
    response_model=LessonResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(LmsAccess)],
)
def create_lesson(
    module_id: int,
    payload: LessonCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> LessonResponse:
    module = db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    _assert_course_access(db, current_user, module.course_id)
    lesson = Lesson(module_id=module_id, **payload.model_dump())
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return LessonResponse.model_validate(lesson)


@router.post(
    "/lessons/{lesson_id}/file",
    response_model=LessonResponse,
    dependencies=[Depends(LmsAccess)],
)
async def upload_lesson_file(
    lesson_id: int,
    db: DatabaseSession,
    file: UploadFile = File(...),
    current_user: User = Depends(StaffUser),
) -> LessonResponse:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _assert_course_access(db, current_user, lesson.module.course_id)
    extension = LESSON_UPLOAD_TYPES.get((file.content_type or "").lower())
    if extension is None:
        raise HTTPException(status_code=400, detail="Lesson files must be PDF or JPEG images")
    data = await file.read()
    if not data or len(data) > MAX_LESSON_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="The lesson file must be 10 MB or smaller")
    directory = LESSON_UPLOAD_DIR / str(lesson.module.course_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"lesson-{lesson.id}-{uuid4().hex}{extension}"
    (directory / filename).write_bytes(data)
    lesson.content_url = f"/uploads/lms/lessons/{lesson.module.course_id}/{filename}"
    lesson.lesson_type = "pdf" if extension == ".pdf" else "file"
    db.commit()
    db.refresh(lesson)
    return LessonResponse.model_validate(lesson)


@router.patch("/lessons/{lesson_id}", response_model=LessonResponse, dependencies=[Depends(LmsAccess)])
def update_lesson(
    lesson_id: int,
    payload: LessonUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> LessonResponse:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _assert_course_access(db, current_user, lesson.module.course_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lesson, field, value)
    db.commit()
    db.refresh(lesson)
    return LessonResponse.model_validate(lesson)


@router.delete("/lessons/{lesson_id}", dependencies=[Depends(LmsAccess)])
def delete_lesson(
    lesson_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _assert_course_access(db, current_user, lesson.module.course_id)
    db.delete(lesson)
    db.commit()
    return {"message": "Lesson deleted"}


@router.post(
    "/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(LmsAccess)],
)
def create_assignment(
    payload: AssignmentCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> AssignmentResponse:
    _assert_course_access(db, current_user, payload.course_id)
    if payload.module_id is not None:
        module = db.get(CourseModule, payload.module_id)
        if module is None or module.course_id != payload.course_id:
            raise HTTPException(status_code=400, detail="Module does not belong to this course")
    assignment = Assignment(**payload.model_dump(), created_by_id=current_user.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return _assignment_response(db, assignment)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse, dependencies=[Depends(LmsAccess)])
def update_assignment(
    assignment_id: int,
    payload: AssignmentUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> AssignmentResponse:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _assert_course_access(db, current_user, assignment.course_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return _assignment_response(db, assignment)


@router.delete("/assignments/{assignment_id}", dependencies=[Depends(LmsAccess)])
def delete_assignment(
    assignment_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _assert_course_access(db, current_user, assignment.course_id)
    db.delete(assignment)
    db.commit()
    return {"message": "Assignment deleted"}


@router.post(
    "/assignments/{assignment_id}/submissions/{submission_id}/grade",
    response_model=AssignmentResponse,
    dependencies=[Depends(LmsAccess)],
)
def grade_submission(
    assignment_id: int,
    submission_id: int,
    payload: AssignmentGradeRequest,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> AssignmentResponse:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _assert_course_access(db, current_user, assignment.course_id)
    submission = db.get(AssignmentSubmission, submission_id)
    if submission is None or submission.assignment_id != assignment_id:
        raise HTTPException(status_code=404, detail="Submission not found")
    if payload.marks > assignment.max_marks:
        raise HTTPException(status_code=400, detail="Marks cannot exceed the assignment maximum")
    percentage = (payload.marks / assignment.max_marks) * 100 if assignment.max_marks else 0
    grade = payload.grade
    if grade is None:
        if percentage >= 90:
            grade = "A+"
        elif percentage >= 80:
            grade = "A"
        elif percentage >= 70:
            grade = "B+"
        elif percentage >= 60:
            grade = "B"
        elif percentage >= 50:
            grade = "C"
        elif percentage >= 40:
            grade = "D"
        else:
            grade = "F"
    submission.marks = payload.marks
    submission.grade = grade
    submission.feedback = payload.feedback
    submission.status = "graded"
    submission.graded_by_id = current_user.id
    submission.graded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(assignment)
    return _assignment_response(db, assignment)


@router.post(
    "/quizzes",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(LmsAccess)],
)
def create_quiz(
    payload: QuizCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuizResponse:
    _assert_course_access(db, current_user, payload.course_id)
    data = payload.model_dump(exclude={"questions"})
    quiz = Quiz(**data)
    db.add(quiz)
    db.flush()
    for question in payload.questions:
        db.add(QuizQuestion(quiz_id=quiz.id, **question.model_dump()))
    db.commit()
    db.refresh(quiz)
    return _quiz_response(db, quiz)


@router.patch("/quizzes/{quiz_id}", response_model=QuizResponse, dependencies=[Depends(LmsAccess)])
def update_quiz(
    quiz_id: int,
    payload: QuizUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuizResponse:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _assert_course_access(db, current_user, quiz.course_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(quiz, field, value)
    db.commit()
    db.refresh(quiz)
    return _quiz_response(db, quiz)


@router.delete("/quizzes/{quiz_id}", dependencies=[Depends(LmsAccess)])
def delete_quiz(
    quiz_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _assert_course_access(db, current_user, quiz.course_id)
    db.delete(quiz)
    db.commit()
    return {"message": "Quiz deleted"}


@router.post(
    "/quizzes/{quiz_id}/questions",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(LmsAccess)],
)
def add_quiz_question(
    quiz_id: int,
    payload: QuizQuestionCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> QuizResponse:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _assert_course_access(db, current_user, quiz.course_id)
    db.add(QuizQuestion(quiz_id=quiz_id, **payload.model_dump()))
    db.commit()
    db.refresh(quiz)
    return _quiz_response(db, quiz)


@router.delete("/quizzes/{quiz_id}/questions/{question_id}", dependencies=[Depends(LmsAccess)])
def delete_quiz_question(
    quiz_id: int,
    question_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StaffUser),
) -> dict[str, str]:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _assert_course_access(db, current_user, quiz.course_id)
    question = db.get(QuizQuestion, question_id)
    if question is None or question.quiz_id != quiz_id:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()
    return {"message": "Question deleted"}


# ---------------------------------------------------------------------------
# Student learning
# ---------------------------------------------------------------------------

def _student_course_payload(
    db: DatabaseSession, student: Student, enrollment: Enrollment
) -> StudentLearningEnrollment:
    course = enrollment.batch.course
    modules = db.scalars(
        select(CourseModule)
        .options(joinedload(CourseModule.lessons))
        .where(
            CourseModule.course_id == course.id,
            CourseModule.is_published.is_(True),
        )
        .order_by(CourseModule.position, CourseModule.id)
    ).unique().all()
    progress_rows = db.scalars(
        select(LessonProgress).where(LessonProgress.enrollment_id == enrollment.id)
    ).all()
    progress = {row.lesson_id: row for row in progress_rows}

    assignments = db.scalars(
        select(Assignment).where(
            Assignment.course_id == course.id,
            Assignment.is_published.is_(True),
        ).order_by(Assignment.due_date.is_(None), Assignment.due_date, Assignment.id)
    ).all()
    submission_rows = db.scalars(
        select(AssignmentSubmission).where(AssignmentSubmission.enrollment_id == enrollment.id)
    ).all()
    submissions = {row.assignment_id: row for row in submission_rows}

    quizzes = db.scalars(
        select(Quiz)
        .options(joinedload(Quiz.questions))
        .where(Quiz.course_id == course.id, Quiz.is_published.is_(True))
        .order_by(Quiz.id)
    ).unique().all()
    attempt_rows = db.scalars(
        select(QuizAttempt).where(
            QuizAttempt.enrollment_id == enrollment.id,
            QuizAttempt.submitted_at.is_not(None),
        )
    ).all()
    attempts: dict[int, list[QuizAttempt]] = {}
    for attempt in attempt_rows:
        attempts.setdefault(attempt.quiz_id, []).append(attempt)

    total_lessons = 0
    completed_lessons = 0
    time_spent = 0
    student_modules: list[StudentModule] = []
    for module in modules:
        student_lessons: list[StudentLesson] = []
        for lesson in module.lessons:
            if not lesson.is_published:
                continue
            row = progress.get(lesson.id)
            total_lessons += 1
            if row is not None and row.status == "completed":
                completed_lessons += 1
            if row is not None:
                time_spent += row.time_spent_seconds
            student_lessons.append(
                StudentLesson(
                    id=lesson.id,
                    title=lesson.title,
                    description=lesson.description,
                    lesson_type=lesson.lesson_type,
                    content_url=lesson.content_url,
                    content_text=lesson.content_text,
                    duration_minutes=lesson.duration_minutes,
                    status=row.status if row else "not_started",
                    time_spent_seconds=row.time_spent_seconds if row else 0,
                    completed_at=row.completed_at if row else None,
                )
            )
        student_modules.append(
            StudentModule(
                id=module.id,
                title=module.title,
                description=module.description,
                position=module.position,
                lessons=student_lessons,
            )
        )

    student_assignments = []
    for assignment in assignments:
        submission = submissions.get(assignment.id)
        student_assignments.append(
            StudentAssignment(
                id=assignment.id,
                module_id=assignment.module_id,
                title=assignment.title,
                description=assignment.description,
                instructions=assignment.instructions,
                due_date=assignment.due_date,
                max_marks=assignment.max_marks,
                attachment_url=assignment.attachment_url,
                submission=(
                    StudentSubmission(
                        status=submission.status,
                        marks=submission.marks,
                        grade=submission.grade,
                        feedback=submission.feedback,
                        file_url=submission.file_url,
                        file_name=submission.file_name,
                        text_answer=submission.text_answer,
                        submitted_at=submission.submitted_at,
                        graded_at=submission.graded_at,
                    )
                    if submission
                    else None
                ),
            )
        )

    student_quizzes = []
    for quiz in quizzes:
        quiz_attempts = attempts.get(quiz.id, [])
        best = max((attempt.percentage for attempt in quiz_attempts), default=None)
        student_quizzes.append(
            StudentQuizSummary(
                id=quiz.id,
                module_id=quiz.module_id,
                title=quiz.title,
                description=quiz.description,
                quiz_type=quiz.quiz_type,
                pass_percentage=quiz.pass_percentage,
                time_limit_minutes=quiz.time_limit_minutes,
                question_count=len(quiz.questions),
                best_percentage=round(best, 2) if best is not None else None,
                passed=any(attempt.passed for attempt in quiz_attempts),
                attempts=len(quiz_attempts),
            )
        )

    return StudentLearningEnrollment(
        enrollment_id=enrollment.id,
        enrollment_code=enrollment.enrollment_code,
        course_id=course.id,
        course_name=course.name,
        batch_name=enrollment.batch.name,
        status=enrollment.status,
        progress_percentage=round((completed_lessons / total_lessons) * 100, 2) if total_lessons else 0.0,
        total_lessons=total_lessons,
        completed_lessons=completed_lessons,
        time_spent_seconds=time_spent,
        modules=student_modules,
        assignments=student_assignments,
        quizzes=student_quizzes,
    )


@router.get("/me/learning", response_model=StudentLearningResponse)
def get_my_learning(
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> StudentLearningResponse:
    student = db.scalar(
        select(Student).where(Student.user_id == current_user.id, Student.is_active.is_(True))
    )
    if student is None:
        raise HTTPException(status_code=403, detail="No active student profile is linked to this account")
    enrollments = db.scalars(
        select(Enrollment)
        .options(joinedload(Enrollment.batch).joinedload(Batch.course))
        .where(
            Enrollment.student_id == student.id,
            Enrollment.status.in_(("active", "completed")),
        )
        .order_by(Enrollment.admission_date.desc())
    ).unique().all()
    return StudentLearningResponse(
        enrollments=[
            _student_course_payload(db, student, enrollment) for enrollment in enrollments
        ]
    )


@router.post("/me/lessons/{lesson_id}/complete", response_model=LessonProgressResponse)
def complete_lesson(
    lesson_id: int,
    payload: LessonProgressUpdate,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> LessonProgressResponse:
    lesson = db.scalar(
        select(Lesson)
        .options(joinedload(Lesson.module))
        .where(Lesson.id == lesson_id, Lesson.is_published.is_(True))
    )
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _student, enrollment = _assert_student_enrollment(
        db, current_user, lesson.module.course_id
    )
    record = db.scalar(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if record is None:
        record = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            status="completed",
            time_spent_seconds=payload.time_spent_seconds,
            completed_at=now,
        )
        db.add(record)
    else:
        record.status = "completed"
        record.time_spent_seconds += payload.time_spent_seconds
        record.completed_at = record.completed_at or now
    db.commit()
    db.refresh(record)
    return LessonProgressResponse(
        lesson_id=record.lesson_id,
        enrollment_id=record.enrollment_id,
        status=record.status,
        time_spent_seconds=record.time_spent_seconds,
        completed_at=record.completed_at,
    )


@router.post("/me/assignments/{assignment_id}/submit", response_model=StudentAssignment)
async def submit_assignment(
    assignment_id: int,
    db: DatabaseSession,
    file: UploadFile | None = File(default=None),
    text_answer: str = Form(default=""),
    current_user: User = Depends(StudentUser),
) -> StudentAssignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or not assignment.is_published:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _student, enrollment = _assert_student_enrollment(
        db, current_user, assignment.course_id
    )
    existing = db.scalar(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment.id,
            AssignmentSubmission.enrollment_id == enrollment.id,
        )
    )
    if existing is not None and existing.status == "graded":
        raise HTTPException(status_code=409, detail="This submission has already been graded")

    file_url = None
    file_name = None
    if file is not None:
        original_name = Path(file.filename or "assignment").name
        extension = Path(original_name).suffix.lower()
        if extension not in SUBMISSION_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Upload a PDF, ZIP, Office document, image, drawing or code file",
            )
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")
        if len(data) > MAX_SUBMISSION_SIZE:
            raise HTTPException(status_code=400, detail="The file must be 10 MB or smaller")
        directory = ASSIGNMENT_UPLOAD_DIR / str(assignment.id) / str(enrollment.id)
        directory.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}{extension}"
        (directory / stored_name).write_bytes(data)
        file_url = f"/uploads/lms/assignments/{assignment.id}/{enrollment.id}/{stored_name}"
        file_name = original_name

    if not text_answer.strip() and file_url is None:
        raise HTTPException(status_code=400, detail="Add an answer or attach a file")

    if existing is None:
        existing = AssignmentSubmission(
            assignment_id=assignment.id,
            enrollment_id=enrollment.id,
        )
        db.add(existing)
    existing.text_answer = text_answer.strip() or None
    if file_url is not None:
        existing.file_url = file_url
        existing.file_name = file_name
    existing.status = "submitted"
    existing.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(existing)
    return StudentAssignment(
        id=assignment.id,
        module_id=assignment.module_id,
        title=assignment.title,
        description=assignment.description,
        instructions=assignment.instructions,
        due_date=assignment.due_date,
        max_marks=assignment.max_marks,
        attachment_url=assignment.attachment_url,
        submission=StudentSubmission(
            status=existing.status,
            marks=existing.marks,
            grade=existing.grade,
            feedback=existing.feedback,
            file_url=existing.file_url,
            file_name=existing.file_name,
            text_answer=existing.text_answer,
            submitted_at=existing.submitted_at,
            graded_at=existing.graded_at,
        ),
    )


def _quiz_total_marks(quiz: Quiz) -> Decimal:
    return sum((question.marks for question in quiz.questions), Decimal("0"))


def _quiz_deadline(quiz: Quiz, started_at: datetime) -> datetime | None:
    if not quiz.time_limit_minutes:
        return None
    return started_at + timedelta(minutes=quiz.time_limit_minutes)


def _resume_quiz_attempt(
    db: DatabaseSession,
    quiz: Quiz,
    enrollment: Enrollment,
) -> QuizAttempt:
    """Return the student's open attempt, starting one if needed.

    Reusing the open row keeps ``started_at`` stable, so closing and reopening
    the quiz cannot reset the time limit or create unlimited attempts.
    """
    attempt = db.scalar(
        select(QuizAttempt)
        .where(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.enrollment_id == enrollment.id,
            QuizAttempt.submitted_at.is_(None),
        )
        .order_by(QuizAttempt.id.desc())
    )
    if attempt is not None:
        return attempt

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        enrollment_id=enrollment.id,
        score=Decimal("0"),
        total_marks=_quiz_total_marks(quiz),
        percentage=0,
        passed=False,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        submitted_at=None,
    )
    db.add(attempt)
    db.flush()
    return attempt


def _finalize_expired_attempt(
    db: DatabaseSession, attempt: QuizAttempt, quiz: Quiz, deadline: datetime
) -> None:
    """Close an attempt that ran past its deadline without accepting answers."""
    attempt.score = Decimal("0")
    attempt.total_marks = _quiz_total_marks(quiz)
    attempt.percentage = 0
    attempt.passed = False
    attempt.submitted_at = deadline
    db.flush()


@router.get("/me/quizzes/{quiz_id}", response_model=StudentQuizTake)
def get_my_quiz(
    quiz_id: int,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> StudentQuizTake:
    quiz = db.scalar(
        select(Quiz).options(joinedload(Quiz.questions)).where(Quiz.id == quiz_id)
    )
    if quiz is None or not quiz.is_published:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _student, enrollment = _assert_student_enrollment(db, current_user, quiz.course_id)
    if not quiz.questions:
        raise HTTPException(status_code=400, detail="This quiz has no questions yet")
    attempt = _resume_quiz_attempt(db, quiz, enrollment)
    deadline = _quiz_deadline(quiz, attempt.started_at)
    if deadline is not None and datetime.now(timezone.utc).replace(tzinfo=None) > deadline:
        # The previous sitting timed out. Close it as an expired attempt and
        # open a fresh one so the student can still take the quiz.
        _finalize_expired_attempt(db, attempt, quiz, deadline)
        attempt = _resume_quiz_attempt(db, quiz, enrollment)
        deadline = _quiz_deadline(quiz, attempt.started_at)
    db.commit()
    db.refresh(attempt)
    return StudentQuizTake(
        id=quiz.id,
        attempt_id=attempt.id,
        title=quiz.title,
        description=quiz.description,
        pass_percentage=quiz.pass_percentage,
        time_limit_minutes=quiz.time_limit_minutes,
        started_at=attempt.started_at,
        expires_at=deadline,
        questions=[
            StudentQuizQuestion(
                id=question.id,
                question_text=question.question_text,
                option_a=question.option_a,
                option_b=question.option_b,
                option_c=question.option_c,
                option_d=question.option_d,
                marks=question.marks,
                position=question.position,
            )
            for question in quiz.questions
        ],
    )


@router.post("/me/quizzes/{quiz_id}/submit", response_model=QuizSubmitResponse)
def submit_quiz(
    quiz_id: int,
    payload: QuizSubmitRequest,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> QuizSubmitResponse:
    quiz = db.scalar(
        select(Quiz).options(joinedload(Quiz.questions)).where(Quiz.id == quiz_id)
    )
    if quiz is None or not quiz.is_published:
        raise HTTPException(status_code=404, detail="Quiz not found")
    _student, enrollment = _assert_student_enrollment(db, current_user, quiz.course_id)
    if not quiz.questions:
        raise HTTPException(status_code=400, detail="This quiz has no questions yet")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if payload.attempt_id is not None:
        attempt = db.get(QuizAttempt, payload.attempt_id)
        if (
            attempt is None
            or attempt.quiz_id != quiz.id
            or attempt.enrollment_id != enrollment.id
        ):
            raise HTTPException(status_code=404, detail="Quiz attempt not found")
        if attempt.submitted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This quiz attempt has already been submitted",
            )
    else:
        attempt = _resume_quiz_attempt(db, quiz, enrollment)

    total_marks = _quiz_total_marks(quiz)
    deadline = _quiz_deadline(quiz, attempt.started_at)
    if deadline is not None and now > deadline:
        # Late answers are not accepted; the sitting is closed with no credit.
        _finalize_expired_attempt(db, attempt, quiz, deadline)
        db.commit()
        return QuizSubmitResponse(
            attempt_id=attempt.id,
            score=Decimal("0"),
            total_marks=total_marks,
            percentage=0.0,
            passed=False,
            correct_answers=0,
            total_questions=len(quiz.questions),
        )

    answers = {answer.question_id: answer.selected_option for answer in payload.answers}
    attempt.total_marks = total_marks
    score = Decimal("0")
    correct = 0
    for question in quiz.questions:
        selected = answers.get(question.id)
        is_correct = selected is not None and selected == question.correct_option
        if is_correct:
            score += question.marks
            correct += 1
        db.add(
            QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_option=selected,
                is_correct=is_correct,
                marks_awarded=question.marks if is_correct else Decimal("0"),
            )
        )
    percentage = (
        float((score / attempt.total_marks) * 100) if attempt.total_marks else 0.0
    )
    attempt.score = score
    attempt.total_marks = total_marks
    attempt.percentage = round(percentage, 2)
    attempt.passed = percentage >= quiz.pass_percentage
    attempt.submitted_at = now
    db.commit()
    return QuizSubmitResponse(
        attempt_id=attempt.id,
        score=score,
        total_marks=attempt.total_marks,
        percentage=attempt.percentage,
        passed=attempt.passed,
        correct_answers=correct,
        total_questions=len(quiz.questions),
    )
