"""Background automation for scheduled notifications and certificates.

The loop is only started when ``AUTOMATION_ENABLED`` is true. It defaults to a
dry run, and every delivery still requires SMTP/WhatsApp credentials, so a
misconfigured environment cannot message students by accident.
"""
from __future__ import annotations

import asyncio
import logging

from app.api.certificates import auto_issue_documents
from app.core.config import (
    AUTOMATION_AUTO_CERTIFICATES,
    AUTOMATION_CHANNELS,
    AUTOMATION_COOLDOWN_DAYS,
    AUTOMATION_DRY_RUN,
    AUTOMATION_FEE_REMINDER_DAYS,
    AUTOMATION_INTERVAL_HOURS,
)
from app.db.database import SessionLocal
from app.services.notifications import CATEGORIES, run_notifications


logger = logging.getLogger("nict.automation")


async def daily_notification_loop() -> None:
    """Run the notification sweep once, then repeat on a fixed interval."""
    interval = max(AUTOMATION_INTERVAL_HOURS, 0.25) * 3600
    # Give the API a moment to finish starting before the first sweep.
    await asyncio.sleep(45)
    while True:
        try:
            with SessionLocal() as db:
                plans = run_notifications(
                    db,
                    categories=list(CATEGORIES),
                    channels=list(AUTOMATION_CHANNELS),
                    days_ahead=AUTOMATION_FEE_REMINDER_DAYS,
                    dry_run=AUTOMATION_DRY_RUN,
                    triggered_by_id=None,
                    cooldown_days=AUTOMATION_COOLDOWN_DAYS,
                )
                logger.info(
                    "Automation sweep finished (dry_run=%s): %s planned, %s sent, %s skipped, %s failed",
                    AUTOMATION_DRY_RUN,
                    len(plans),
                    sum(1 for plan in plans if plan.status == "sent"),
                    sum(1 for plan in plans if plan.status == "skipped"),
                    sum(1 for plan in plans if plan.status == "failed"),
                )
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("Notification sweep failed")

        if AUTOMATION_AUTO_CERTIFICATES:
            try:
                with SessionLocal() as db:
                    result = auto_issue_documents(
                        db,
                        document_type="certificate",
                        dry_run=AUTOMATION_DRY_RUN,
                    )
                    logger.info(
                        "Certificate sweep finished (dry_run=%s): scanned=%s issued=%s skipped=%s completed=%s",
                        result.dry_run,
                        result.scanned,
                        result.issued,
                        result.skipped,
                        result.completed_enrollments,
                    )
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception("Certificate sweep failed")

        await asyncio.sleep(interval)
