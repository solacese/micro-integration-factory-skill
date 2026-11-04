"""Small advisor API: no database, Redis, or retired control plane required."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from spec2event.services.advisor_service import AdvisorService

app = FastAPI(title="MI v1 Factory", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://solacese.github.io", "http://localhost:8086"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
advisor = AdvisorService()


class ChatRequest(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=16)
    coreJava: str = Field(default="", max_length=45_000)
    coreGo: str = Field(default="", max_length=45_000)
    confirmationToken: str = Field(default="", max_length=24_000)


class ValidationRequest(BaseModel):
    jobId: str = Field(min_length=32, max_length=32)
    validationToken: str = Field(max_length=2000)


@app.post("/validation/status")
def validation_status(request: ValidationRequest):
    try:
        return advisor.validator.status(request.jobId, request.validationToken)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": "SAP AI Core",
        "configured": bool(os.getenv("AI_CORE_SECRET_ID") or os.getenv("SAP_CLIENT_ID")),
    }


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        return advisor.respond(
            request.messages, request.coreJava, request.confirmationToken, request.coreGo
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except (RuntimeError, TimeoutError):
        raise HTTPException(
            502, "The build service could not complete this request. Please retry."
        ) from None
