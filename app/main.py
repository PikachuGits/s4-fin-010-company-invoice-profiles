"""FastAPI application factory for the S4-FIN-010 delivery."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.invoice_profiles import router as invoice_profiles_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="Company Invoice Profiles API (S4-FIN-010)",
        version="0.1.0",
        description="企业开票资料的维护、校验与脱敏（会员空间平台 · 回款与开票对接）",
    )
    application.include_router(invoice_profiles_router)
    return application


app = create_app()