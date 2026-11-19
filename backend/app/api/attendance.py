from datetime import date, datetime, timedelta, timezone
import hashlib
import ipaddress
import math
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    require_module,
    require_roles,
)
from app.api.audit import record_audit
from app.models.attendance import Attendance, AttendanceSession
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.role import Role
from app.models.staff_attendance import StaffAttendance
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.attendance import (
    AttendanceCreate,
    AttendanceResponse,
    AttendanceSessionCreate,
    AttendanceSessionResponse,
    AttendanceUpdate,
    QRAttendanceCreate,
    StaffAttendanceCreate,
    StaffAttendancePerson,
    StaffAttendanceResponse,
    StaffAttendanceSummaryRow,
    StaffSelfCheckInRequest,
)


router = APIRouter(prefix="/api/attendance", tags=["Attendance"])
AttendanceUser = require_roles("Super Admin", "Branch Admin", "Faculty", "Staff")
StudentUser = require_roles("Student")
AttendanceAccess = require_module("attendance")
StaffAttendanceUser = require_roles(
    "Super Admin", "Branch Admin", "Faculty", "Staff"
)
STAFF_ATTENDANCE_ROLES = ("Faculty", "Staff", "Counsellor", "Branch Admin")


def get_accessible_enrollment(
    db: DatabaseSession,
    enrollment_id: int,
    current_user: User,
) -> Enrollment:
    enrollment = db.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.batch))
        .where(Enrollment.id == enrollment_id)
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    check_branch_access(current_user, enrollment.batch.branch_id)
    if current_user.role.name == "Faculty" and enrollment.batch.faculty_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty can manage attendance only for assigned batches",
        )
    return enrollment


def get_accessible_batch(db: DatabaseSession, batch_id: int, current_user: User) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None or not batch.is_active:
        raise HTTPException(status_code=404, detail="Active batch not found")
    check_branch_access(current_user, batch.branch_id)
    if current_user.role.name == "Faculty" and batch.faculty_id != current_user.id:
        raise HTTPException(status_code=403, detail="Faculty can create sessions only for assigned batches")
    return batch


@router.post("/sessions", response_model=AttendanceSessionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(AttendanceAccess)])
def create_attendance_session(
    payload: AttendanceSessionCreate,
    db: DatabaseSession,
    current_user: User = Depends(AttendanceUser),
) -> AttendanceSessionResponse:
    batch = get_accessible_batch(db, payload.batch_id, current_user)
    if payload.attendance_date != date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QR attendance sessions can only be created for today",
        )
    raw_token = secrets.token_urlsafe(32)
    session = AttendanceSession(
        batch_id=batch.id,
        created_by_id=current_user.id,
        attendance_date=payload.attendance_date,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=payload.expires_in_minutes),
    )
    db.add(session)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "attendance_session_created",
        "attendance_session",
        session.id,
        {"batch_id": batch.id, "attendance_date": str(session.attendance_date)},
    )
    db.commit()
    db.refresh(session)
    return AttendanceSessionResponse(
        session_id=session.id,
        batch_id=session.batch_id,
        attendance_date=session.attendance_date,
        expires_at=session.expires_at.replace(tzinfo=timezone.utc),
        token=raw_token,
    )


@router.post("/sessions/submit", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
def submit_qr_attendance(
    payload: QRAttendanceCreate,
    db: DatabaseSession,
    current_user: User = Depends(StudentUser),
) -> Attendance:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    session = db.scalar(
        select(AttendanceSession)
        .options(joinedload(AttendanceSession.batch))
        .where(AttendanceSession.token_hash == token_hash)
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if session is None or session.expires_at <= now:
        raise HTTPException(status_code=400, detail="This attendance QR code has expired")
    student = db.scalar(
        select(Student).where(Student.user_id == current_user.id, Student.is_active.is_(True))
    )
    if student is None:
        raise HTTPException(status_code=403, detail="No active student profile is linked to this account")
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.batch_id == session.batch_id,
            Enrollment.status == "active",
        )
    )
    if enrollment is None:
        raise HTTPException(status_code=403, detail="You are not actively enrolled in this batch")
    if db.scalar(select(Attendance).where(
        Attendance.enrollment_id == enrollment.id,
        Attendance.attendance_date == session.attendance_date,
    )):
        raise HTTPException(status_code=409, detail="Attendance is already recorded for this date")
    record = Attendance(
        enrollment_id=enrollment.id,
        attendance_date=session.attendance_date,
        status="present",
        remarks="Marked through QR attendance",
        marked_by_id=session.created_by_id,
    )
    db.add(record)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "qr_attendance_submitted",
        "attendance",
        record.id,
        {"batch_id": session.batch_id, "attendance_date": str(session.attendance_date)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Attendance is already recorded for this date") from None
    db.refresh(record)
    return record


@router.post(
    "",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(AttendanceAccess)],
)
def mark_attendance(
    payload: AttendanceCreate,
    db: DatabaseSession,
    current_user: User = Depends(AttendanceUser),
) -> Attendance:
    enrollment = get_accessible_enrollment(db, payload.enrollment_id, current_user)
    if enrollment.status != "active":
        raise HTTPException(status_code=400, detail="Enrollment is not active")

    existing = db.scalar(
        select(Attendance).where(
            Attendance.enrollment_id == payload.enrollment_id,
            Attendance.attendance_date == payload.attendance_date,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance is already marked for this date",
        )

    record = Attendance(marked_by_id=current_user.id, **payload.model_dump())
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance is already marked for this date",
        ) from None
    db.refresh(record)
    return record


