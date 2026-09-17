from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ArtifactPatch:
    path: str
    content: str


@dataclass
class AiRefinementResult:
    applied: bool
    status: str
    message: str
    patches: list[ArtifactPatch] = field(default_factory=list)
    prompt: str | None = None
    raw_response: str | None = None


class AiRefinementProvider:
    def available(self) -> bool:
        raise NotImplementedError

    def refine(self, canonical_model: dict, artifacts: dict[str, str]) -> AiRefinementResult:
        raise NotImplementedError
