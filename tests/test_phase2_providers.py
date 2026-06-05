from __future__ import annotations

import pytest

from as_docs.config import Config
from as_docs.enricher.providers.factory import create_provider


class _DummyProvider:
    def __init__(self, ai_cfg) -> None:
        self.ai_cfg = ai_cfg


def test_factory_returns_copilot_provider(monkeypatch) -> None:
    cfg = Config()
    cfg.ai.provider = "copilot"

    monkeypatch.setattr("as_docs.enricher.providers.factory.CopilotProvider", _DummyProvider)

    provider = create_provider(cfg)
    assert isinstance(provider, _DummyProvider)
    assert provider.ai_cfg.provider == "copilot"


def test_factory_returns_anthropic_provider(monkeypatch) -> None:
    cfg = Config()
    cfg.ai.provider = "anthropic"

    monkeypatch.setattr("as_docs.enricher.providers.factory.AnthropicProvider", _DummyProvider)

    provider = create_provider(cfg)
    assert isinstance(provider, _DummyProvider)
    assert provider.ai_cfg.provider == "anthropic"


def test_factory_rejects_unknown_provider() -> None:
    cfg = Config()
    cfg.ai.provider = "unknown"

    with pytest.raises(RuntimeError, match="Unsupported ai.provider"):
        create_provider(cfg)
