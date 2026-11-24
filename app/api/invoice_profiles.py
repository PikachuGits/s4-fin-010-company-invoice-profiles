"""Company invoice-profile endpoints (S4-FIN-010).

Routes (per work order)::

    GET    /api/finance/companies/{company_id}/invoice-profiles
    POST   /api/finance/companies/{company_id}/invoice-profiles
    GET    /api/finance/companies/{company_id}/invoice-profiles/{profile_id}
    PATCH  /api/finance/companies/{company_id}/invoice-profiles/{profile_id}
    DELETE /api/finance/companies/{company_id}/invoice-profiles/{profile_id}

Masking policy: the list endpoint always masks the bank account to the last
4 digits; the detail endpoint returns the full account only for the finance
role.  Every mutation writes audit rows (before/after diff) in the same
transaction — one row per touched profile (a default transfer touches two).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import validators as v
from app.audit import AuditSink, field_diff, get_audit_sink, snapshot
from app.crm import CompanyRecord, JsonCompanyDirectory, get_company_directory
from app.db import get_session
from app.enums import InvoiceType
from app.iam import Principal, get_principal
from app.models.invoice_profile import CompanyInvoiceProfile
from app.schemas.invoice import ProfileCreate, ProfileListOut, ProfileOut, ProfilePatch

router = APIRouter(
    prefix="/api/finance/companies/{company_id}/invoice-profiles",
    tags=["invoice-profiles"],
)


def _company_or_404(
    directory: JsonCompanyDirectory, principal: Principal, company_id: UUID
) -> CompanyRecord:
    company = directory.get_company(principal.org_id, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company_not_found")
    return company


def _profile_or_404(
    session: Session, principal: Principal, company_id: UUID, profile_id: UUID
) -> CompanyInvoiceProfile:
    stmt = select(CompanyInvoiceProfile).where(
        CompanyInvoiceProfile.id == profile_id,
        CompanyInvoiceProfile.company_id == company_id,
        CompanyInvoiceProfile.org_id == principal.org_id,
        CompanyInvoiceProfile.deleted_at.is_(None),
    )
    profile = session.execute(stmt).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="invoice_profile_not_found")
    return profile


def _fail(failure: v.ValidationFailure) -> None:
    raise HTTPException(status_code=422, detail=[failure.as_detail()])


def _serialize(
    profile: CompanyInvoiceProfile, principal: Principal, *, allow_full: bool
) -> ProfileOut:
    full = allow_full and principal.can_view_full_account
    return ProfileOut(
        id=profile.id,
        company_id=profile.company_id,
        title=profile.title,
        tax_id=profile.tax_id,
        registered_address=profile.registered_address,
        registered_phone=profile.registered_phone,
        bank_name=profile.bank_name,
        bank_account=profile.bank_account if full else v.mask_bank_account(profile.bank_account),
        bank_account_masked=not full and profile.bank_account is not None,
        default_invoice_type=InvoiceType(profile.default_invoice_type),
        receive_email=profile.receive_email,
        receive_phone=profile.receive_phone,
        is_default=profile.is_default,
        name_mismatch_reason=profile.name_mismatch_reason,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _current_default(
    session: Session, principal: Principal, company_id: UUID, *, lock: bool = False
) -> CompanyInvoiceProfile | None:
    stmt = select(CompanyInvoiceProfile).where(
        CompanyInvoiceProfile.org_id == principal.org_id,
        CompanyInvoiceProfile.company_id == company_id,
        CompanyInvoiceProfile.is_default.is_(True),
        CompanyInvoiceProfile.deleted_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    return session.execute(stmt).scalar_one_or_none()


def _active_profiles(
    session: Session, principal: Principal, company_id: UUID
) -> list[CompanyInvoiceProfile]:
    stmt = (
        select(CompanyInvoiceProfile)
        .where(
            CompanyInvoiceProfile.org_id == principal.org_id,
            CompanyInvoiceProfile.company_id == company_id,
            CompanyInvoiceProfile.deleted_at.is_(None),
        )
        .order_by(
            CompanyInvoiceProfile.is_default.desc(),
            CompanyInvoiceProfile.created_at.asc(),
        )
    )
    return list(session.execute(stmt).scalars())


@router.get("", response_model=ProfileListOut)
def list_profiles(
    company_id: UUID,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    directory: JsonCompanyDirectory = Depends(get_company_directory),
) -> ProfileListOut:
    """列表：银行账号一律只显示后 4 位（财务角色也一样，全量走详情接口）。"""

    _company_or_404(directory, principal, company_id)
    profiles = _active_profiles(session, principal, company_id)
    items = [_serialize(p, principal, allow_full=False) for p in profiles]
    return ProfileListOut(items=items, total=len(items))


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(
    company_id: UUID,
    profile_id: UUID,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    directory: JsonCompanyDirectory = Depends(get_company_directory),
) -> ProfileOut:
    """详情：完整银行账号仅财务角色可见。"""

    _company_or_404(directory, principal, company_id)
    profile = _profile_or_404(session, principal, company_id, profile_id)
    return _serialize(profile, principal, allow_full=True)


@router.post("", response_model=ProfileOut, status_code=201)
def create_profile(
    company_id: UUID,
    payload: ProfileCreate,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    directory: JsonCompanyDirectory = Depends(get_company_directory),
    audit: AuditSink = Depends(get_audit_sink),
) -> ProfileOut:
    company = _company_or_404(directory, principal, company_id)

    try:
        tax_id = v.validate_tax_id(payload.tax_id)
        bank_account = v.normalize_bank_account(payload.bank_account)
        address = (payload.registered_address or "").strip() or None
        phone = v.validate_phone("registered_phone", payload.registered_phone)
        bank_name = (payload.bank_name or "").strip() or None
        v.validate_special_invoice_fields(
            payload.default_invoice_type.value,
            registered_address=address,
            registered_phone=phone,
            bank_name=bank_name,
            bank_account=bank_account,
        )
        reason = v.validate_name_mismatch(
            payload.title, company.name, payload.name_mismatch_reason
        )
        email = v.validate_email(payload.receive_email)
        receive_phone = v.validate_phone("receive_phone", payload.receive_phone)
    except v.ValidationFailure as failure:
        _fail(failure)

    existing = _active_profiles(session, principal, company_id)
    is_default = payload.is_default or not existing

    # 默认切换：同事务内先降级现默认，并为被改动的资料各写一条审计。
    if is_default and existing:
        current = _current_default(session, principal, company_id, lock=True)
        if current is not None:
            old = snapshot(current)
            current.is_default = False
            session.flush()
            audit.record(
                session, principal, profile=current, action="update",
                old=old, new=snapshot(current),
            )

    profile = CompanyInvoiceProfile(
        org_id=principal.org_id,
        site_id=principal.site_id,
        company_id=company_id,
        title=payload.title.strip(),
        tax_id=tax_id,
        registered_address=address,
        registered_phone=phone,
        bank_name=bank_name,
        bank_account=bank_account,
        default_invoice_type=payload.default_invoice_type.value,
        receive_email=email,
        receive_phone=receive_phone,
        is_default=is_default,
        name_mismatch_reason=reason,
        created_by=principal.user_id,
    )
    session.add(profile)
    session.flush()
    audit.record(
        session, principal, profile=profile, action="create",
        old=None, new=snapshot(profile),
    )
    session.commit()
    return _serialize(profile, principal, allow_full=True)


@router.patch("/{profile_id}", response_model=ProfileOut)
def patch_profile(
    company_id: UUID,
    profile_id: UUID,
    payload: ProfilePatch,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    directory: JsonCompanyDirectory = Depends(get_company_directory),
    audit: AuditSink = Depends(get_audit_sink),
) -> ProfileOut:
    company = _company_or_404(directory, principal, company_id)
    profile = _profile_or_404(session, principal, company_id, profile_id)
    changes = payload.model_dump(exclude_unset=True)

    for required_field in ("title", "tax_id", "default_invoice_type"):
        if required_field in changes and changes[required_field] is None:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "field": required_field,
                    "code": "null_not_allowed",
                    "message": "该字段为必填，不能置空",
                }],
            )

    if changes.get("is_default") is False and profile.is_default:
        raise HTTPException(
            status_code=422,
            detail=[{
                "field": "is_default",
                "code": "default_transfer_required",
                "message": "不能直接取消默认，请将另一份资料设为默认",
            }],
        )

    merged = {
        "title": changes.get("title", profile.title),
        "tax_id": changes.get("tax_id", profile.tax_id),
        "registered_address": changes.get("registered_address", profile.registered_address),
        "registered_phone": changes.get("registered_phone", profile.registered_phone),
        "bank_name": changes.get("bank_name", profile.bank_name),
        "bank_account": changes.get("bank_account", profile.bank_account),
        "default_invoice_type": (
            changes["default_invoice_type"].value
            if "default_invoice_type" in changes
            else profile.default_invoice_type
        ),
        "receive_email": changes.get("receive_email", profile.receive_email),
        "receive_phone": changes.get("receive_phone", profile.receive_phone),
        "name_mismatch_reason": changes.get("name_mismatch_reason", profile.name_mismatch_reason),
    }

    try:
        merged["tax_id"] = v.validate_tax_id(merged["tax_id"])
        merged["bank_account"] = v.normalize_bank_account(merged["bank_account"])
        merged["registered_address"] = (merged["registered_address"] or "").strip() or None
        merged["registered_phone"] = v.validate_phone("registered_phone", merged["registered_phone"])
        merged["bank_name"] = (merged["bank_name"] or "").strip() or None
        v.validate_special_invoice_fields(
            merged["default_invoice_type"],
            registered_address=merged["registered_address"],
            registered_phone=merged["registered_phone"],
            bank_name=merged["bank_name"],
            bank_account=merged["bank_account"],
        )
        merged["name_mismatch_reason"] = v.validate_name_mismatch(
            merged["title"], company.name, merged["name_mismatch_reason"]
        )
        merged["receive_email"] = v.validate_email(merged["receive_email"])
        merged["receive_phone"] = v.validate_phone("receive_phone", merged["receive_phone"])
        merged["title"] = merged["title"].strip()
    except v.ValidationFailure as failure:
        _fail(failure)

    old = snapshot(profile)

    # 设为默认：同事务降级现默认并写审计。
    if changes.get("is_default") is True and not profile.is_default:
        current = _current_default(session, principal, company_id, lock=True)
        if current is not None and current.id != profile.id:
            current_old = snapshot(current)
            current.is_default = False
            session.flush()
            audit.record(
                session, principal, profile=current, action="update",
                old=current_old, new=snapshot(current),
            )
        profile.is_default = True
    elif "is_default" in changes and changes["is_default"] is not None:
        profile.is_default = changes["is_default"]

    for field, value in merged.items():
        setattr(profile, field, value)

    session.flush()
    new = snapshot(profile)
    if field_diff(old, new):
        audit.record(
            session, principal, profile=profile, action="update", old=old, new=new
        )
    session.commit()
    return _serialize(profile, principal, allow_full=True)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(
    company_id: UUID,
    profile_id: UUID,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    directory: JsonCompanyDirectory = Depends(get_company_directory),
    audit: AuditSink = Depends(get_audit_sink),
) -> Response:
    """软删除；若删的是默认且还有其余资料，自动提升最早创建的一份为默认。"""

    _company_or_404(directory, principal, company_id)
    profile = _profile_or_404(session, principal, company_id, profile_id)

    old = snapshot(profile)
    was_default = profile.is_default
    profile.deleted_at = datetime.now(timezone.utc)
    profile.is_default = False
    session.flush()
    audit.record(
        session, principal, profile=profile, action="delete", old=old, new=None
    )

    if was_default:
        remaining = _active_profiles(session, principal, company_id)
        if remaining:
            promoted = remaining[0]
            promoted_old = snapshot(promoted)
            promoted.is_default = True
            session.flush()
            audit.record(
                session, principal, profile=promoted, action="update",
                old=promoted_old, new=snapshot(promoted),
            )

    session.commit()
    return Response(status_code=204)