"""Audit writing for invoice-profile mutations.

``LocalChangeLogSink`` is the S2-AUDIT stub allowed by the work order: it
writes to ``finance_invoice_profile_change_log`` inside the caller's
transaction.  Production replaces this class with a client for
``POST /internal/audit/events`` (same payload shape); no other module changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.iam import Principal
from app.models.change_log import InvoiceProfileChangeLog
from app.models.invoice_profile import CompanyInvoiceProfile

# Fields captured in snapshots and diffs (business columns only).
AUDITED_FIELDS = (
    "company_id",
    "title",
    "tax_id",
    "registered_address",
    "registered_phone",
    "bank_name",
    "bank_account",
    "default_invoice_type",
    "receive_email",
    "receive_phone",
    "is_default",
    "name_mismatch_reason",
)


def snapshot(profile: CompanyInvoiceProfile) -> dict:
    """JSON-safe full snapshot of the audited business fields."""

    data: dict = {}
    for field in AUDITED_FIELDS:
        value = getattr(profile, field)
        if isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, datetime):  # pragma: no cover - defensive
            value = value.isoformat()
        data[field] = value
    return data


def field_diff(old: dict | None, new: dict | None) -> dict:
    """Field-level ``{field: {"old": ..., "new": ...}}`` diff."""

    old = old or {}
    new = new or {}
    diff: dict = {}
    for field in AUDITED_FIELDS:
        before, after = old.get(field), new.get(field)
        if before != after:
            diff[field] = {"old": before, "new": after}
    return diff


class AuditSink(Protocol):
    def record(
        self,
        session: Session,
        principal: Principal,
        *,
        profile: CompanyInvoiceProfile,
        action: str,
        old: dict | None,
        new: dict | None,
    ) -> None: ...


class LocalChangeLogSink:
    """Write one audit row per touched profile, in the same transaction."""

    def record(
        self,
        session: Session,
        principal: Principal,
        *,
        profile: CompanyInvoiceProfile,
        action: str,
        old: dict | None,
        new: dict | None,
    ) -> None:
        session.add(
            InvoiceProfileChangeLog(
                org_id=principal.org_id,
                site_id=principal.site_id,
                entity_id=profile.id,
                company_id=profile.company_id,
                action=action,
                old_value=old,
                new_value=new,
                diff=field_diff(old, new),
                operator_id=principal.user_id,
                created_by=principal.user_id,
            )
        )


def get_audit_sink() -> AuditSink:
    """FastAPI dependency; replace with the S2-AUDIT client in production."""

    return LocalChangeLogSink()