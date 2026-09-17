from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spec2event.api.routes import router
from spec2event.config import get_settings

settings = get_settings()

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(settings.log_level.upper()))

app = FastAPI(
    title="Spec2Event API",
    version="0.1.0",
    description="OpenAPI to Solace MDK generation and deployment orchestration API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.next_public_app_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
