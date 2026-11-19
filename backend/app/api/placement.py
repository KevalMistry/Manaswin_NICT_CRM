from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.api.audit import record_audit
from app.api.dependencies import DatabaseSession, branch_scope, require_module, require_roles
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.placement import Company, JobOpening, PlacementApplication
from app.models.student import Student
from app.models.user import User
from app.schemas.placement import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    JobOpeningCreate,
    JobOpeningResponse,
    JobOpeningUpdate,
    OpportunityResponse,
    PlacementSummary,
    StudentApplicationResponse,
    StudentApplyRequest,
)


staff_router = APIRouter(prefix="/api/placement", tags=["Placement Cell"])
# The placement cell is managed by staff who already work with students. It
# reuses a dedicated module key so access can be granted per role.
PlacementAccess = require_module("placement")
PlacementUser = require_roles(
    "Super Admin", "Branch Admin", "Staff", "Counsellor", "Faculty"
)

student_router = APIRouter(prefix="/api/placement-portal", tags=["Placement Portal"])
StudentUser = require_roles("Student")


def _check_branch_access(current_user: User, branch_id: int | None) -> None:
    if current_user.role.name == "Super Admin" or branch_id is None:
        return
    if current_user.branch_id is None or current_user.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this branch",
        )


def _opening_query():
    return select(JobOpening).options(
        joinedload(JobOpening.company),
        joinedload(JobOpening.branch),
        selectinload(JobOpening.courses),
        selectinload(JobOpening.applications),
    )


def _company_response(company: Company, openings_count: int) -> CompanyResponse:
    return CompanyResponse(
        id=company.id,
        name=company.name,
        industry=company.industry,
        website=company.website,
        location=company.location,
        contact_person=company.contact_person,
        contact_email=company.contact_email,
        contact_phone=company.contact_phone,
        notes=company.notes,
        is_active=company.is_active,
        openings_count=openings_count,
        created_at=company.created_at,
    )


def _opening_response(opening: JobOpening) -> JobOpeningResponse:
    return JobOpeningResponse(
        id=opening.id,
        company_id=opening.company_id,
        company_name=opening.company.name,
        title=opening.title,
        description=opening.description,
        location=opening.location,
        employment_type=opening.employment_type,
        work_mode=opening.work_mode,
        salary_min=opening.salary_min,
        salary_max=opening.salary_max,
        vacancies=opening.vacancies,
        last_date=opening.last_date,
        status=opening.status,
        branch_id=opening.branch_id,
        branch_name=opening.branch.name if opening.branch else None,
        course_ids=[course.id for course in opening.courses],
        course_names=[course.name for course in opening.courses],
        applications_count=len(opening.applications),
        created_at=opening.created_at,
    )


def _student_course_names(
    db: DatabaseSession, student_ids: list[int]
) -> dict[int, list[str]]:
    if not student_ids:
        return {}
    rows = db.execute(
        select(Enrollment.student_id, Course.name)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .join(Course, Batch.course_id == Course.id)
        .where(
            Enrollment.student_id.in_(student_ids),
            Enrollment.status.in_(("active", "completed")),
        )
        .order_by(Course.name)
    ).all()
    grouped: dict[int, list[str]] = {}
    for student_id, course_name in rows:
        names = grouped.setdefault(student_id, [])
        if course_name not in names:
            names.append(course_name)
    return grouped


def _application_response(
    application: PlacementApplication, course_names: list[str]
) -> ApplicationResponse:
    student = application.student
    return ApplicationResponse(
        id=application.id,
        job_opening_id=application.job_opening_id,
        opening_title=application.opening.title,
        company_name=application.opening.company.name,
        student_id=application.student_id,
        student_name=student.full_name,
        student_code=student.student_code,
        branch_id=student.branch_id,
        branch_name=student.branch.name if student.branch else "—",
        course_names=course_names,
        status=application.status,
        source=application.source,
        resume_url=application.resume_url,
        cover_note=application.cover_note,
        interview_date=application.interview_date,
        interview_mode=application.interview_mode,
        interview_location=application.interview_location,
        feedback=application.feedback,
        offer_salary=application.offer_salary,
        offer_date=application.offer_date,
        joining_date=application.joining_date,
        offer_letter_url=application.offer_letter_url,
        applied_at=application.applied_at,
        updated_at=application.updated_at,
    )


