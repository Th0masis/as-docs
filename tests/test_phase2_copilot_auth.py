from __future__ import annotations

from as_docs.config import AIConfig
from as_docs.enricher.providers.copilot_client import (
    CopilotProvider,
    _is_sdk_auth_error,
    _sdk_auth_error_message,
)


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


def test_is_sdk_auth_error_detects_known_runtime_message() -> None:
    exc = RuntimeError(
        "Session error: Execution failed: Error: Session was not created with authentication info or custom provider"
    )
    assert _is_sdk_auth_error(exc) is True


def test_sdk_auth_error_message_mentions_configured_env_name() -> None:
    msg = _sdk_auth_error_message("MY_TOKEN")
    assert "MY_TOKEN" in msg
    assert "gh auth login" in msg


def test_request_maps_generic_sdk_auth_exception_to_runtime_error(monkeypatch) -> None:
    cfg = AIConfig()
    cfg.provider = "copilot"
    cfg.max_retries = 0

    monkeypatch.setattr(
        "as_docs.enricher.providers.copilot_client._resolve_github_token",
        lambda _env: None,
    )

    provider = CopilotProvider(cfg)

    def _boom(*_args, **_kwargs):
        raise Exception(
            "Session error: Execution failed: Error: Session was not created with authentication info or custom provider"
        )

    monkeypatch.setattr(provider, "_send_with_sdk", _boom)

    try:
        provider.enrich_pou("{}", "gpt-4.1", 128)
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Copilot SDK authentication failed" in str(exc)
