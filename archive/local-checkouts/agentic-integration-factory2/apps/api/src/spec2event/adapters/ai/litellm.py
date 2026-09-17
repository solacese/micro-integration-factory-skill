from __future__ import annotations

import json
from typing import Any

import httpx

from spec2event.adapters.ai.base import AiRefinementProvider, AiRefinementResult, ArtifactPatch

ALLOWED_AI_PATH_SUFFIXES = (
    ".md",
    ".yml",
    ".yaml",
    ".json",
    "CanonicalEventService.java",
    "README.md",
)
MAX_MODEL_OPERATIONS = 8
MAX_ARTIFACTS = 6
MAX_ARTIFACT_CHARS = 2500
AI_TIMEOUT_SECONDS = 90.0


class LiteLLMRefinementProvider(AiRefinementProvider):
    def __init__(self, *, base_url: str | None, api_key: str | None, model: str | None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"

    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def refine(self, canonical_model: dict, artifacts: dict[str, str]) -> AiRefinementResult:
        if not self.available():
            return AiRefinementResult(
                applied=False, status="not_configured", message="LiteLLM is not configured"
            )

        allowlisted = {
            path: content
            for path, content in artifacts.items()
            if path.endswith(ALLOWED_AI_PATH_SUFFIXES)
        }
        if not allowlisted:
            return AiRefinementResult(
                applied=False,
                status="not_configured",
                message="No allowlisted artifacts for AI refinement",
            )

        summarized_model = json.dumps(_summarize_canonical_model(canonical_model), indent=2)
        summarized_artifacts = json.dumps(_summarize_artifacts(allowlisted), indent=2)
        prompt = (
            "You are refining an OSS Solace MDK micro-integration project.\n"
            "Return JSON only using this shape: "
            '{"patches":[{"path":"...","content":"..."}],"message":"..."}.\n'
            "Only modify allowlisted files. Improve naming, mapping comments, "
            "sample payloads, and README clarity.\n"
            "If you edit Java, preserve package names, class names, imports, "
            "fields, and every existing public method signature and return type. "
            "Do not delete methods used by controllers or change runtime behavior.\n"
            f"Canonical model:\n{summarized_model}\n"
            f"Artifacts:\n{summarized_artifacts}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You output strict JSON and do not add prose outside JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(
                _chat_completion_url(self.base_url),
                headers=headers,
                json=payload,
                timeout=httpx.Timeout(AI_TIMEOUT_SECONDS, connect=5.0),
            )
            response.raise_for_status()
        except Exception as exc:
            return AiRefinementResult(
                applied=False,
                status="failed",
                message=f"LiteLLM request failed: {exc}",
                prompt=prompt,
            )

        raw_response = response.text
        try:
            content = response.json()["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            patches = [
                ArtifactPatch(path=item["path"], content=item["content"])
                for item in parsed.get("patches", [])
                if isinstance(item, dict)
            ]
            safe_patches = [patch for patch in patches if patch.path in allowlisted]
            return AiRefinementResult(
                applied=bool(safe_patches),
                status="completed" if safe_patches else "partial",
                message=parsed.get("message", "AI refinement completed"),
                patches=safe_patches,
                prompt=prompt,
                raw_response=raw_response,
            )
        except Exception as exc:
            return AiRefinementResult(
                applied=False,
                status="failed",
                message=f"Unable to parse LiteLLM response: {exc}",
                prompt=prompt,
                raw_response=raw_response,
            )


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]
    return json.loads(content)


def _chat_completion_url(base_url: str) -> str:
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _summarize_canonical_model(canonical_model: dict[str, Any]) -> dict[str, Any]:
    operations = canonical_model.get("operations", [])
    summarized_operations = []
    for operation in operations[:MAX_MODEL_OPERATIONS]:
        summarized_operations.append(
            {
                "operationId": operation.get("operationId"),
                "method": operation.get("method"),
                "path": operation.get("path"),
                "summary": operation.get("summary"),
                "emitsEvent": operation.get("emitsEvent"),
                "eventCandidates": operation.get("eventCandidates", [])[:2],
            }
        )
    return {
        "serviceName": canonical_model.get("serviceName"),
        "serviceVersion": canonical_model.get("serviceVersion"),
        "topics": canonical_model.get("topics", [])[:12],
        "schemaNames": canonical_model.get("schemaNames", [])[:12],
        "applicationNames": canonical_model.get("applicationNames", [])[:6],
        "operations": summarized_operations,
    }


def _summarize_artifacts(artifacts: dict[str, str]) -> dict[str, str]:
    summarized: dict[str, str] = {}
    for path in sorted(artifacts)[:MAX_ARTIFACTS]:
        content = artifacts[path]
        summarized[path] = content[:MAX_ARTIFACT_CHARS]
    return summarized
