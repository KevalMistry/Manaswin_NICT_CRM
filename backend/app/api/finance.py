"""Finance module: expenses, bank accounts, cash book and summary.

Fees are the only income stream in the current data model. A fee payment is
linked to a branch through ``Payment -> FeeInstallment -> FeePlan ->
Enrollment -> Batch``. Expenses carry a direct ``branch_id``. Every endpoint
therefore applies the same branch scope used by the rest of the application.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.core.config import GST_RATE_PERCENT
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.enrollment import Enrollment
from app.models.fee import FeeInstallment, FeePlan, Payment
from app.models.finance import BankAccount, Expense
from app.models.user import User
from app.schemas.finance import (
    BankAccountCreate,
    BankAccountResponse,
    BankAccountUpdate,
    CashBookEntry,
    CashBookResponse,
    ExpenseCreate,
    ExpenseResponse,
    ExpenseUpdate,
    FinanceSummary,
)


router = APIRouter(prefix="/api/finance", tags=["Finance"])
FinanceAccess = require_module("finance")
FinanceUser = require_roles("Super Admin", "Branch Admin", "Staff")


def _money(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(value).quantize(Decimal("0.01"))


def _gst_component(amount: Decimal | None) -> Decimal:
    """Return the inclusive GST portion of an amount at the configured rate."""
    if not amount:
        return Decimal("0.00")
    rate = Decimal(str(GST_RATE_PERCENT))
    if rate <= 0:
        return Decimal("0.00")
    return (Decimal(amount) * rate / (Decimal("100") + rate)).quantize(
        Decimal("0.01")
    )


def _resolve_branch(current_user: User, branch_id: int | None) -> int:
    if branch_id is None:
        branch_id = current_user.branch_id
    if branch_id is None:
        raise HTTPException(
            status_code=400, detail="Choose a branch for this record"
        )
    check_branch_access(current_user, branch_id)
    return branch_id


def _validate_branch(db: DatabaseSession, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


def _fee_payment_query():
    return (
        select(Payment, FeeInstallment, FeePlan, Enrollment, Batch, Branch)
        .join(FeeInstallment, Payment.installment_id == FeeInstallment.id)
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
        .join(Branch, Batch.branch_id == Branch.id)
    )


def _expense_response(expense: Expense, recorder: str | None) -> ExpenseResponse:
    return ExpenseResponse(
        id=expense.id,
        branch_id=expense.branch_id,
        branch_name=expense.branch.name if expense.branch else "—",
        category=expense.category,
        description=expense.description,
        amount=expense.amount,
        gst_amount=expense.gst_amount,
        expense_date=expense.expense_date,
        payment_method=expense.payment_method,
        vendor=expense.vendor,
        reference=expense.reference,
        notes=expense.notes,
        receipt_url=expense.receipt_url,
        recorded_by=recorder,
        created_at=expense.created_at,
    )


def _bank_response(account: BankAccount) -> BankAccountResponse:
    return BankAccountResponse(
        id=account.id,
        branch_id=account.branch_id,
        branch_name=account.branch.name if account.branch else None,
        account_name=account.account_name,
        bank_name=account.bank_name,
        account_number=account.account_number,
        ifsc=account.ifsc,
        opening_balance=account.opening_balance,
        is_active=account.is_active,
        created_at=account.created_at,
    )


def _collected_total(
    db: DatabaseSession,
    branch_id: int | None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Decimal:
    query = select(func.coalesce(func.sum(Payment.amount), 0)).select_from(Payment).join(
        FeeInstallment, Payment.installment_id == FeeInstallment.id
    ).join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id).join(
        Enrollment, FeePlan.enrollment_id == Enrollment.id
    ).join(Batch, Enrollment.batch_id == Batch.id)
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    if date_from is not None:
        query = query.where(Payment.payment_date >= date_from)
    if date_to is not None:
        query = query.where(Payment.payment_date <= date_to)
    return _money(db.scalar(query))


def _expense_total(
    db: DatabaseSession,
    branch_id: int | None,
    date_from: date | None = None,
    date_to: date | None = None,
    *,
    gst_only: bool = False,
) -> Decimal:
    column = Expense.gst_amount if gst_only else Expense.amount
    query = select(func.coalesce(func.sum(column), 0))
    if branch_id is not None:
        query = query.where(Expense.branch_id == branch_id)
    if date_from is not None:
        query = query.where(Expense.expense_date >= date_from)
    if date_to is not None:
        query = query.where(Expense.expense_date <= date_to)
    return _money(db.scalar(query))


def _outstanding_total(db: DatabaseSession, branch_id: int | None) -> Decimal:
    paid_subquery = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.installment_id == FeeInstallment.id)
        .scalar_subquery()
    )
    query = (
        select(
            func.coalesce(
                func.sum(FeeInstallment.amount - paid_subquery), 0
            )
        )
        .join(FeePlan, FeeInstallment.fee_plan_id == FeePlan.id)
        .join(Enrollment, FeePlan.enrollment_id == Enrollment.id)
        .join(Batch, Enrollment.batch_id == Batch.id)
    )
    if branch_id is not None:
        query = query.where(Batch.branch_id == branch_id)
    return _money(db.scalar(query))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
@router.get(
    "/summary",
    response_model=FinanceSummary,
    dependencies=[Depends(FinanceAccess)],
)
def finance_summary(
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
    date_from: date | None = None,
    date_to: date | None = None,
) -> FinanceSummary:
    scope = branch_scope(current_user)
    fees = _collected_total(db, scope, date_from, date_to)
    expenses = _expense_total(db, scope, date_from, date_to)
    expense_gst = _expense_total(db, scope, date_from, date_to, gst_only=True)
    gst_payable = (_gst_component(fees) - expense_gst).quantize(Decimal("0.01"))

    bank_query = select(func.coalesce(func.sum(BankAccount.opening_balance), 0)).where(
        BankAccount.is_active.is_(True)
    )
    count_query = select(func.count(BankAccount.id)).where(
        BankAccount.is_active.is_(True)
    )
    if scope is not None:
        bank_query = bank_query.where(BankAccount.branch_id == scope)
        count_query = count_query.where(BankAccount.branch_id == scope)
    opening = _money(db.scalar(bank_query))
    active_accounts = int(db.scalar(count_query) or 0)

    lifetime_fees = _collected_total(db, scope)
    lifetime_expenses = _expense_total(db, scope)
    bank_balance = (opening + lifetime_fees - lifetime_expenses).quantize(
        Decimal("0.01")
    )

    expense_count = int(
        db.scalar(
            select(func.count(Expense.id)).where(
                Expense.branch_id == scope
            )
            if scope is not None
            else select(func.count(Expense.id))
        )
        or 0
    )

    return FinanceSummary(
        fees_collected=fees,
        expenses=expenses,
        net_income=(fees - expenses).quantize(Decimal("0.01")),
        outstanding_fees=_outstanding_total(db, scope),
        gst_payable=gst_payable,
        gst_rate_percent=GST_RATE_PERCENT,
        bank_balance=bank_balance,
        active_bank_accounts=active_accounts,
        expense_count=expense_count,
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
@router.get(
    "/expenses",
    response_model=list[ExpenseResponse],
    dependencies=[Depends(FinanceAccess)],
)
def list_expenses(
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
    category: str | None = Query(default=None, max_length=40),
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ExpenseResponse]:
    query = select(Expense).options(
        joinedload(Expense.branch), joinedload(Expense.recorded_by)
    )
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(Expense.branch_id == scope)
    if category:
        query = query.where(Expense.category == category)
    if date_from is not None:
        query = query.where(Expense.expense_date >= date_from)
    if date_to is not None:
        query = query.where(Expense.expense_date <= date_to)
    expenses = db.scalars(
        query.order_by(Expense.expense_date.desc(), Expense.id.desc())
    ).unique().all()
    return [
        _expense_response(
            expense,
            expense.recorded_by.full_name if expense.recorded_by else None,
        )
        for expense in expenses
    ]


@router.post(
    "/expenses",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(FinanceAccess)],
)
def create_expense(
    payload: ExpenseCreate,
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> ExpenseResponse:
    branch_id = _resolve_branch(current_user, payload.branch_id)
    _validate_branch(db, branch_id)
    if payload.gst_amount > payload.amount:
        raise HTTPException(
            status_code=400, detail="GST cannot be greater than the expense amount"
        )
    expense = Expense(
        branch_id=branch_id,
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        gst_amount=payload.gst_amount,
        expense_date=payload.expense_date,
        payment_method=payload.payment_method,
        vendor=payload.vendor,
        reference=payload.reference,
        notes=payload.notes,
        receipt_url=payload.receipt_url,
        recorded_by_id=current_user.id,
    )
    db.add(expense)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "expense_created",
        "expense",
        expense.id,
        payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(expense)
    return _expense_response(expense, current_user.full_name)


@router.patch(
    "/expenses/{expense_id}",
    response_model=ExpenseResponse,
    dependencies=[Depends(FinanceAccess)],
)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> ExpenseResponse:
    expense = db.scalar(
        select(Expense).options(joinedload(Expense.branch)).where(Expense.id == expense_id)
    )
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    check_branch_access(current_user, expense.branch_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    if "branch_id" in changes and changes["branch_id"] is not None:
        _resolve_branch(current_user, changes["branch_id"])
        _validate_branch(db, changes["branch_id"])
    amount = changes.get("amount", expense.amount)
    gst = changes.get("gst_amount", expense.gst_amount)
    if gst > amount:
        raise HTTPException(
            status_code=400, detail="GST cannot be greater than the expense amount"
        )
    for field, value in changes.items():
        setattr(expense, field, value)
    record_audit(
        db,
        current_user.id,
        "expense_updated",
        "expense",
        expense.id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(expense)
    return _expense_response(expense, current_user.full_name)


@router.delete(
    "/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(FinanceAccess)],
)
def delete_expense(
    expense_id: int,
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> None:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    check_branch_access(current_user, expense.branch_id)
    record_audit(
        db,
        current_user.id,
        "expense_deleted",
        "expense",
        expense.id,
        {"description": expense.description, "amount": str(expense.amount)},
    )
    db.delete(expense)
    db.commit()


# ---------------------------------------------------------------------------
# Bank accounts
# ---------------------------------------------------------------------------
@router.get(
    "/bank-accounts",
    response_model=list[BankAccountResponse],
    dependencies=[Depends(FinanceAccess)],
)
def list_bank_accounts(
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> list[BankAccountResponse]:
    query = select(BankAccount).options(joinedload(BankAccount.branch))
    scope = branch_scope(current_user)
    if scope is not None:
        query = query.where(BankAccount.branch_id == scope)
    accounts = db.scalars(query.order_by(BankAccount.bank_name, BankAccount.id)).all()
    return [_bank_response(account) for account in accounts]


@router.post(
    "/bank-accounts",
    response_model=BankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(FinanceAccess)],
)
def create_bank_account(
    payload: BankAccountCreate,
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> BankAccountResponse:
    branch_id = payload.branch_id
    if current_user.role.name != "Super Admin":
        branch_id = current_user.branch_id
    if branch_id is not None:
        check_branch_access(current_user, branch_id)
        _validate_branch(db, branch_id)
    account = BankAccount(
        branch_id=branch_id,
        account_name=payload.account_name,
        bank_name=payload.bank_name,
        account_number=payload.account_number,
        ifsc=payload.ifsc,
        opening_balance=payload.opening_balance,
        is_active=payload.is_active,
    )
    db.add(account)
    db.flush()
    record_audit(
        db,
        current_user.id,
        "bank_account_created",
        "bank_account",
        account.id,
        {"bank_name": account.bank_name, "account_name": account.account_name},
    )
    db.commit()
    db.refresh(account)
    return _bank_response(account)


@router.patch(
    "/bank-accounts/{account_id}",
    response_model=BankAccountResponse,
    dependencies=[Depends(FinanceAccess)],
)
def update_bank_account(
    account_id: int,
    payload: BankAccountUpdate,
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> BankAccountResponse:
    account = db.scalar(
        select(BankAccount)
        .options(joinedload(BankAccount.branch))
        .where(BankAccount.id == account_id)
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Bank account not found")
    if account.branch_id is not None:
        check_branch_access(current_user, account.branch_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were provided")
    if "branch_id" in changes and changes["branch_id"] is not None:
        check_branch_access(current_user, changes["branch_id"])
        _validate_branch(db, changes["branch_id"])
    for field, value in changes.items():
        setattr(account, field, value)
    record_audit(
        db,
        current_user.id,
        "bank_account_updated",
        "bank_account",
        account.id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(account)
    return _bank_response(account)


@router.delete(
    "/bank-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(FinanceAccess)],
)
def delete_bank_account(
    account_id: int,
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
) -> None:
    account = db.get(BankAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Bank account not found")
    if account.branch_id is not None:
        check_branch_access(current_user, account.branch_id)
    if current_user.role.name != "Super Admin" and account.branch_id is None:
        raise HTTPException(
            status_code=403, detail="Only head office can delete a shared account"
        )
    record_audit(
        db,
        current_user.id,
        "bank_account_deleted",
        "bank_account",
        account.id,
        {"bank_name": account.bank_name},
    )
    db.delete(account)
    db.commit()


# ---------------------------------------------------------------------------
# Cash book
# ---------------------------------------------------------------------------
@router.get(
    "/cashbook",
    response_model=CashBookResponse,
    dependencies=[Depends(FinanceAccess)],
)
def cash_book(
    db: DatabaseSession,
    current_user: User = Depends(FinanceUser),
    date_from: date | None = None,
    date_to: date | None = None,
) -> CashBookResponse:
    scope = branch_scope(current_user)

    # Opening balance: bank opening balances plus every fee received and every
    # expense paid before the window start.
    opening_query = select(func.coalesce(func.sum(BankAccount.opening_balance), 0)).where(
        BankAccount.is_active.is_(True)
    )
    if scope is not None:
        opening_query = opening_query.where(BankAccount.branch_id == scope)
    opening = _money(db.scalar(opening_query))
    if date_from is not None:
        day_before = date_from - timedelta(days=1)
        opening = opening + _collected_total(db, scope, None, day_before) - _expense_total(
            db, scope, None, day_before
        )

    payment_query = _fee_payment_query()
    expense_query = select(Expense).options(joinedload(Expense.branch))
    if scope is not None:
        payment_query = payment_query.where(Batch.branch_id == scope)
        expense_query = expense_query.where(Expense.branch_id == scope)
    if date_from is not None:
        payment_query = payment_query.where(Payment.payment_date >= date_from)
        expense_query = expense_query.where(Expense.expense_date >= date_from)
    if date_to is not None:
        payment_query = payment_query.where(Payment.payment_date <= date_to)
        expense_query = expense_query.where(Expense.expense_date <= date_to)

    entries: list[CashBookEntry] = []
    for payment, _installment, _plan, enrollment, _batch, branch in db.execute(
        payment_query
    ).all():
        entries.append(
            CashBookEntry(
                entry_date=payment.payment_date,
                entry_type="income",
                reference=payment.receipt_number,
                description=f"Fee payment · {enrollment.enrollment_code}",
                category="Fees",
                branch_name=branch.name,
                money_in=payment.amount,
                money_out=Decimal("0.00"),
            )
        )
    for expense in db.scalars(expense_query).unique().all():
        entries.append(
            CashBookEntry(
                entry_date=expense.expense_date,
                entry_type="expense",
                reference=expense.reference or f"EXP-{expense.id}",
                description=expense.description,
                category=expense.category,
                branch_name=expense.branch.name if expense.branch else "—",
                money_in=Decimal("0.00"),
                money_out=expense.amount,
            )
        )
    entries.sort(key=lambda entry: (entry.entry_date, entry.reference), reverse=True)
    total_in = sum((entry.money_in for entry in entries), Decimal("0.00"))
    total_out = sum((entry.money_out for entry in entries), Decimal("0.00"))
    return CashBookResponse(
        opening_balance=opening.quantize(Decimal("0.01")),
        closing_balance=(opening + total_in - total_out).quantize(Decimal("0.01")),
        total_in=total_in.quantize(Decimal("0.01")),
        total_out=total_out.quantize(Decimal("0.01")),
        entries=entries,
    )
