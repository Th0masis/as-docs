from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from as_docs.enricher.providers.base import EnrichmentPayload


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0


class EnrichmentCache:
    def __init__(self, cache_dir: Path, provider: str, model: str) -> None:
        self._cache_dir = cache_dir
        self._provider = provider
        self._model = model
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, scope: str, name: str, level: int, content: str) -> EnrichmentPayload | None:
        path = self._path_for(scope=scope, name=name, level=level, content=content)
        if not path.exists():
            return None

        raw = json.loads(path.read_text(encoding="utf-8"))
        return EnrichmentPayload(
            description=str(raw.get("description", "")),
            responsibilities=[str(x) for x in raw.get("responsibilities", [])],
            patterns=[str(x) for x in raw.get("patterns", [])],
            notes=str(raw.get("notes", "")),
        )

    def set(self, scope: str, name: str, level: int, content: str, payload: EnrichmentPayload) -> None:
        path = self._path_for(scope=scope, name=name, level=level, content=content)
        data = {
            "provider": self._provider,
            "model": self._model,
            "description": payload.description,
            "responsibilities": payload.responsibilities,
            "patterns": payload.patterns,
            "notes": payload.notes,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _path_for(self, scope: str, name: str, level: int, content: str) -> Path:
        digest = _hash_content(content)
        safe_model = self._model.replace("/", "_").replace(":", "_")
        safe_name = name.replace(" ", "_")
        filename = f"{scope}.{safe_name}.L{level}.{self._provider}.{safe_model}.{digest}.json"
        return self._cache_dir / filename


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
