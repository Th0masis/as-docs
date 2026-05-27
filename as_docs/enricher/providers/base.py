from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EnrichmentPayload:
    description: str
    responsibilities: list[str]
    patterns: list[str] = field(default_factory=list)
    notes: str = ""


class AIProvider(Protocol):
    def enrich_task(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        ...

    def enrich_pou(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        ...
