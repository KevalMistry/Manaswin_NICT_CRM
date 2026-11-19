from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    require_module,
    require_roles,
)
from app.models.batch import Batch
from app.models.enrollment import Enrollment
from app.models.examination import ExamMark, ExamSubject, Examination
from app.schemas.examination import (
    ExamMarkCreate,
    ExamMarkResponse,
    ExamMarkUpdate,
    ExaminationCreate,
    ExaminationResponse,
)


router = APIRouter(prefix="/api/examinations", tags=["Examinations"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff")
ExaminationsAccess = require_module("examinations")


def check_batch_access(current_user, batch: Batch) -> None:
    check_branch_access(current_user, batch.branch_id)
    if current_user.role.name == "Faculty" and batch.faculty_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Faculty can manage only examinations for assigned batches",
        )


def calculate_grade(marks: Decimal, max_marks: Decimal, pass_marks: Decimal) -> str:
    if marks < pass_marks:
        return "F"
    percentage = (marks / max_marks) * 100
    if percentage >= 90:
        return "A+"
    if percentage >= 80:
        return "A"
    if percentage >= 70:
        return "B+"
    if percentage >= 60:
        return "B"
    if percentage >= 50:
        return "C"
    return "D"


@router.post("", response_model=ExaminationResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ExaminationsAccess)])
def create_examination(
    payload: ExaminationCreate,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> Examination:
    batch = db.get(Batch, payload.batch_id)
    if batch is None or not batch.is_active:
        raise HTTPException(status_code=400, detail="Active batch does not exist")
    check_batch_access(current_user, batch)
    subject_names = [subject.name.strip().casefold() for subject in payload.subjects]
    if len(subject_names) != len(set(subject_names)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subject names must be unique within an examination",
        )
    examination = Examination(
        name=payload.name,
        batch_id=payload.batch_id,
        exam_date=payload.exam_date,
        subjects=[ExamSubject(**subject.model_dump()) for subject in payload.subjects],
    )
    db.add(examination)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Examination could not be created because a subject name already exists",
        ) from None
    db.refresh(examination)
    return examination


@router.get("", response_model=list[ExaminationResponse], dependencies=[Depends(ExaminationsAccess)])
def list_examinations(
    db: DatabaseSession,
    current_user=Depends(AdminUser),
    batch_id: int | None = Query(default=None),
    include_unpublished: bool = True,
) -> list[Examination]:
    query = select(Examination).join(Batch)
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Batch.branch_id == scope)
    if current_user.role.name == "Faculty":
        query = query.where(Batch.faculty_id == current_user.id)
    if batch_id is not None:
        query = query.where(Examination.batch_id == batch_id)
    if not include_unpublished:
        query = query.where(Examination.is_published.is_(True))
    return list(db.scalars(query.order_by(Examination.exam_date.desc())).all())


@router.patch("/{examination_id}/publish", response_model=ExaminationResponse, dependencies=[Depends(ExaminationsAccess)])
def publish_examination(
    examination_id: int,
    db: DatabaseSession,
    current_user=Depends(require_roles("Super Admin", "Branch Admin")),
) -> Examination:
    examination = db.scalar(
        select(Examination).options(joinedload(Examination.batch)).where(
            Examination.id == examination_id
        )
    )
    if examination is None:
        raise HTTPException(status_code=404, detail="Examination not found")
    check_batch_access(current_user, examination.batch)
    examination.is_published = True
    db.commit()
    db.refresh(examination)
    return examination


