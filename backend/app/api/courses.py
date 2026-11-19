from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DatabaseSession, require_module, require_roles
from app.models.course import Course
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate


router = APIRouter(prefix="/api/courses", tags=["Courses"])
AdminUser = require_roles("Super Admin", "Branch Admin", "Staff")
CourseReader = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff", "Counsellor")
CoursesRead = require_module("courses", "enrollments")
CoursesWrite = require_module("courses")


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(CoursesWrite)])
def create_course(
    payload: CourseCreate,
    db: DatabaseSession,
    _: object = Depends(AdminUser),
) -> Course:
    if db.scalar(select(Course).where(Course.code == payload.code)) is not None:
        raise HTTPException(status_code=409, detail="Course code already exists")
    course = Course(**payload.model_dump())
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Course code already exists") from None
    db.refresh(course)
    return course


@router.get("", response_model=list[CourseResponse], dependencies=[Depends(CoursesRead)])
def list_courses(
    db: DatabaseSession,
    _: object = Depends(CourseReader),
    include_inactive: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Course]:
    query = select(Course).order_by(Course.name).offset(offset).limit(limit)
    if not include_inactive:
        query = query.where(Course.is_active.is_(True))
    return list(db.scalars(query).all())


@router.get("/{course_id}", response_model=CourseResponse, dependencies=[Depends(CoursesRead)])
def get_course(
    course_id: int,
    db: DatabaseSession,
    _: object = Depends(AdminUser),
) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.patch("/{course_id}", response_model=CourseResponse, dependencies=[Depends(CoursesWrite)])
def update_course(
    course_id: int,
    payload: CourseUpdate,
    db: DatabaseSession,
    _: object = Depends(AdminUser),
) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes and db.scalar(
        select(Course).where(
            Course.code == changes["code"],
            Course.id != course_id,
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="Course code already exists")
    for field, value in changes.items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", response_model=CourseResponse, dependencies=[Depends(CoursesWrite)])
def deactivate_course(
    course_id: int,
    db: DatabaseSession,
    _: object = Depends(AdminUser),
) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    course.is_active = False
    db.commit()
    db.refresh(course)
    return course