@router.patch(
    "/{attendance_id}",
    response_model=AttendanceResponse,
    dependencies=[Depends(AttendanceAccess)],
)
def update_attendance(
    attendance_id: int,
    payload: AttendanceUpdate,
    db: DatabaseSession,
    current_user: User = Depends(AttendanceUser),
) -> Attendance:
    record = db.scalar(
        select(Attendance)
        .options(joinedload(Attendance.enrollment).joinedload(Enrollment.batch))
        .where(Attendance.id == attendance_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    check_branch_access(current_user, record.enrollment.batch.branch_id)
    record.status = payload.status
    if payload.remarks is not None:
        record.remarks = payload.remarks
    record.marked_by_id = current_user.id
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[AttendanceResponse], dependencies=[Depends(AttendanceAccess)])
def list_attendance(
    db: DatabaseSession,
    current_user: User = Depends(AttendanceUser),
    enrollment_id: int | None = Query(default=None),
    attendance_date: date | None = Query(default=None),
    batch_id: int | None = Query(default=None),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(present|absent|late|excused)$",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Attendance]:
    query = (
        select(Attendance)
        .join(Enrollment, Attendance.enrollment_id == Enrollment.id)
        .join(Enrollment.batch)
        .order_by(Attendance.attendance_date.desc(), Attendance.id.desc())
        .offset(offset)
        .limit(limit)
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Enrollment.batch.has(branch_id=scope))
    if current_user.role.name == "Faculty":
        query = query.where(Enrollment.batch.has(faculty_id=current_user.id))
    if enrollment_id is not None:
        query = query.where(Attendance.enrollment_id == enrollment_id)
    if attendance_date is not None:
        query = query.where(Attendance.attendance_date == attendance_date)
    if batch_id is not None:
        query = query.where(Enrollment.batch_id == batch_id)
    if status_filter is not None:
        query = query.where(Attendance.status == status_filter)
    return list(db.scalars(query).all())


@router.get("/summary/{enrollment_id}", dependencies=[Depends(AttendanceAccess)])
def attendance_summary(
    enrollment_id: int,
    db: DatabaseSession,
    current_user: User = Depends(AttendanceUser),
) -> dict[str, int | float]:
    get_accessible_enrollment(db, enrollment_id, current_user)
    total, present, absent, late, excused = db.execute(
        select(
            func.count(Attendance.id),
            func.sum(case((Attendance.status == "present", 1), else_=0)),
            func.sum(case((Attendance.status == "absent", 1), else_=0)),
            func.sum(case((Attendance.status == "late", 1), else_=0)),
            func.sum(case((Attendance.status == "excused", 1), else_=0)),
        ).where(Attendance.enrollment_id == enrollment_id)
    ).one()
    total_count = int(total or 0)
    present_count = int(present or 0)
    excused_count = int(excused or 0)
    # Excused absences are authorised and must not lower the attendance rate.
    attended_count = present_count + int(late or 0) + excused_count
    return {
        "total": total_count,
        "present": present_count,
        "absent": int(absent or 0),
        "late": int(late or 0),
        "excused": excused_count,
        "attendance_percentage": round(
            (attended_count / total_count) * 100, 2
        ) if total_count else 0.0,
    }


# ---------------------------------------------------------------------------
# Faculty / staff attendance
# ---------------------------------------------------------------------------

def _month_range(month: str) -> tuple[date, date]:
    try:
        year, month_number = (int(part) for part in month.split("-"))
        start = date(year, month_number, 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400, detail="Use YYYY-MM format for the attendance month"
        ) from None
    end = (
        date(year + 1, 1, 1) if month_number == 12 else date(year, month_number + 1, 1)
    ) - timedelta(days=1)
    return start, end


def _haversine_meters(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    """Great-circle distance in metres between two WGS84 coordinates."""
    radius = 6_371_000.0
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(value)))


def _client_ip(request: Request) -> str:
    """Return the peer address as resolved by the ASGI server.

    ``X-Forwarded-For`` is intentionally ignored here. The header is supplied
    by the caller, so trusting it let anyone claim an office IP and bypass the
    attendance network check. Deployments behind a reverse proxy should let
    Uvicorn's ``--proxy-headers`` support (with ``FORWARDED_ALLOW_IPS``) update
    ``request.client`` instead.
    """
    candidate = request.client.host if request.client else ""
    if candidate.startswith("::ffff:"):
        candidate = candidate.removeprefix("::ffff:")
    return candidate


def _office_network_allows(branch: Branch, client_ip: str) -> bool:
    """Return True when the request comes from an allowed office network.

    An empty allowlist disables the network check. Invalid entries are ignored
    so a typo cannot lock every employee out of check-in; the geofence remains
    the primary control.
    """
    configured = (branch.office_network or "").strip()
    if not configured:
        return True
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in configured.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def _staff_attendance_payload(record: StaffAttendance) -> StaffAttendanceResponse:
    user = record.user
    return StaffAttendanceResponse(
        id=record.id,
        user_id=record.user_id,
        attendance_date=record.attendance_date,
        status=record.status,
        check_in=record.check_in,
        check_out=record.check_out,
        remarks=record.remarks,
        latitude=float(record.latitude) if record.latitude is not None else None,
        longitude=float(record.longitude) if record.longitude is not None else None,
        distance_meters=(
            float(record.distance_meters) if record.distance_meters is not None else None
        ),
        location_status=record.location_status,
        ip_address=record.ip_address,
        marked_by_id=record.marked_by_id,
        created_at=record.created_at,
        user_name=user.full_name if user else None,
        user_role=user.role.name if user and user.role else None,
        branch_id=user.branch_id if user else None,
        branch_name=user.branch.name if user and user.branch else None,
    )


def _get_staff_target(
    db: DatabaseSession, user_id: int, current_user: User
) -> User:
    target = db.scalar(
        select(User).options(joinedload(User.role)).where(User.id == user_id)
    )
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Staff account not found")
    if target.role is None or target.role.name not in STAFF_ATTENDANCE_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Attendance can be recorded only for faculty or staff accounts",
        )
    role = current_user.role.name
    if role == "Super Admin":
        return target
    if role == "Branch Admin":
        if target.branch_id != current_user.branch_id:
            raise HTTPException(
                status_code=403,
                detail="You can record attendance only for your assigned branch",
            )
        return target
    if target.id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can record only your own attendance",
        )
    return target