def _application_query():
    return select(PlacementApplication).options(
        joinedload(PlacementApplication.opening).joinedload(JobOpening.company),
        joinedload(PlacementApplication.student).joinedload(Student.branch),
    )


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------
@staff_router.get(
    "/companies",
    response_model=list[CompanyResponse],
    dependencies=[Depends(PlacementAccess)],
)
def list_companies(
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
    search: str | None = Query(default=None, max_length=120),
) -> list[CompanyResponse]:
    query = select(Company).order_by(Company.name)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Company.name.ilike(pattern),
                Company.industry.ilike(pattern),
                Company.location.ilike(pattern),
            )
        )
    companies = db.scalars(query).all()
    counts = dict(
        db.execute(
            select(JobOpening.company_id, func.count(JobOpening.id)).group_by(
                JobOpening.company_id
            )
        ).all()
    )
    return [_company_response(company, int(counts.get(company.id, 0))) for company in companies]


@staff_router.post(
    "/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PlacementAccess)],
)
def create_company(
    payload: CompanyCreate,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> CompanyResponse:
    if db.scalar(select(Company).where(Company.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="A company with this name already exists")
    company = Company(
        name=payload.name.strip(),
        industry=payload.industry,
        website=payload.website,
        location=payload.location,
        contact_person=payload.contact_person,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        notes=payload.notes,
        is_active=payload.is_active,
    )
    db.add(company)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "placement_company_created",
        "company",
        company.id,
        {"name": company.name},
    )
    db.commit()
    db.refresh(company)
    return _company_response(company, 0)


@staff_router.patch(
    "/companies/{company_id}",
    response_model=CompanyResponse,
    dependencies=[Depends(PlacementAccess)],
)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> CompanyResponse:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    if "name" in changes and changes["name"]:
        changes["name"] = changes["name"].strip()
        duplicate = db.scalar(
            select(Company).where(Company.name == changes["name"], Company.id != company.id)
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="A company with this name already exists")
    for field, value in changes.items():
        setattr(company, field, value)
    record_audit(
        db,
        current_user.id,
        "placement_company_updated",
        "company",
        company.id,
        changes,
    )
    db.commit()
    db.refresh(company)
    openings_count = db.scalar(
        select(func.count(JobOpening.id)).where(JobOpening.company_id == company.id)
    ) or 0
    return _company_response(company, int(openings_count))


@staff_router.delete(
    "/companies/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(PlacementAccess)],
)
def delete_company(
    company_id: int,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> None:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    opening_count = db.scalar(
        select(func.count(JobOpening.id)).where(JobOpening.company_id == company.id)
    ) or 0
    if opening_count:
        raise HTTPException(
            status_code=409,
            detail="Remove or reassign this company's job openings before deleting it",
        )
    record_audit(
        db,
        current_user.id,
        "placement_company_deleted",
        "company",
        company.id,
        {"name": company.name},
    )
    db.delete(company)
    db.commit()


# ---------------------------------------------------------------------------
# Job openings
# ---------------------------------------------------------------------------
def _validate_courses(db: DatabaseSession, course_ids: list[int]) -> list[Course]:
    ids = list(dict.fromkeys(course_ids))
    if not ids:
        return []
    courses = db.scalars(select(Course).where(Course.id.in_(ids))).all()
    if len(courses) != len(ids):
        raise HTTPException(status_code=404, detail="One or more courses were not found")
    return list(courses)


def _validate_company(db: DatabaseSession, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.is_active:
        raise HTTPException(status_code=400, detail="This company is inactive")
    return company


def _apply_salary_guard(payload_min, payload_max, current_min, current_max) -> None:
    minimum = payload_min if payload_min is not None else current_min
    maximum = payload_max if payload_max is not None else current_max
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(
            status_code=400, detail="Minimum salary cannot be greater than maximum salary"
        )


def _scoped_openings(query, current_user: User):
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(
            or_(JobOpening.branch_id.is_(None), JobOpening.branch_id == scope)
        )
    return query


@staff_router.get(
    "/openings",
    response_model=list[JobOpeningResponse],
    dependencies=[Depends(PlacementAccess)],
)
def list_openings(
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
    status_filter: str | None = Query(default=None, alias="status"),
    company_id: int | None = None,
) -> list[JobOpeningResponse]:
    query = _scoped_openings(_opening_query(), current_user)
    if status_filter:
        query = query.where(JobOpening.status == status_filter)
    if company_id is not None:
        query = query.where(JobOpening.company_id == company_id)
    openings = db.scalars(query.order_by(JobOpening.created_at.desc())).unique().all()
    return [_opening_response(opening) for opening in openings]


@staff_router.post(
    "/openings",
    response_model=JobOpeningResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PlacementAccess)],
)
def create_opening(
    payload: JobOpeningCreate,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> JobOpeningResponse:
    company = _validate_company(db, payload.company_id)
    branch_id = payload.branch_id
    if branch_id is None and current_user.role.name != "Super Admin":
        branch_id = current_user.branch_id
    _check_branch_access(current_user, branch_id)
    if branch_id is not None and db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    _apply_salary_guard(
        payload.salary_min, payload.salary_max, None, None
    )
    courses = _validate_courses(db, payload.course_ids)
    opening = JobOpening(
        company_id=company.id,
        title=payload.title.strip(),
        description=payload.description,
        location=payload.location or company.location,
        employment_type=payload.employment_type,
        work_mode=payload.work_mode,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        vacancies=payload.vacancies,
        last_date=payload.last_date,
        status=payload.status,
        branch_id=branch_id,
        created_by_id=current_user.id,
        courses=courses,
    )
    db.add(opening)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "placement_opening_created",
        "job_opening",
        opening.id,
        {
            "company": company.name,
            "title": opening.title,
            "course_ids": [course.id for course in courses],
        },
    )
    db.commit()
    db.refresh(opening)
    return _opening_response(opening)


@staff_router.patch(
    "/openings/{opening_id}",
    response_model=JobOpeningResponse,
    dependencies=[Depends(PlacementAccess)],
)
def update_opening(
    opening_id: int,
    payload: JobOpeningUpdate,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> JobOpeningResponse:
    opening = db.scalar(_opening_query().where(JobOpening.id == opening_id))
    if opening is None:
        raise HTTPException(status_code=404, detail="Job opening not found")
    _check_branch_access(current_user, opening.branch_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    course_ids = changes.pop("course_ids", None)
    if "company_id" in changes:
        company = _validate_company(db, changes["company_id"])
        changes["company_id"] = company.id
    if "branch_id" in changes:
        _check_branch_access(current_user, changes["branch_id"])
        if changes["branch_id"] is not None and db.get(Branch, changes["branch_id"]) is None:
            raise HTTPException(status_code=404, detail="Branch not found")
    _apply_salary_guard(
        changes.get("salary_min"),
        changes.get("salary_max"),
        opening.salary_min,
        opening.salary_max,
    )
    if "title" in changes and changes["title"]:
        changes["title"] = changes["title"].strip()
    for field, value in changes.items():
        setattr(opening, field, value)
    if course_ids is not None:
        opening.courses = _validate_courses(db, course_ids)
    record_audit(
        db,
        current_user.id,
        "placement_opening_updated",
        "job_opening",
        opening.id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(opening)
    return _opening_response(opening)


@staff_router.delete(
    "/openings/{opening_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(PlacementAccess)],
)
def delete_opening(
    opening_id: int,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> None:
    opening = db.scalar(_opening_query().where(JobOpening.id == opening_id))
    if opening is None:
        raise HTTPException(status_code=404, detail="Job opening not found")
    _check_branch_access(current_user, opening.branch_id)
    if opening.applications:
        raise HTTPException(
            status_code=409,
            detail="Close the opening instead of deleting it; students have already applied",
        )
    record_audit(
        db,
        current_user.id,
        "placement_opening_deleted",
        "job_opening",
        opening.id,
        {"title": opening.title},
    )
    db.delete(opening)
    db.commit()


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
@staff_router.get(
    "/applications",
    response_model=list[ApplicationResponse],
    dependencies=[Depends(PlacementAccess)],
)
def list_applications(
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
    status_filter: str | None = Query(default=None, alias="status"),
    job_opening_id: int | None = None,
    student_id: int | None = None,
    search: str | None = Query(default=None, max_length=120),
) -> list[ApplicationResponse]:
    query = _application_query()
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.join(Student, PlacementApplication.student_id == Student.id).where(
            Student.branch_id == scope
        )
    if status_filter:
        query = query.where(PlacementApplication.status == status_filter)
    if job_opening_id is not None:
        query = query.where(PlacementApplication.job_opening_id == job_opening_id)
    if student_id is not None:
        query = query.where(PlacementApplication.student_id == student_id)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.join(JobOpening, PlacementApplication.job_opening_id == JobOpening.id).join(
            Company, JobOpening.company_id == Company.id
        ).where(
            or_(
                Student.full_name.ilike(pattern),
                Student.student_code.ilike(pattern),
                Company.name.ilike(pattern),
                JobOpening.title.ilike(pattern),
            )
        )
    applications = db.scalars(
        query.order_by(PlacementApplication.updated_at.desc(), PlacementApplication.id.desc())
    ).unique().all()
    names = _student_course_names(db, [app.student_id for app in applications])
    return [
        _application_response(app, names.get(app.student_id, []))
        for app in applications
    ]


@staff_router.post(
    "/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PlacementAccess)],
)
def create_application(
    payload: ApplicationCreate,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> ApplicationResponse:
    opening = db.scalar(_opening_query().where(JobOpening.id == payload.job_opening_id))
    if opening is None:
        raise HTTPException(status_code=404, detail="Job opening not found")
    _check_branch_access(current_user, opening.branch_id)
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.branch))
        .where(Student.id == payload.student_id)
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if not student.is_active:
        raise HTTPException(status_code=400, detail="This student is inactive")
    _check_branch_access(current_user, student.branch_id)
    duplicate = db.scalar(
        select(PlacementApplication).where(
            PlacementApplication.job_opening_id == opening.id,
            PlacementApplication.student_id == student.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail="This student has already been added to this opening"
        )
    application = PlacementApplication(
        job_opening_id=opening.id,
        student_id=student.id,
        status=payload.status,
        source="office",
        resume_url=payload.resume_url,
        cover_note=payload.cover_note,
    )
    db.add(application)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "placement_application_created",
        "placement_application",
        application.id,
        {"opening_id": opening.id, "student_id": student.id, "status": application.status},
    )
    db.commit()
    db.refresh(application)
    names = _student_course_names(db, [student.id]).get(student.id, [])
    return _application_response(application, names)


@staff_router.patch(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    dependencies=[Depends(PlacementAccess)],
)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> ApplicationResponse:
    application = db.scalar(
        _application_query().where(PlacementApplication.id == application_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    _check_branch_access(current_user, application.student.branch_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    previous_status = application.status
    for field, value in changes.items():
        setattr(application, field, value)
    record_audit(
        db,
        current_user.id,
        "placement_application_updated",
        "placement_application",
        application.id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    if changes.get("status") and changes["status"] != previous_status:
        record_audit(
            db,
            current_user.id,
            "placement_status_changed",
            "placement_application",
            application.id,
            {"from": previous_status, "to": changes["status"]},
        )
    db.commit()
    db.refresh(application)
    names = _student_course_names(db, [application.student_id]).get(
        application.student_id, []
    )
    return _application_response(application, names)


@staff_router.delete(
    "/applications/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(PlacementAccess)],
)
def delete_application(
    application_id: int,
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> None:
    application = db.scalar(
        _application_query().where(PlacementApplication.id == application_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    _check_branch_access(current_user, application.student.branch_id)
    record_audit(
        db,
        current_user.id,
        "placement_application_deleted",
        "placement_application",
        application.id,
        {"student_id": application.student_id, "opening_id": application.job_opening_id},
    )
    db.delete(application)
    db.commit()


@staff_router.get(
    "/summary",
    response_model=PlacementSummary,
    dependencies=[Depends(PlacementAccess)],
)
def placement_summary(
    db: DatabaseSession,
    current_user: User = Depends(PlacementUser),
) -> PlacementSummary:
    scope = branch_scope(current_user)
    company_count = db.scalar(select(func.count(Company.id))) or 0
    opening_query = select(func.count(JobOpening.id)).where(JobOpening.status == "open")
    if scope is not None:
        opening_query = opening_query.where(
            or_(JobOpening.branch_id.is_(None), JobOpening.branch_id == scope)
        )
    open_openings = db.scalar(opening_query) or 0
    app_query = select(PlacementApplication.status, func.count(PlacementApplication.id))
    if scope is not None:
        app_query = app_query.join(
            Student, PlacementApplication.student_id == Student.id
        ).where(Student.branch_id == scope)
    rows = db.execute(app_query.group_by(PlacementApplication.status)).all()
    by_status = {row[0]: int(row[1]) for row in rows}
    total = sum(by_status.values())
    return PlacementSummary(
        companies=int(company_count),
        open_openings=int(open_openings),
        total_applications=total,
        by_status=by_status,
        offers_released=by_status.get("offer_released", 0) + by_status.get("joined", 0),
        joined=by_status.get("joined", 0),
    )


# ---------------------------------------------------------------------------
# Student-facing placement portal
# ---------------------------------------------------------------------------
def _student_for_user(db: DatabaseSession, current_user: User) -> Student:
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.branch))
        .where(Student.user_id == current_user.id, Student.is_active.is_(True))
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return student


def _student_course_ids(db: DatabaseSession, student_id: int) -> set[int]:
    return set(
        db.scalars(
            select(Batch.course_id)
            .join(Enrollment, Enrollment.batch_id == Batch.id)
            .where(
                Enrollment.student_id == student_id,
                Enrollment.status.in_(("active", "completed")),
            )
        ).all()
    )


@student_router.get("/opportunities", response_model=list[OpportunityResponse])
def list_opportunities(
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> list[OpportunityResponse]:
    student = _student_for_user(db, current_user)
    course_ids = _student_course_ids(db, student.id)
    openings = db.scalars(
        _opening_query()
        .where(
            JobOpening.status == "open",
            or_(JobOpening.last_date.is_(None), JobOpening.last_date >= date.today()),
            or_(JobOpening.branch_id.is_(None), JobOpening.branch_id == student.branch_id),
        )
        .order_by(JobOpening.created_at.desc())
    ).unique().all()
    applications = {
        application.job_opening_id: application
        for application in db.scalars(
            select(PlacementApplication).where(
                PlacementApplication.student_id == student.id
            )
        ).all()
    }
    results: list[OpportunityResponse] = []
    for opening in openings:
        eligible_courses = {course.id for course in opening.courses}
        if eligible_courses and not eligible_courses.intersection(course_ids):
            continue
        application = applications.get(opening.id)
        results.append(
            OpportunityResponse(
                id=opening.id,
                company_name=opening.company.name,
                title=opening.title,
                description=opening.description,
                location=opening.location,
                employment_type=opening.employment_type,
                work_mode=opening.work_mode,
                salary_min=opening.salary_min,
                salary_max=opening.salary_max,
                vacancies=opening.vacancies,
                last_date=opening.last_date,
                course_names=[course.name for course in opening.courses],
                application_id=application.id if application else None,
                application_status=application.status if application else None,
            )
        )
    return results


@student_router.post(
    "/opportunities/{opening_id}/apply",
    response_model=StudentApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_to_opening(
    opening_id: int,
    payload: StudentApplyRequest,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> StudentApplicationResponse:
    student = _student_for_user(db, current_user)
    opening = db.scalar(_opening_query().where(JobOpening.id == opening_id))
    if opening is None:
        raise HTTPException(status_code=404, detail="Job opening not found")
    if opening.status != "open":
        raise HTTPException(status_code=400, detail="This opening is closed")
    if opening.last_date is not None and opening.last_date < date.today():
        raise HTTPException(status_code=400, detail="The application deadline has passed")
    if opening.branch_id is not None and opening.branch_id != student.branch_id:
        raise HTTPException(status_code=403, detail="This opening is for another branch")
    eligible_courses = {course.id for course in opening.courses}
    if eligible_courses and not eligible_courses.intersection(
        _student_course_ids(db, student.id)
    ):
        raise HTTPException(
            status_code=403, detail="This opening is not open to your course"
        )
    duplicate = db.scalar(
        select(PlacementApplication).where(
            PlacementApplication.job_opening_id == opening.id,
            PlacementApplication.student_id == student.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="You have already applied to this opening")
    application = PlacementApplication(
        job_opening_id=opening.id,
        student_id=student.id,
        status="applied",
        source="student",
        resume_url=payload.resume_url,
        cover_note=payload.cover_note,
    )
    db.add(application)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "placement_application_submitted",
        "placement_application",
        application.id,
        {"opening_id": opening.id, "student_id": student.id},
    )
    db.commit()
    db.refresh(application)
    return StudentApplicationResponse(
        id=application.id,
        job_opening_id=opening.id,
        opening_title=opening.title,
        company_name=opening.company.name,
        status=application.status,
        interview_date=application.interview_date,
        interview_mode=application.interview_mode,
        interview_location=application.interview_location,
        feedback=application.feedback,
        offer_salary=application.offer_salary,
        offer_date=application.offer_date,
        joining_date=application.joining_date,
        offer_letter_url=application.offer_letter_url,
        applied_at=application.applied_at,
    )


@student_router.get("/applications", response_model=list[StudentApplicationResponse])
def list_my_applications(
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> list[StudentApplicationResponse]:
    student = _student_for_user(db, current_user)
    applications = db.scalars(
        _application_query()
        .where(PlacementApplication.student_id == student.id)
        .order_by(PlacementApplication.updated_at.desc())
    ).unique().all()
    return [
        StudentApplicationResponse(
            id=application.id,
            job_opening_id=application.job_opening_id,
            opening_title=application.opening.title,
            company_name=application.opening.company.name,
            status=application.status,
            interview_date=application.interview_date,
            interview_mode=application.interview_mode,
            interview_location=application.interview_location,
            feedback=application.feedback,
            offer_salary=application.offer_salary,
            offer_date=application.offer_date,
            joining_date=application.joining_date,
            offer_letter_url=application.offer_letter_url,
            applied_at=application.applied_at,
        )
        for application in applications
    ]
