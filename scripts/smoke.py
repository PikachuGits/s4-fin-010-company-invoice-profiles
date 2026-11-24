#!/usr/bin/env python
"""Runtime smoke against a live uvicorn instance (all data fictitious).

Usage:
    DATABASE_URL=... .venv/bin/python scripts/smoke.py [--base http://127.0.0.1:8874]

Verifies the four acceptance criteria over real HTTP and prints the audit
rows written for the PATCH.  Exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import create_engine, text

from tests.factories import BANK_ACCOUNT, COMPANY_A, VALID_USCC, headers, profile_payload, url
import os


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8874")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base, timeout=10)
    ok = True

    # AC1: 18 位税号校验位错误 → 422
    bad = VALID_USCC[:17] + ("0" if VALID_USCC[17] != "0" else "1")
    r = client.post(url(), json=profile_payload(tax_id=bad), headers=headers())
    print(f"AC1 坏校验位创建 -> {r.status_code} {r.json()['detail'][0]['code']}")
    ok &= r.status_code == 422

    # AC2: 专票缺开户行/账号 → 422
    payload = profile_payload(default_invoice_type="special")
    payload.pop("bank_name")
    r = client.post(url(), json=payload, headers=headers())
    print(f"AC2 专票缺开户行 -> {r.status_code} {r.json()['detail'][0]['code']}")
    ok &= r.status_code == 422

    # 正常创建（专票四项齐全）
    r = client.post(url(), json=profile_payload(default_invoice_type="special"), headers=headers())
    pid = r.json()["id"]
    print(f"创建专票资料 -> {r.status_code} id={pid}")
    ok &= r.status_code == 201

    # AC3: 列表脱敏（财务角色也只看后4位）
    r = client.get(url(), headers=headers("finance"))
    item = r.json()["items"][0]
    print(f"AC3 列表银行账号 -> {item['bank_account']} (masked={item['bank_account_masked']})")
    ok &= item["bank_account"] == "****" + BANK_ACCOUNT[-4:] and BANK_ACCOUNT not in r.text

    # 详情：财务全量 / 非财务脱敏
    r = client.get(url(profile_id=pid), headers=headers("finance"))
    print(f"详情(财务) -> {r.json()['bank_account']}")
    ok &= r.json()["bank_account"] == BANK_ACCOUNT
    r = client.get(url(profile_id=pid), headers=headers("sales"))
    print(f"详情(销售) -> {r.json()['bank_account']}")
    ok &= r.json()["bank_account"] == "****" + BANK_ACCOUNT[-4:]

    # AC4: PATCH 写 1 条带前后差异的审计
    r = client.patch(url(profile_id=pid), json={"registered_phone": "022-99998888"}, headers=headers())
    print(f"PATCH 注册电话 -> {r.status_code}")
    ok &= r.status_code == 200
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, diff FROM finance_invoice_profile_change_log "
                "WHERE entity_id = :pid AND action = 'update' ORDER BY created_at"
            ),
            {"pid": pid},
        ).all()
    print(f"AC4 审计 update 行数 -> {len(rows)}; diff -> {rows[0][1] if rows else None}")
    ok &= len(rows) == 1 and rows[0][1] == {
        "registered_phone": {"old": "022-12345678", "new": "022-99998888"}
    }

    print("\nSMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())