def _staff_people_query(current_user: User):
    return (
        select(User)
        .options(joinedload(User.role), joinedload(User.branch))
        .where(
            User.is_active.is_(True),
            User.role.has(Role.name.in_(STAFF_ATTENDANCE_ROLES)),
        )
    )


@router.get(
    "/staff/people",
    response_model=list[StaffAttendancePerson],
    dependencies=[Depends(AttendanceAccess)],
)
def list_staff_attendance_people(
    db: DatabaseSession,
    current_user: User = Depends(StaffAttendanceUser),
    branch_id: int | None = Query(default=None),
) -> list[StaffAttendancePerson]:
    query = _staff_people_query(current_user)
    role = current_user.role.name
    if role == "Super Admin":
        if branch_id is not None:
            query = query.where(User.branch_id == branch_id)
    elif role == "Branch Admin":
        query = query.where(User.branch_id == current_user.branch_id)
    else:
        query = query.where(User.id == current_user.id)
    users = db.scalars(query.order_by(User.full_name)).all()
    return [
        StaffAttendancePerson(
            id=user.id,
            full_name=user.full_name,
            role_name=user.role.name if user.role else "",
            branch_id=user.branch_id,
            branch_name=user.branch.name if user.branch else None,
            phone=user.phone,
        )
        for user in users
    ]


def _staff_attendance_query(current_user: User, branch_id: int | None):
    query = select(StaffAttendance).options(
        joinedload(StaffAttendance.user).joinedload(User.role),
        joinedload(StaffAttendance.user).joinedload(User.branch),
    )
    role = current_user.role.name
    if role == "Super Admin":
        if branch_id is not None:
            query = query.join(User, StaffAttendance.user_id == User.id).where(
                User.branch_id == branch_id
            )
    elif role == "Branch Admin":
        query = query.join(User, StaffAttendance.user_id == User.id).where(
            User.branch_id == current_user.branch_id
        )
    else:
        query = query.where(StaffAttendance.user_id == current_user.id)
    return query


