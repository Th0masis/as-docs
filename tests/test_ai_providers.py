from __future__ import annotations

import pytest

from as_docs.config import Config
from as_docs.enricher.providers.anthropic_client import (
    _normalize_payload as anthropic_normalize,
)
from as_docs.enricher.providers.copilot_client import (
    _normalize_payload as copilot_normalize,
)
from as_docs.enricher.providers.factory import create_provider


class _DummyProvider:
    def __init__(self, ai_cfg) -> None:
        self.ai_cfg = ai_cfg


def test_factory_returns_copilot_provider(monkeypatch) -> None:
    cfg = Config()
    cfg.ai.provider = "copilot"

    monkeypatch.setattr(
        "as_docs.enricher.providers.factory.CopilotProvider", _DummyProvider
    )

    provider = create_provider(cfg)
    assert isinstance(provider, _DummyProvider)
    assert provider.ai_cfg.provider == "copilot"


def test_factory_returns_anthropic_provider(monkeypatch) -> None:
    cfg = Config()
    cfg.ai.provider = "anthropic"

    monkeypatch.setattr(
        "as_docs.enricher.providers.factory.AnthropicProvider", _DummyProvider
    )

    provider = create_provider(cfg)
    assert isinstance(provider, _DummyProvider)
    assert provider.ai_cfg.provider == "anthropic"


def test_factory_rejects_unknown_provider() -> None:
    cfg = Config()
    cfg.ai.provider = "unknown"

    with pytest.raises(RuntimeError, match="Unsupported ai.provider"):
        create_provider(cfg)


def test_provider_normalization_contract_parity() -> None:
    raw = {
        "description": "  Handles motor state transitions. ",
        "responsibilities": [" Read inputs ", "Update outputs", ""],
        "patterns": [" state machine ", ""],
        "notes": "  Uses TON for debounce.  ",
    }

    copilot_payload = copilot_normalize(raw)
    anthropic_payload = anthropic_normalize(raw)

    assert copilot_payload.description == anthropic_payload.description
    assert copilot_payload.responsibilities == anthropic_payload.responsibilities
    assert copilot_payload.patterns == anthropic_payload.patterns
    assert copilot_payload.notes == anthropic_payload.notes


def test_provider_normalization_contract_parity_with_non_list_patterns() -> None:
    raw = {
        "description": "Task summary",
        "responsibilities": ["One"],
        "patterns": "not-a-list",
        "notes": "",
    }

    copilot_payload = copilot_normalize(raw)
    anthropic_payload = anthropic_normalize(raw)

    assert copilot_payload.patterns == []
    assert anthropic_payload.patterns == []
