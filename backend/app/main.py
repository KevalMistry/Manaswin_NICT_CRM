from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager
from app.core.config import AUTOMATION_ENABLED, CORS_ORIGINS, ENABLE_API_DOCS
from app.db.database import SessionLocal, database_connected
from app.services.automation import daily_notification_loop
from app.services.permissions import ensure_permissions_seeded
from app.api.auth import router as auth_router
from app.api.branches import router as branches_router
from app.api.students import router as students_router
from app.api.courses import router as courses_router
from app.api.batches import router as batches_router
from app.api.enrollments import router as enrollments_router
from app.api.enquiries import router as enquiries_router
from app.api.fees import router as fees_router
from app.api.attendance import router as attendance_router
from app.api.examinations import router as examinations_router
from app.api.certificates import router as certificates_router
from app.api.staff import router as staff_router
from app.api.dashboard import router as dashboard_router
from app.api.student_portal import router as student_portal_router
from app.api.audit import router as audit_router
from app.api.permissions import router as permissions_router
from app.api.reports import router as reports_router
from app.api.lms import router as lms_router
from app.api.online_exams import router as online_exams_router
from app.api.notifications import router as notifications_router
from app.api.parents import router as parents_router
from app.api.parent_portal import router as parent_portal_router
from app.api.placement import staff_router as placement_router
from app.api.placement import student_router as placement_portal_router
from app.api.finance import router as finance_router
from app.api.franchise import router as franchise_router
from app.api.admissions import public_router as public_admissions_router
from app.api.admissions import router as admissions_router
from app.api.email_templates import router as email_templates_router
from app.api.media import router as media_router
from app.services.email_templates import ensure_email_templates_seeded


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Add permission rows for modules introduced after a role was first seeded
    # (for example the placement cell) so navigation stays up to date.
    with SessionLocal() as db:
        ensure_permissions_seeded(db)
        try:
            ensure_email_templates_seeded(db)
        except Exception:
            # The templates table may not exist yet during a fresh migration.
            db.rollback()
    task = None
    if AUTOMATION_ENABLED:
        task = asyncio.create_task(daily_notification_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)
uploads_directory = Path(__file__).resolve().parents[1] / "uploads"
uploads_directory.mkdir(parents=True, exist_ok=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response

app.include_router(auth_router)
app.include_router(branches_router)
app.include_router(students_router)
app.include_router(courses_router)
app.include_router(batches_router)
app.include_router(enrollments_router)
app.include_router(enquiries_router)
app.include_router(fees_router)
app.include_router(attendance_router)
app.include_router(examinations_router)
app.include_router(certificates_router)
app.include_router(staff_router)
app.include_router(dashboard_router)
app.include_router(student_portal_router)
app.include_router(audit_router)
app.include_router(permissions_router)
app.include_router(reports_router)
app.include_router(lms_router)
app.include_router(online_exams_router)
app.include_router(notifications_router)
app.include_router(parents_router)
app.include_router(parent_portal_router)
app.include_router(placement_router)
app.include_router(placement_portal_router)
app.include_router(finance_router)
app.include_router(franchise_router)
app.include_router(admissions_router)
app.include_router(public_admissions_router)
app.include_router(email_templates_router)
app.include_router(media_router)

@app.get("/")
async def root():
    return {"message": "Institute Management API"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected" if database_connected else "disconnected",
    }


@app.get("/api/health")
async def api_health_check():
    return {
        "status": "healthy",
        "database": "connected" if database_connected else "disconnected",
    }