@router.get(
    "/staff",
    response_model=list[StaffAttendanceResponse],
    dependencies=[Depends(AttendanceAccess)],
)
def list_staff_attendance(
    db: DatabaseSession,
    current_user: User = Depends(StaffAttendanceUser),
    attendance_date: date | None = Query(default=None),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    user_id: int | None = Query(default=None),
    branch_id: int | None = Query(default=None),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(present|absent|late|leave|half_day)$",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[StaffAttendanceResponse]:
    query = _staff_attendance_query(current_user, branch_id)
    if attendance_date is not None:
        query = query.where(StaffAttendance.attendance_date == attendance_date)
    if month is not None:
        start, end = _month_range(month)
        query = query.where(
            StaffAttendance.attendance_date >= start,
            StaffAttendance.attendance_date <= end,
        )
    if user_id is not None:
        if current_user.role.name not in {"Super Admin", "Branch Admin"} and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can view only your own attendance")
        query = query.where(StaffAttendance.user_id == user_id)
    if status_filter is not None:
        query = query.where(StaffAttendance.status == status_filter)
    records = db.scalars(
        query.order_by(
            StaffAttendance.attendance_date.desc(), StaffAttendance.id.desc()
        )
        .offset(offset)
        .limit(limit)
    ).all()
    return [_staff_attendance_payload(record) for record in records]


@router.post(
    "/staff",
    response_model=StaffAttendanceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(AttendanceAccess)],
)
def mark_staff_attendance(
    payload: StaffAttendanceCreate,
    db: DatabaseSession,
    current_user: User = Depends(StaffAttendanceUser),
) -> StaffAttendanceResponse:
    target = _get_staff_target(db, payload.user_id or current_user.id, current_user)
    # Self-marking without location proof is exactly the "mark from home"
    # loophole this endpoint used to allow. Only admins may mark attendance on
    # behalf of someone else, and even they must use location-verified
    # check-in for their own record.
    if target.id == current_user.id and current_user.role.name != "Super Admin":
        raise HTTPException(
            status_code=403,
            detail="Use the location-verified self check-in to record your own attendance.",
        )
    if current_user.role.name not in {"Super Admin", "Branch Admin"}:
        raise HTTPException(
            status_code=403,
            detail="Only a branch admin can mark attendance for another person.",
        )
    record = db.scalar(
        select(StaffAttendance).where(
            StaffAttendance.user_id == target.id,
            StaffAttendance.attendance_date == payload.attendance_date,
        )
    )
    check_in = payload.check_in
    if record is None:
        record = StaffAttendance(
            user_id=target.id,
            attendance_date=payload.attendance_date,
            status=payload.status,
            check_in=check_in,
            check_out=payload.check_out,
            remarks=payload.remarks,
            marked_by_id=current_user.id,
        )
        db.add(record)
        action = "staff_attendance_marked"
    else:
        record.status = payload.status
        record.check_in = payload.check_in if payload.check_in is not None else record.check_in
        record.check_out = payload.check_out if payload.check_out is not None else record.check_out
        record.remarks = payload.remarks
        record.marked_by_id = current_user.id
        action = "staff_attendance_updated"
    db.flush()
    record_audit(
        db,
        current_user.id,
        action,
        "staff_attendance",
        record.id,
        {
            "user_id": target.id,
            "attendance_date": str(payload.attendance_date),
            "status": payload.status,
        },
    )
    db.commit()
    db.refresh(record)
    return _staff_attendance_payload(record)


