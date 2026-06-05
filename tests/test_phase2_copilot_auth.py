from __future__ import annotations

from as_docs.config import AIConfig
from as_docs.enricher.providers.copilot_client import CopilotProvider


def test_copilot_provider_init_allows_missing_token(monkeypatch) -> None:
    cfg = AIConfig()
    cfg.provider = "copilot"

    monkeypatch.setattr(
        "as_docs.enricher.providers.copilot_client._resolve_github_token",
        lambda _env: None,
    )

    provider = CopilotProvider(cfg)

    assert provider._github_login == "<unknown>"


def test_copilot_provider_init_allows_failed_preflight(monkeypatch) -> None:
    cfg = AIConfig()
    cfg.provider = "copilot"

    monkeypatch.setattr(
        "as_docs.enricher.providers.copilot_client._resolve_github_token",
        lambda _env: "fake-token",
    )

    def _raise(_token: str) -> str:
        raise RuntimeError("preflight failed")

    monkeypatch.setattr(
        "as_docs.enricher.providers.copilot_client._verify_copilot_entitlement",
        _raise,
    )

    provider = CopilotProvider(cfg)

    assert provider._github_login == "<unknown>"


def test_copilot_provider_init_keeps_login_when_preflight_passes(monkeypatch) -> None:
    cfg = AIConfig()
    cfg.provider = "copilot"

    monkeypatch.setattr(
        "as_docs.enricher.providers.copilot_client._resolve_github_token",
        lambda _env: "fake-token",
    )
    monkeypatch.setattr(
        "as_docs.enricher.providers.copilot_client._verify_copilot_entitlement",
        lambda _token: "octocat",
    )

    provider = CopilotProvider(cfg)

    assert provider._github_login == "octocat"
