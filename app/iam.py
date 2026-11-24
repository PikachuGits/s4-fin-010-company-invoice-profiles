"""S2-IAM integration stub.

The work order allows dependent modules to be mocked.  This module is the
single identity integration point: ``get_principal`` reads the authenticated
principal from trusted headers injected by the gateway.  In production this
dependency is replaced by an S2-IAM token introspection call; nothing else in
the code base needs to change.

Only the four headers below are trusted, and only behind the gateway.  Do not
expose this app directly to the internet without replacing the dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException

from app.enums import FinanceRole


@dataclass(frozen=True)
class Principal:
    """Authenticated caller plus the tenant scope resolved by S2-IAM."""

    user_id: UUID
    org_id: UUID
    site_id: UUID
    role: FinanceRole

    @property
    def can_view_full_account(self) -> bool:
        """Full bank account numbers are restricted to the finance role."""

        return self.role is FinanceRole.finance


def get_principal(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_site_id: str | None = Header(default=None, alias="X-Site-Id"),
    x_role: str | None = Header(default=None, alias="X-Role"),
) -> Principal:
    """Resolve the caller; missing or malformed identity headers yield 401."""

    if not all((x_user_id, x_org_id, x_site_id, x_role)):
        raise HTTPException(status_code=401, detail="missing_identity_headers")
    try:
        role = FinanceRole(x_role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid_role") from exc
    try:
        return Principal(
            user_id=UUID(x_user_id),
            org_id=UUID(x_org_id),
            site_id=UUID(x_site_id),
            role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid_identity_headers") from exc