@router.post(
    "/staff/check-in",
    response_model=StaffAttendanceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(AttendanceAccess)],
)
def staff_self_check_in(
    payload: StaffSelfCheckInRequest,
    request: Request,
    db: DatabaseSession,
    current_user: User = Depends(StaffAttendanceUser),
) -> StaffAttendanceResponse:
    if current_user.role.name not in STAFF_ATTENDANCE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Self check-in is available only for faculty and staff accounts",
        )
    branch = current_user.branch or db.get(Branch, current_user.branch_id)
    if branch is None:
        raise HTTPException(
            status_code=400,
            detail="Your account is not assigned to a branch, so attendance cannot be verified.",
        )
    if branch.latitude is None or branch.longitude is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This branch has no check-in location configured. Ask a Super Admin "
                "to add the branch coordinates before staff can self check-in."
            ),
        )
    radius = int(branch.geofence_radius_meters or 150)
    if payload.accuracy_meters is not None and payload.accuracy_meters > 250:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Location accuracy is only +/-{payload.accuracy_meters:.0f} m. "
                "Move to an open area and try again."
            ),
        )
    distance = _haversine_meters(
        float(branch.latitude),
        float(branch.longitude),
        payload.latitude,
        payload.longitude,
    )
    if distance > radius:
        raise HTTPException(
            status_code=403,
            detail=(
                f"You are about {distance:.0f} m from {branch.name}. "
                f"Self check-in is allowed only within {radius} m of the branch."
            ),
        )
    client_ip = _client_ip(request)
    if not _office_network_allows(branch, client_ip):
        raise HTTPException(
            status_code=403,
            detail=(
                "This check-in did not come from the branch network. "
                "Connect to the institute Wi-Fi and try again."
            ),
        )
    today = date.today()
    record = db.scalar(
        select(StaffAttendance).where(
            StaffAttendance.user_id == current_user.id,
            StaffAttendance.attendance_date == today,
        )
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if record is None:
        record = StaffAttendance(
            user_id=current_user.id,
            attendance_date=today,
            status="present",
            check_in=now,
            marked_by_id=current_user.id,
            remarks="Location-verified self check-in",
        )
        db.add(record)
    elif record.status != "present":
        record.status = "present"
        record.check_in = record.check_in or now
        record.marked_by_id = current_user.id
        record.remarks = record.remarks or "Location-verified self check-in"
    else:
        raise HTTPException(
            status_code=409, detail="You have already checked in today"
        )
    record.latitude = payload.latitude
    record.longitude = payload.longitude
    record.distance_meters = round(distance, 2)
    record.location_status = "verified"
    record.ip_address = client_ip
    db.flush()
    record_audit(
        db,
        current_user.id,
        "staff_self_check_in",
        "staff_attendance",
        record.id,
        {
            "attendance_date": str(today),
            "distance_meters": round(distance, 2),
            "branch_id": branch.id,
            "ip_address": client_ip,
        },
    )
    db.commit()
    db.refresh(record)
    return _staff_attendance_payload(record)


@router.get(
    "/staff/summary",
    response_model=list[StaffAttendanceSummaryRow],
    dependencies=[Depends(AttendanceAccess)],
)
def staff_attendance_summary(
    db: DatabaseSession,
    current_user: User = Depends(StaffAttendanceUser),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    branch_id: int | None = Query(default=None),
) -> list[StaffAttendanceSummaryRow]:
    if month is None:
        month = date.today().strftime("%Y-%m")
    start, end = _month_range(month)

    people_query = (
        select(User)
        .options(joinedload(User.role), joinedload(User.branch))
        .where(
            User.is_active.is_(True),
            User.role.has(Role.name.in_(STAFF_ATTENDANCE_ROLES)),
        )
    )
    role = current_user.role.name
    if role == "Super Admin":
        if branch_id is not None:
            people_query = people_query.where(User.branch_id == branch_id)
    elif role == "Branch Admin":
        people_query = people_query.where(User.branch_id == current_user.branch_id)
    else:
        people_query = people_query.where(User.id == current_user.id)
    people = db.scalars(people_query.order_by(User.full_name)).all()

    counts = db.execute(
        select(
            StaffAttendance.user_id,
            StaffAttendance.status,
            func.count(StaffAttendance.id),
        )
        .where(
            StaffAttendance.attendance_date >= start,
            StaffAttendance.attendance_date <= end,
        )
        .group_by(StaffAttendance.user_id, StaffAttendance.status)
    ).all()
    by_user: dict[int, dict[str, int]] = {}
    for user_id, status_value, count in counts:
        by_user.setdefault(user_id, {})[status_value] = int(count or 0)

    rows: list[StaffAttendanceSummaryRow] = []
    for person in people:
        totals = by_user.get(person.id, {})
        present = totals.get("present", 0)
        late = totals.get("late", 0)
        absent = totals.get("absent", 0)
        leave = totals.get("leave", 0)
        half_day = totals.get("half_day", 0)
        recorded = present + late + absent + leave + half_day
        attended = present + late + (half_day * 0.5)
        rows.append(
            StaffAttendanceSummaryRow(
                user_id=person.id,
                user_name=person.full_name,
                role_name=person.role.name if person.role else "",
                branch_name=person.branch.name if person.branch else None,
                present=present,
                absent=absent,
                late=late,
                leave=leave,
                half_day=half_day,
                recorded_days=recorded,
                attendance_rate=round((attended / recorded) * 100, 2) if recorded else 0.0,
            )
        )
    return rows