@router.post("/marks", response_model=ExamMarkResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(ExaminationsAccess)])
def record_marks(
    payload: ExamMarkCreate,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> ExamMark:
    subject = db.scalar(
        select(ExamSubject)
        .options(joinedload(ExamSubject.examination).joinedload(Examination.batch))
        .where(ExamSubject.id == payload.exam_subject_id)
    )
    enrollment = db.get(Enrollment, payload.enrollment_id)
    if subject is None or enrollment is None:
        raise HTTPException(status_code=404, detail="Subject or enrollment not found")
    if subject.examination.batch_id != enrollment.batch_id:
        raise HTTPException(status_code=400, detail="Enrollment is not part of this exam batch")
    check_batch_access(current_user, subject.examination.batch)
    if payload.marks_obtained > subject.max_marks:
        raise HTTPException(status_code=400, detail="Marks cannot exceed maximum marks")
    if db.scalar(
        select(ExamMark).where(
            ExamMark.exam_subject_id == payload.exam_subject_id,
            ExamMark.enrollment_id == payload.enrollment_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Marks already recorded")
    mark = ExamMark(
        grade=calculate_grade(
            payload.marks_obtained, subject.max_marks, subject.pass_marks
        ),
        **payload.model_dump(),
    )
    db.add(mark)
    db.commit()
    db.refresh(mark)
    return mark


@router.patch("/marks/{mark_id}", response_model=ExamMarkResponse, dependencies=[Depends(ExaminationsAccess)])
def update_marks(
    mark_id: int,
    payload: ExamMarkUpdate,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> ExamMark:
    mark = db.scalar(
        select(ExamMark)
        .options(
            joinedload(ExamMark.exam_subject)
            .joinedload(ExamSubject.examination)
            .joinedload(Examination.batch)
        )
        .where(ExamMark.id == mark_id)
    )
    if mark is None:
        raise HTTPException(status_code=404, detail="Exam mark not found")
    subject = mark.exam_subject
    if subject.examination.is_published:
        raise HTTPException(status_code=400, detail="Cannot edit marks of a published examination")
    check_batch_access(current_user, subject.examination.batch)
    if payload.marks_obtained > subject.max_marks:
        raise HTTPException(status_code=400, detail="Marks cannot exceed maximum marks")
    mark.marks_obtained = payload.marks_obtained
    mark.grade = calculate_grade(payload.marks_obtained, subject.max_marks, subject.pass_marks)
    if payload.remarks is not None:
        mark.remarks = payload.remarks
    db.commit()
    db.refresh(mark)
    return mark


@router.get("/{examination_id}/marks", dependencies=[Depends(ExaminationsAccess)])
def get_examination_marks(
    examination_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> list[dict]:
    exam = db.get(Examination, examination_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Examination not found")
    batch = db.get(Batch, exam.batch_id)
    if batch:
        check_batch_access(current_user, batch)
    rows = db.execute(
        select(ExamMark)
        .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
        .where(ExamSubject.examination_id == examination_id)
    ).scalars().all()
    return [
        {
            "id": row.id,
            "exam_subject_id": row.exam_subject_id,
            "enrollment_id": row.enrollment_id,
            "marks_obtained": float(row.marks_obtained),
            "grade": row.grade,
            "remarks": row.remarks,
        }
        for row in rows
    ]


@router.get("/results/{enrollment_id}", dependencies=[Depends(ExaminationsAccess)])
def get_result(
    enrollment_id: int,
    db: DatabaseSession,
    current_user=Depends(AdminUser),
) -> dict:
    enrollment = db.scalar(
        select(Enrollment).options(joinedload(Enrollment.batch)).where(
            Enrollment.id == enrollment_id
        )
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    check_batch_access(current_user, enrollment.batch)
    rows = db.execute(
        select(ExamMark, ExamSubject, Examination)
        .join(ExamSubject, ExamMark.exam_subject_id == ExamSubject.id)
        .join(Examination, ExamSubject.examination_id == Examination.id)
        .where(
            ExamMark.enrollment_id == enrollment_id,
            Examination.is_published.is_(True),
        )
        .order_by(Examination.exam_date.desc(), ExamSubject.name)
    ).all()
    total_obtained = sum((row[0].marks_obtained for row in rows), Decimal("0"))
    total_max = sum((row[1].max_marks for row in rows), Decimal("0"))
    return {
        "enrollment_id": enrollment_id,
        "total_obtained": total_obtained,
        "total_maximum": total_max,
        "percentage": round((total_obtained / total_max) * 100, 2) if total_max else 0,
        "results": [
            {
                "examination": row[2].name,
                "subject": row[1].name,
                "marks_obtained": row[0].marks_obtained,
                "max_marks": row[1].max_marks,
                "grade": row[0].grade,
                "remarks": row[0].remarks,
            }
            for row in rows
        ],
    }
