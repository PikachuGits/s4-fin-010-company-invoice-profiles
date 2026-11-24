"""Request / response schemas for company invoice profiles."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import InvoiceType


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    tax_id: str = Field(min_length=1, max_length=40)
    registered_address: str | None = Field(default=None, max_length=300)
    registered_phone: str | None = Field(default=None, max_length=32)
    bank_name: str | None = Field(default=None, max_length=200)
    bank_account: str | None = Field(default=None, max_length=40)
    default_invoice_type: InvoiceType = InvoiceType.general
    receive_email: str | None = Field(default=None, max_length=200)
    receive_phone: str | None = Field(default=None, max_length=32)
    is_default: bool = False
    name_mismatch_reason: str | None = None


class ProfilePatch(BaseModel):
    """Partial update; only fields present in the payload are touched."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, min_length=1, max_length=40)
    registered_address: str | None = Field(default=None, max_length=300)
    registered_phone: str | None = Field(default=None, max_length=32)
    bank_name: str | None = Field(default=None, max_length=200)
    bank_account: str | None = Field(default=None, max_length=40)
    default_invoice_type: InvoiceType | None = None
    receive_email: str | None = Field(default=None, max_length=200)
    receive_phone: str | None = Field(default=None, max_length=32)
    is_default: bool | None = None
    name_mismatch_reason: str | None = None


class ProfileOut(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    tax_id: str
    registered_address: str | None
    registered_phone: str | None
    bank_name: str | None
    bank_account: str | None
    bank_account_masked: bool
    default_invoice_type: InvoiceType
    receive_email: str | None
    receive_phone: str | None
    is_default: bool
    name_mismatch_reason: str | None
    created_at: datetime
    updated_at: datetime


class ProfileListOut(BaseModel):
    items: list[ProfileOut]
    total: int