from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from as_docs.config import AIConfig
from as_docs.enricher.providers.base import EnrichmentPayload


SYSTEM_INSTRUCTION = (
    "You are a documentation assistant for B&R Automation Studio projects. "
    "Return strict JSON only with keys: description, responsibilities, patterns, notes."
)

_GH_API = "https://api.github.com"
_COPILOT_TOKEN_URL = f"{_GH_API}/copilot_internal/v2/token"


def _resolve_github_token(api_key_env: str = "GITHUB_TOKEN") -> str | None:
    """Return a GitHub token from the first available source.

    Priority:
    1. Environment variable named by *api_key_env* (config-defined, e.g. ``GITHUB_TOKEN``).
    2. ``GH_TOKEN`` standard GitHub CLI env var.
    3. ``gh auth token`` from the GitHub CLI (used by VS Code's GitHub extension).
    """
    for var in (api_key_env, "GH_TOKEN", "GITHUB_TOKEN"):
        tok = os.getenv(var, "").strip()
        if tok:
            return tok

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            tok = result.stdout.strip()
            if tok:
                return tok
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def _verify_copilot_entitlement(token: str) -> str:
    """Verify *token* is valid and the account has a Copilot entitlement.

    Returns the GitHub login on success; raises :class:`RuntimeError` otherwise.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "as-docs",
    }

    # Step 1: resolve the GitHub login.
    try:
        req = urllib.request.Request(f"{_GH_API}/user", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            user_data = json.loads(resp.read())
        login: str = user_data.get("login") or "<unknown>"
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GitHub token is invalid or expired (HTTP {exc.code}). "
            "Sign in to GitHub in VS Code or run 'gh auth login'."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not reach GitHub API to verify credentials: {exc}") from exc

    # Step 2: verify Copilot entitlement via the internal token endpoint.
    try:
        req = urllib.request.Request(_COPILOT_TOKEN_URL, headers=headers)
        urllib.request.urlopen(req, timeout=10).close()  # noqa: S310
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 422):
            raise RuntimeError(
                f"GitHub account '{login}' does not have an active Copilot subscription. "
                "Visit https://github.com/features/copilot to subscribe."
            ) from exc
        # Unexpected HTTP error – treat as a transient network issue, not a hard block.
        # Log and continue; the SDK itself will surface a cleaner error if Copilot is unavailable.
    except Exception:
        pass  # Network failure during entitlement probe — let the SDK handle it.

    return login


class CopilotProvider:
    def __init__(self, ai_config: AIConfig) -> None:
        self._cfg = ai_config
        token = _resolve_github_token(ai_config.api_key_env)
        if not token:
            raise RuntimeError(
                "No GitHub authentication found. "
                "Sign in to GitHub in VS Code, install the GitHub CLI and run "
                "'gh auth login', or set the GITHUB_TOKEN environment variable."
            )
        login = _verify_copilot_entitlement(token)
        self._github_login = login
        # Do NOT store the raw token — the Copilot SDK auto-discovers
        # VS Code credentials at runtime.

    def enrich_task(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def enrich_pou(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def _request(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        max_attempts = self._cfg.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                content = self._send_with_sdk(prompt=prompt, model=model, max_tokens=max_tokens)
                raw_json = _extract_json_block(content)
                parsed = json.loads(raw_json)
                return _normalize_payload(parsed)
            except (RuntimeError, TimeoutError) as exc:
                if attempt >= max_attempts:
                    raise RuntimeError(f"Copilot provider request failed: {exc}") from exc
                time.sleep(0.4 * attempt)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Copilot provider returned invalid JSON: {exc}") from exc

        raise RuntimeError("Copilot provider request failed after retries.")

    def _send_with_sdk(self, prompt: str, model: str, max_tokens: int) -> str:
        try:
            return asyncio.run(self._send_with_sdk_async(prompt=prompt, model=model, max_tokens=max_tokens))
        except RuntimeError as exc:
            if "asyncio.run() cannot be called" not in str(exc):
                raise
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self._send_with_sdk_async(prompt=prompt, model=model, max_tokens=max_tokens)
                )
            finally:
                loop.close()

    async def _send_with_sdk_async(self, prompt: str, model: str, max_tokens: int) -> str:
        try:
            from copilot import CopilotClient
            from copilot.session import PermissionHandler
            from copilot.session_events import AssistantMessageData
        except Exception as exc:  # pragma: no cover - exercised when dependency is missing
            raise RuntimeError(
                "Copilot SDK is not installed. Install package 'github-copilot-sdk'."
            ) from exc

        client = CopilotClient()
        await client.start()

        session = None
        try:
            session_kwargs: dict[str, Any] = {
                "on_permission_request": PermissionHandler.approve_all,
                "model": model,
                # No github_token — SDK auto-discovers VS Code GitHub session.
            }

            # Backward compatibility: if a custom provider endpoint is configured,
            # route requests through SDK provider config instead of default Copilot routing.
            # The bearer_token is read from env at call time so it is never stored on self.
            if self._cfg.api_base_url.strip():
                bearer = _resolve_github_token(self._cfg.api_key_env) or ""
                session_kwargs["provider"] = {
                    "type": "openai",
                    "base_url": self._cfg.api_base_url,
                    "bearer_token": bearer,
                    "wire_api": "completions",
                    "max_output_tokens": max_tokens,
                }

            session = await client.create_session(**session_kwargs)
            full_prompt = f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
            reply = await session.send_and_wait(
                full_prompt,
                timeout=float(self._cfg.timeout_seconds),
            )

            if reply is None or getattr(reply, "data", None) is None:
                raise RuntimeError("Copilot SDK returned no assistant message.")

            data = reply.data
            if isinstance(data, AssistantMessageData):
                content = data.content or ""
            else:
                content = str(getattr(data, "content", "") or "")

            if not content.strip():
                raise RuntimeError("Copilot SDK returned an empty assistant message.")

            return content
        finally:
            if session is not None:
                try:
                    await session.disconnect()
                except Exception:
                    pass
            try:
                await client.stop()
            except Exception:
                force_stop = getattr(client, "force_stop", None)
                if callable(force_stop):
                    await force_stop()


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("Copilot provider response does not contain a JSON object.")
    return text[start : end + 1]


def _normalize_payload(data: dict[str, Any]) -> EnrichmentPayload:
    desc = str(data.get("description", "")).strip()
    if not desc:
        raise RuntimeError("Copilot provider response is missing non-empty 'description'.")

    responsibilities = data.get("responsibilities", [])
    if not isinstance(responsibilities, list):
        raise RuntimeError("Copilot provider response field 'responsibilities' must be an array.")

    patterns = data.get("patterns", [])
    if not isinstance(patterns, list):
        patterns = []

    notes = str(data.get("notes", "")).strip()

    return EnrichmentPayload(
        description=desc,
        responsibilities=[str(item).strip() for item in responsibilities if str(item).strip()],
        patterns=[str(item).strip() for item in patterns if str(item).strip()],
        notes=notes,
    )
