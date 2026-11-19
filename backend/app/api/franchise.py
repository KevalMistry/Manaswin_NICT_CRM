"""Franchise profiles and royalty settlements (head-office view)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.audit import record_audit
from app.api.dependencies import (
    DatabaseSession,
    branch_scope,
    check_branch_access,
    require_module,
    require_roles,
)
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.enrollment import Enrollment
from app.models.fee import FeeInstallment, FeePlan, Payment
from app.models.finance import FranchiseProfile, RoyaltyPayment
from app.models.student import Student
from app.models.user import User
from app.schemas.franchise import (
    FRANCHISE_STATUSES,
    FranchiseCreate,
    FranchiseResponse,
    FranchiseSummary,
    FranchiseUpdate,
    RoyaltyCreate,
    RoyaltyResponse,
    RoyaltyUpdate,
)


router = APIRouter(prefix="/api/franchises", tags=["Franchise Management"])
FranchiseAccess = require_module("franchises")
FranchiseUser = require_roles("Super Admin", "Branch Admin")

ZERO = Decimal("0.00")


def _money(value: Decimal | None) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(value).quantize(Decimal("0.01"))


def _branch_revenue(db: DatabaseSession, branch_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .where(Batch.branch_id == branch_id)
    )
    return _money(total)


def _branch_students(db: DatabaseSession, branch_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(Student.id)).where(
                Student.branch_id == branch_id, Student.is_active.is_(True)
            )
        )
        or 0
    )


def _branch_royalty_paid(db: DatabaseSession, franchise_id: int) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(RoyaltyPayment.amount), 0)).where(
            RoyaltyPayment.franchise_id == franchise_id
        )
    )
    return _money(total)


def _franchise_response(db: DatabaseSession, profile: FranchiseProfile) -> FranchiseResponse:
    revenue = _branch_revenue(db, profile.branch_id)
    expected = _money(revenue * profile.royalty_percent / Decimal("100"))
    paid = _branch_royalty_paid(db, profile.id)
    return FranchiseResponse(
        id=profile.id,
        branch_id=profile.branch_id,
        branch_name=profile.branch.name if profile.branch else "—",
        branch_code=profile.branch.code if profile.branch else "—",
        owner_name=profile.owner_name,
        owner_phone=profile.owner_phone,
        owner_email=profile.owner_email,
        agreement_start=profile.agreement_start,
        agreement_end=profile.agreement_end,
        royalty_percent=profile.royalty_percent,
        status=profile.status,
        notes=profile.notes,
        students=_branch_students(db, profile.branch_id),
        revenue=revenue,
        royalty_paid=paid,
        royalty_due=(expected - paid).quantize(Decimal("0.01")),
        created_at=profile.created_at,
    )


def _royalty_response(
    payment: RoyaltyPayment, recorder: str | None
) -> RoyaltyResponse:
    return RoyaltyResponse(
        id=payment.id,
        franchise_id=payment.franchise_id,
        branch_name=payment.franchise.branch.name if payment.franchise.branch else "—",
        owner_name=payment.franchise.owner_name,
        amount=payment.amount,
        payment_date=payment.payment_date,
        period_from=payment.period_from,
        period_to=payment.period_to,
        reference=payment.reference,
        notes=payment.notes,
        recorded_by=recorder,
        created_at=payment.created_at,
    )


def _validate_status(value: str) -> None:
    if value not in FRANCHISE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Status must be one of: " + ", ".join(FRANCHISE_STATUSES),
        )


def _validate_dates(period_from: date, period_to: date) -> None:
    if period_to < period_from:
        raise HTTPException(
            status_code=400, detail="Period end cannot be before period start"
        )


def _scoped_franchise(
    db: DatabaseSession, current_user: User, franchise_id: int
) -> FranchiseProfile:
    profile = db.scalar(
        select(FranchiseProfile)
        .options(joinedload(FranchiseProfile.branch))
        .where(FranchiseProfile.id == franchise_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    check_branch_access(current_user, profile.branch_id)
    return profile


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
@router.get(
    "/profiles",
    response_model=list[FranchiseResponse],
    dependencies=[Depends(FranchiseAccess)],
)
def list_profiles(
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> list[FranchiseResponse]:
    query = select(FranchiseProfile).options(joinedload(FranchiseProfile.branch))
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(FranchiseProfile.branch_id == scope)
    profiles = db.scalars(query.order_by(FranchiseProfile.branch_id)).all()
    return [_franchise_response(db, profile) for profile in profiles]


@router.post(
    "/profiles",
    response_model=FranchiseResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(FranchiseAccess)],
)
def create_profile(
    payload: FranchiseCreate,
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> FranchiseResponse:
    check_branch_access(current_user, payload.branch_id)
    branch = db.get(Branch, payload.branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    if db.scalar(
        select(FranchiseProfile).where(FranchiseProfile.branch_id == payload.branch_id)
    ):
        raise HTTPException(
            status_code=409, detail="This branch already has a franchise profile"
        )
    _validate_status(payload.status)
    if payload.agreement_end is not None and payload.agreement_end < payload.agreement_start:
        raise HTTPException(
            status_code=400, detail="Agreement end cannot be before the start date"
        )
    profile = FranchiseProfile(
        branch_id=payload.branch_id,
        owner_name=payload.owner_name,
        owner_phone=payload.owner_phone,
        owner_email=str(payload.owner_email) if payload.owner_email else None,
        agreement_start=payload.agreement_start,
        agreement_end=payload.agreement_end,
        royalty_percent=payload.royalty_percent,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(profile)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "franchise_profile_created",
        "franchise_profile",
        profile.id,
        payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(profile)
    return _franchise_response(db, profile)


@router.patch(
    "/profiles/{franchise_id}",
    response_model=FranchiseResponse,
    dependencies=[Depends(FranchiseAccess)],
)
def update_profile(
    franchise_id: int,
    payload: FranchiseUpdate,
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> FranchiseResponse:
    profile = _scoped_franchise(db, current_user, franchise_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    if "status" in changes and changes["status"]:
        _validate_status(changes["status"])
    start = changes.get("agreement_start", profile.agreement_start)
    end = changes.get("agreement_end", profile.agreement_end)
    if end is not None and end < start:
        raise HTTPException(
            status_code=400, detail="Agreement end cannot be before the start date"
        )
    if "owner_email" in changes and changes["owner_email"] is not None:
        changes["owner_email"] = str(changes["owner_email"])
    for field, value in changes.items():
        setattr(profile, field, value)
    record_audit(
        db,
        current_user.id,
        "franchise_profile_updated",
        "franchise_profile",
        profile.id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(profile)
    return _franchise_response(db, profile)


@router.delete(
    "/profiles/{franchise_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(FranchiseAccess)],
)
def delete_profile(
    franchise_id: int,
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> None:
    profile = _scoped_franchise(db, current_user, franchise_id)
    record_audit(
        db,
        current_user.id,
        "franchise_profile_deleted",
        "franchise_profile",
        profile.id,
        {"branch_id": profile.branch_id, "owner_name": profile.owner_name},
    )
    db.delete(profile)
    db.commit()


# ---------------------------------------------------------------------------
# Royalty payments
# ---------------------------------------------------------------------------
@router.get(
    "/royalties",
    response_model=list[RoyaltyResponse],
    dependencies=[Depends(FranchiseAccess)],
)
def list_royalties(
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
    franchise_id: int | None = None,
) -> list[RoyaltyResponse]:
    query = select(RoyaltyPayment).options(
        joinedload(RoyaltyPayment.franchise).joinedload(FranchiseProfile.branch),
        joinedload(RoyaltyPayment.recorded_by),
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.join(
            FranchiseProfile, RoyaltyPayment.franchise_id == FranchiseProfile.id
        ).where(FranchiseProfile.branch_id == scope)
    if franchise_id is not None:
        query = query.where(RoyaltyPayment.franchise_id == franchise_id)
    payments = db.scalars(
        query.order_by(RoyaltyPayment.payment_date.desc(), RoyaltyPayment.id.desc())
    ).unique().all()
    return [
        _royalty_response(
            payment,
            payment.recorded_by.full_name if payment.recorded_by else None,
        )
        for payment in payments
    ]


@router.post(
    "/royalties",
    response_model=RoyaltyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(FranchiseAccess)],
)
def create_royalty(
    payload: RoyaltyCreate,
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> RoyaltyResponse:
    profile = _scoped_franchise(db, current_user, payload.franchise_id)
    _validate_dates(payload.period_from, payload.period_to)
    payment = RoyaltyPayment(
        franchise_id=profile.id,
        amount=payload.amount,
        payment_date=payload.payment_date,
        period_from=payload.period_from,
        period_to=payload.period_to,
        reference=payload.reference,
        notes=payload.notes,
        recorded_by_id=current_user.id,
    )
    db.add(payment)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "royalty_payment_recorded",
        "royalty_payment",
        payment.id,
        payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(payment)
    return _royalty_response(payment, current_user.full_name)


@router.patch(
    "/royalties/{payment_id}",
    response_model=RoyaltyResponse,
    dependencies=[Depends(FranchiseAccess)],
)
def update_royalty(
    payment_id: int,
    payload: RoyaltyUpdate,
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> RoyaltyResponse:
    payment = db.scalar(
        select(RoyaltyPayment)
        .options(
            joinedload(RoyaltyPayment.franchise).joinedload(FranchiseProfile.branch),
            joinedload(RoyaltyPayment.recorded_by),
        )
        .where(RoyaltyPayment.id == payment_id)
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Royalty payment not found")
    check_branch_access(current_user, payment.franchise.branch_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    start = changes.get("period_from", payment.period_from)
    end = changes.get("period_to", payment.period_to)
    _validate_dates(start, end)
    for field, value in changes.items():
        setattr(payment, field, value)
    record_audit(
        db,
        current_user.id,
        "royalty_payment_updated",
        "royalty_payment",
        payment.id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(payment)
    return _royalty_response(
        payment, payment.recorded_by.full_name if payment.recorded_by else None
    )


@router.delete(
    "/royalties/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(FranchiseAccess)],
)
def delete_royalty(
    payment_id: int,
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> None:
    payment = db.scalar(
        select(RoyaltyPayment)
        .options(joinedload(RoyaltyPayment.franchise))
        .where(RoyaltyPayment.id == payment_id)
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Royalty payment not found")
    check_branch_access(current_user, payment.franchise.branch_id)
    record_audit(
        db,
        current_user.id,
        "royalty_payment_deleted",
        "royalty_payment",
        payment.id,
        {"amount": str(payment.amount)},
    )
    db.delete(payment)
    db.commit()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
@router.get(
    "/summary",
    response_model=FranchiseSummary,
    dependencies=[Depends(FranchiseAccess)],
)
def franchise_summary(
    db: DatabaseSession,
    current_user: User = Depends(FranchiseUser),
) -> FranchiseSummary:
    query = select(FranchiseProfile).options(joinedload(FranchiseProfile.branch))
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(FranchiseProfile.branch_id == scope)
    profiles = db.scalars(query).unique().all()

    revenue = ZERO
    royalty_expected = ZERO
    royalty_paid = ZERO
    students = 0
    for profile in profiles:
        branch_revenue = _branch_revenue(db, profile.branch_id)
        revenue += branch_revenue
        royalty_expected += branch_revenue * profile.royalty_percent / Decimal("100")
        royalty_paid += _branch_royalty_paid(db, profile.id)
        students += _branch_students(db, profile.branch_id)

    return FranchiseSummary(
        franchises=len(profiles),
        active_franchises=sum(1 for profile in profiles if profile.status == "active"),
        students=students,
        revenue=_money(revenue),
        royalty_expected=_money(royalty_expected),
        royalty_paid=_money(royalty_paid),
        royalty_due=_money(royalty_expected - royalty_paid),
    )
