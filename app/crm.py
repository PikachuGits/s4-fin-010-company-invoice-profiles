"""S2-CRM integration stub (company directory).

The work order depends on S2-CRM for the canonical company name.  Per the
unified agreement the dependency is stubbed first: this module reads a JSON
fixture so tests and reviewers can run without S2-CRM.

Production integration point (single place to replace)::

    GET /internal/crm/companies/{company_id}   ->  {"id", "org_id", "name"}

Fixture format (all data fictitious)::

    {"companies": {"<company_uuid>": {"org_id": "<org_uuid>", "name": "..."}}}

The file path comes from ``CRM_COMPANIES_FILE`` or defaults to
``fixtures/crm_companies.json``.  The file is read on every call so a test can
point the variable at a temporary file without cache invalidation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

_DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "crm_companies.json"


@dataclass(frozen=True)
class CompanyRecord:
    """Minimal CRM company projection needed by this module."""

    id: UUID
    org_id: UUID
    name: str


class JsonCompanyDirectory:
    """Read-only company directory backed by a JSON fixture."""

    def __init__(self, path: Path | None = None) -> None:
        override = os.environ.get("CRM_COMPANIES_FILE")
        self.path = Path(override) if override else (path or _DEFAULT_FIXTURE)

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            raise RuntimeError(
                f"CRM company stub not found: {self.path}. "
                "Set CRM_COMPANIES_FILE or restore fixtures/crm_companies.json."
            )
        data = json.loads(self.path.read_text(encoding="utf-8"))
        companies = data.get("companies", {})
        if not isinstance(companies, dict):  # pragma: no cover - defensive
            raise RuntimeError("CRM company stub must contain a 'companies' object")
        return {str(key).lower(): value for key, value in companies.items()}

    def get_company(self, org_id: UUID, company_id: UUID) -> CompanyRecord | None:
        """Return the company iff it exists in this org, else ``None``."""

        raw = self._load().get(str(company_id).lower())
        if raw is None:
            return None
        record = CompanyRecord(
            id=company_id, org_id=UUID(str(raw["org_id"])), name=str(raw["name"])
        )
        if record.org_id != org_id:
            return None
        return record


def get_company_directory() -> JsonCompanyDirectory:
    """FastAPI dependency; override in tests or replace with the S2-CRM client."""

    return JsonCompanyDirectory()