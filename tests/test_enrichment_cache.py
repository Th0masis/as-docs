from __future__ import annotations

from pathlib import Path

from as_docs.enricher.cache import EnrichmentCache
from as_docs.enricher.providers.base import EnrichmentPayload

CONTENT = "PROGRAM Demo\nA := B;"


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = EnrichmentCache(tmp_path, provider="copilot", model="gpt-4.1")
    payload = EnrichmentPayload(
        description="desc",
        responsibilities=["r1", "r2"],
        patterns=["state machine"],
        notes="n",
    )

    cache.set("pou", "Main", 3, CONTENT, payload)
    loaded = cache.get("pou", "Main", 3, CONTENT)

    assert loaded is not None
    assert loaded.description == "desc"
    assert loaded.responsibilities == ["r1", "r2"]
    assert loaded.patterns == ["state machine"]


def test_cache_is_provider_separated(tmp_path: Path) -> None:
    cache_a = EnrichmentCache(tmp_path, provider="copilot", model="gpt-4.1")
    cache_b = EnrichmentCache(tmp_path, provider="anthropic", model="claude")

    payload = EnrichmentPayload(description="desc", responsibilities=["r"])
    cache_a.set("task", "Task1", 2, CONTENT, payload)

    assert cache_a.get("task", "Task1", 2, CONTENT) is not None
    assert cache_b.get("task", "Task1", 2, CONTENT) is None
