from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import json
import logging
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from as_docs.config import AIConfig
from as_docs.enricher.providers.base import EnrichmentPayload


SYSTEM_INSTRUCTION = (
    "You are a documentation assistant for B&R Automation Studio projects. "
    "Return strict JSON only with keys: description, responsibilities, patterns, notes."
)

_GH_API = "https://api.github.com"
_COPILOT_TOKEN_URL = f"{_GH_API}/copilot_internal/v2/token"
_COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"
_DEVICE_CODE_URL = "https://github.com/login/device/code"
_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
_DEVICE_FLOW_SCOPE = "read:user"
_SLOW_DOWN_INCREMENT = 5
_TOKEN_CACHE_PATH = Path.home() / ".config" / "as-docs" / "github_token"
_LOG = logging.getLogger(__name__)


def _resolve_vscode_token_windows() -> str | None:
    """Read VS Code's stored GitHub OAuth token from Windows Credential Manager.

    VS Code's GitHub authentication extension persists the session as a JSON blob
    under the generic credential target ``vscode.github-authentication``.
    The blob is UTF-16-LE encoded and contains a JSON array of session objects,
    each with an ``accessToken`` field.
    """
    if platform.system() != "Windows":
        return None

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.wintypes.DWORD),
                    ("dwHighDateTime", ctypes.wintypes.DWORD)]

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.wintypes.DWORD),
            ("Type", ctypes.wintypes.DWORD),
            ("TargetName", ctypes.wintypes.LPWSTR),
            ("Comment", ctypes.wintypes.LPWSTR),
            ("LastWritten", _FILETIME),
            ("CredentialBlobSize", ctypes.wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", ctypes.wintypes.DWORD),
            ("AttributeCount", ctypes.wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.wintypes.LPWSTR),
            ("UserName", ctypes.wintypes.LPWSTR),
        ]

    CRED_TYPE_GENERIC = 1
    try:
        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        advapi32.CredReadW.restype = ctypes.wintypes.BOOL
        advapi32.CredReadW.argtypes = [
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)),
        ]
        advapi32.CredFree.argtypes = [ctypes.c_void_p]

        pcred = ctypes.POINTER(_CREDENTIAL)()
        if not advapi32.CredReadW(
            "vscode.github-authentication", CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)
        ):
            return None

        try:
            cred = pcred.contents
            raw = bytes(cred.CredentialBlob[i] for i in range(cred.CredentialBlobSize))
            blob = raw.decode("utf-16-le", errors="replace")
            sessions = json.loads(blob)
            if isinstance(sessions, list):
                for sess in sessions:
                    tok = sess.get("accessToken", "").strip()
                    if tok:
                        _LOG.info("Using VS Code GitHub session token from Windows Credential Manager.")
                        return tok
        finally:
            advapi32.CredFree(pcred)
    except Exception as exc:
        _LOG.debug("Windows Credential Manager read failed: %s", exc)
    return None


def _resolve_git_credential_token() -> str | None:
    """Read GitHub token from git credential helper (e.g., Git Credential Manager)."""
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        username = ""
        password = ""
        for line in result.stdout.splitlines():
            if line.startswith("username="):
                username = line.split("=", 1)[1].strip()
            elif line.startswith("password="):
                password = line.split("=", 1)[1].strip()

        # GitHub credential helpers usually return PAT/OAuth token in the password field.
        if password and username:
            return password
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _save_device_flow_token(token: str) -> None:
    """Persist a device-flow-obtained GitHub token to the local cache file."""
    try:
        _TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE_PATH.write_text(token, encoding="utf-8")
        if platform.system() != "Windows":
            import stat as _stat
            _TOKEN_CACHE_PATH.chmod(_stat.S_IRUSR | _stat.S_IWUSR)
    except OSError as exc:
        _LOG.debug("Could not save device flow token to cache: %s", exc)


def _load_device_flow_token() -> str | None:
    """Load a previously-saved device-flow token from the local cache file."""
    try:
        if _TOKEN_CACHE_PATH.exists():
            tok = _TOKEN_CACHE_PATH.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    except OSError:
        pass
    return None


def _resolve_github_token_via_device_flow(client_id: str) -> str | None:
    """Authenticate interactively via GitHub OAuth Device Flow.

    Displays a one-time code for the user to enter at https://github.com/login/device,
    then polls until the user approves.  Saves the resulting token to the local
    cache file so future runs skip the interactive prompt.

    Requires *client_id* from a registered GitHub OAuth App.
    Set ``oauth_client_id`` in ``.as-docs.yaml`` or the ``AS_DOCS_OAUTH_CLIENT_ID``
    environment variable.
    """
    if not client_id:
        return None

    # Step 1: request a device + user code.
    try:
        body = json.dumps({"client_id": client_id, "scope": _DEVICE_FLOW_SCOPE}).encode()
        req = urllib.request.Request(
            _DEVICE_CODE_URL,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
    except Exception as exc:
        _LOG.debug("Device flow code request failed: %s", exc)
        return None

    device_code = data.get("device_code", "")
    user_code = data.get("user_code", "")
    verification_uri = data.get("verification_uri", "https://github.com/login/device")
    expires_in: int = data.get("expires_in", 900)
    interval: int = data.get("interval", 5)

    if not device_code or not user_code:
        _LOG.debug("Device flow response missing device_code or user_code.")
        return None

    # Step 2: prompt the user.
    print(f"\n  GitHub OAuth — Device Flow")
    print(f"  1. Open:       {verification_uri}")
    print(f"  2. Enter code: {user_code}")
    print(f"  Waiting for authorization (expires in {expires_in}s) ...\n")

    # Step 3: poll until approved or expired.
    deadline = time.monotonic() + expires_in
    current_interval = interval
    while time.monotonic() < deadline:
        time.sleep(current_interval)
        try:
            poll_body = json.dumps({
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            }).encode()
            req = urllib.request.Request(
                _OAUTH_TOKEN_URL,
                data=poll_body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                result = json.loads(resp.read())
        except Exception as exc:
            _LOG.debug("Device flow poll failed: %s", exc)
            continue

        if "access_token" in result:
            token: str = result["access_token"].strip()
            _LOG.info("GitHub OAuth Device Flow completed successfully.")
            _save_device_flow_token(token)
            return token

        error = result.get("error", "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            current_interval += _SLOW_DOWN_INCREMENT
            continue
        # Fatal: expired_token, access_denied, incorrect_client_credentials, …
        _LOG.debug("Device flow error: %s — %s", error, result.get("error_description", ""))
        return None

    _LOG.debug("Device flow timed out (expires_in=%s s).", expires_in)
    return None


def _resolve_github_token_with_source(
    api_key_env: str = "GITHUB_TOKEN",
    oauth_client_id: str = "",
) -> tuple[str | None, str]:
    """Return a GitHub token and a human-readable source label.

    Priority:
    1. If *api_key_env* itself looks like a GitHub token (starts with ``ghp_`` or
       ``github_pat_``), use it directly — the user placed the token in the config
       field rather than an env-var name.
    2. Environment variable named by *api_key_env* (config-defined, e.g. ``GITHUB_TOKEN``).
    3. ``GH_TOKEN`` standard GitHub CLI env var.
    4. ``gh auth token`` from the GitHub CLI (used by VS Code's GitHub extension).
    5. Git credential helper entry for https://github.com (e.g., GCM).
    6. VS Code's stored GitHub session token from Windows Credential Manager.
    7. Cached GitHub token from a previous Device Flow login (~/.config/as-docs/github_token).
    8. Interactive GitHub OAuth Device Flow (requires *oauth_client_id* or
       ``AS_DOCS_OAUTH_CLIENT_ID`` env var to be set).
    """
    # Support accidental direct-token usage in the api_key_env config field.
    if api_key_env.startswith(("ghp_", "github_pat_", "ghu_")):
        return api_key_env, "config-direct-token"

    for var in (api_key_env, "GH_TOKEN", "GITHUB_TOKEN"):
        tok = os.getenv(var, "").strip()
        if tok:
            return tok, f"env:{var}"

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
                return tok, "gh-cli"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    tok = _resolve_git_credential_token()
    if tok:
        return tok, "git-credential-helper"

    tok = _resolve_vscode_token_windows()
    if tok:
        return tok, "vscode-windows-credential-manager"

    # Cached device-flow token from a previous interactive login.
    tok = _load_device_flow_token()
    if tok:
        return tok, "device-flow-cache"

    # Interactive Device Flow — only when a client_id is available.
    client_id = oauth_client_id or os.getenv("AS_DOCS_OAUTH_CLIENT_ID", "").strip()
    tok = _resolve_github_token_via_device_flow(client_id)
    if tok:
        return tok, "device-flow-interactive"

    return None, "none"


def _resolve_github_token(
    api_key_env: str = "GITHUB_TOKEN",
    oauth_client_id: str = "",
) -> str | None:
    """Return only the resolved GitHub token (without source metadata)."""
    tok, _ = _resolve_github_token_with_source(api_key_env, oauth_client_id)
    return tok


def _has_resolvable_github_token(api_key_env: str = "GITHUB_TOKEN") -> bool:
    """Whether any token source can currently be resolved."""
    tok, _ = _resolve_github_token_with_source(api_key_env)
    return bool(tok)


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
                f"Copilot entitlement preflight was denied for GitHub account '{login}' "
                f"(HTTP {exc.code}). Runtime access may still succeed via SDK or org policy."
            ) from exc
        # Unexpected HTTP error – treat as a transient network issue, not a hard block.
        # Log and continue; the SDK itself will surface a cleaner error if Copilot is unavailable.
    except Exception:
        pass  # Network failure during entitlement probe — let the SDK handle it.

    return login


def _get_copilot_api_token(github_token: str) -> str:
    """Exchange a GitHub PAT for a short-lived Copilot API token."""
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "as-docs",
    }
    try:
        req = urllib.request.Request(_COPILOT_TOKEN_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
        token = data.get("token", "")
        if not token:
            raise RuntimeError("Copilot token exchange returned no token.")
        return token
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Failed to obtain Copilot API token (HTTP {exc.code}). "
            "Ensure your GitHub token has Copilot access."
        ) from exc


def _send_via_copilot_http(
    github_token: str,
    prompt: str,
    model: str,
    max_tokens: int,
    timeout: int,
) -> str:
    """Call the Copilot Chat completions API directly using HTTP (no SDK required)."""
    copilot_token = _get_copilot_api_token(github_token)

    headers = {
        "Authorization": f"Bearer {copilot_token}",
        "Content-Type": "application/json",
        "User-Agent": "as-docs",
        "Copilot-Integration-Id": "vscode-chat",
        "Editor-Version": "vscode/1.90.0",
        "Editor-Plugin-Version": "copilot-chat/0.15.0",
    }
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
    }).encode()

    try:
        req = urllib.request.Request(_COPILOT_CHAT_URL, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("Copilot API returned empty content.")
        return content
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"Copilot API request failed (HTTP {exc.code}): {body_text}") from exc


class CopilotProvider:
    def __init__(self, ai_config: AIConfig) -> None:
        self._cfg = ai_config
        token, token_source = _resolve_github_token_with_source(
            ai_config.api_key_env, ai_config.oauth_client_id
        )
        self._github_login = "<unknown>"

        _LOG.info("Resolved GitHub credential source: %s", token_source)

        # SDK auth can use the current VS Code session without explicit tokens.
        # Token-based GitHub preflight is best-effort only and must not block.
        if token:
            try:
                self._github_login = _verify_copilot_entitlement(token)
            except Exception as exc:
                _LOG.info("Copilot preflight check inconclusive; continuing with SDK auth.")
                _LOG.debug("Copilot preflight details: %s", exc)
        else:
            _LOG.info(
                "No explicit GitHub token found for preflight. "
                "Proceeding with Copilot SDK session-based auth."
            )

        # Do NOT store the raw token — the Copilot SDK auto-discovers
        # VS Code credentials at runtime.

    def enrich_task(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def enrich_pou(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def _request(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        max_attempts = self._cfg.max_retries + 1
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                content = self._send_with_sdk(prompt=prompt, model=model, max_tokens=max_tokens)
                raw_json = _extract_json_block(content)
                parsed = json.loads(raw_json)
                return _normalize_payload(parsed)
            except (RuntimeError, TimeoutError, Exception) as exc:
                if _is_sdk_not_installed_error(exc):
                    # The github-copilot-sdk package is absent; fall back to HTTP if possible.
                    if _has_resolvable_github_token(self._cfg.api_key_env):
                        _LOG.info("Copilot SDK not installed; attempting direct HTTP API fallback.")
                        return self._request_via_http(prompt=prompt, model=model, max_tokens=max_tokens)
                    raise RuntimeError(
                        "The 'github-copilot-sdk' package is not installed and no GitHub token "
                        "is available for the HTTP fallback. "
                        f"Set the {self._cfg.api_key_env} environment variable (or GH_TOKEN / "
                        "GH_COPILOT_TOKEN) to a valid token and retry."
                    ) from exc
                if _is_sdk_auth_error(exc):
                    # SDK auth failure: only try HTTP fallback when a token is actually available.
                    # Otherwise preserve the original SDK error to avoid masking the root cause.
                    if _has_resolvable_github_token(self._cfg.api_key_env):
                        _LOG.info("SDK auth failed; attempting direct Copilot HTTP API fallback.")
                        return self._request_via_http(prompt=prompt, model=model, max_tokens=max_tokens)
                    if attempt >= max_attempts:
                        raise RuntimeError(
                            f"Copilot SDK authentication failed. "
                            f"{_sdk_auth_error_message(self._cfg.api_key_env)}"
                        ) from exc
                    last_exc = exc
                    time.sleep(0.4 * attempt)
                    continue
                if _is_sdk_model_error(exc):
                    # Model is not available in SDK — try fallback models without retrying.
                    return self._request_with_fallback_models(
                        prompt=prompt, model=model, max_tokens=max_tokens
                    )
                if attempt >= max_attempts:
                    raise RuntimeError(f"Copilot provider request failed: {exc}") from exc
                last_exc = exc
                time.sleep(0.4 * attempt)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Copilot provider returned invalid JSON: {exc}") from exc

        raise RuntimeError(f"Copilot provider request failed after retries: {last_exc}")

    def _request_with_fallback_models(
        self, prompt: str, model: str, max_tokens: int
    ) -> EnrichmentPayload:
        """Try a list of fallback models when the requested model is unavailable in the SDK."""
        fallback_models = [m for m in _SDK_FALLBACK_MODELS if m != model]
        _LOG.warning(
            "Model '%s' is not available in the Copilot SDK. Trying fallbacks: %s",
            model,
            fallback_models,
        )
        for fb_model in fallback_models:
            try:
                _LOG.info("Trying fallback model '%s' via SDK.", fb_model)
                content = self._send_with_sdk(prompt=prompt, model=fb_model, max_tokens=max_tokens)
                raw_json = _extract_json_block(content)
                parsed = json.loads(raw_json)
                _LOG.info("Fallback model '%s' succeeded.", fb_model)
                return _normalize_payload(parsed)
            except Exception as exc:
                if _is_sdk_model_error(exc):
                    _LOG.warning("Fallback model '%s' also unavailable; trying next.", fb_model)
                    continue
                if _is_sdk_auth_error(exc):
                    if _has_resolvable_github_token(self._cfg.api_key_env):
                        break
                    _LOG.warning(
                        "Fallback model '%s' hit SDK auth error but no token is available; "
                        "continuing with SDK model fallbacks.",
                        fb_model,
                    )
                    continue
                _LOG.warning("Fallback model '%s' failed: %s", fb_model, exc)
                continue

        # All SDK fallbacks exhausted — try the HTTP fallback with the original model.
        _LOG.info("All SDK model fallbacks exhausted; attempting direct Copilot HTTP fallback.")
        return self._request_via_http(prompt=prompt, model=model, max_tokens=max_tokens)

    def _request_via_http(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        """Direct HTTP fallback — works from any terminal without VS Code session auth."""
        token = _resolve_github_token(self._cfg.api_key_env)
        if not token:
            raise RuntimeError(
                _sdk_auth_error_message(self._cfg.api_key_env)
                + "\n\nDirect HTTP fallback also failed: no GitHub token available."
            )
        try:
            content = _send_via_copilot_http(
                github_token=token,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                timeout=self._cfg.timeout_seconds,
            )
        except RuntimeError as exc:
            if _is_copilot_scope_error(exc):
                # The resolved token exists but lacks the Copilot scope (HTTP 404).
                # Try OAuth Device Flow if a client_id is available.
                client_id = self._cfg.oauth_client_id or os.getenv("AS_DOCS_OAUTH_CLIENT_ID", "").strip()
                if client_id:
                    _LOG.info(
                        "Token lacks Copilot scope; starting OAuth Device Flow for a scoped token."
                    )
                    device_token = _resolve_github_token_via_device_flow(client_id)
                    if device_token:
                        content = _send_via_copilot_http(
                            github_token=device_token,
                            prompt=prompt,
                            model=model,
                            max_tokens=max_tokens,
                            timeout=self._cfg.timeout_seconds,
                        )
                    else:
                        raise RuntimeError(
                            "OAuth Device Flow did not complete. Authorize the app and retry."
                        ) from exc
                else:
                    raise RuntimeError(
                        f"{exc}\n\n"
                        "The resolved token does not have Copilot API access. Options:\n"
                        "  1. Set GH_TOKEN to a GitHub PAT with Copilot access.\n"
                        "  2. Run 'gh auth login' so 'gh auth token' returns a scoped token.\n"
                        "  3. Add 'oauth_client_id: <your-app-id>' to .as-docs.yaml to enable "
                        "interactive OAuth Device Flow."
                    ) from exc
            else:
                raise
        raw_json = _extract_json_block(content)
        parsed = json.loads(raw_json)
        return _normalize_payload(parsed)

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

        sdk_token = _resolve_github_token(self._cfg.api_key_env)
        client_kwargs: dict[str, Any] = {}
        if sdk_token:
            client_kwargs["github_token"] = sdk_token

        client = CopilotClient(**client_kwargs)
        await client.start()

        session = None
        try:
            session_kwargs: dict[str, Any] = {
                "on_permission_request": PermissionHandler.approve_all,
                "model": model,
            }

            if sdk_token:
                session_kwargs["github_token"] = sdk_token

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


def _is_sdk_not_installed_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "copilot sdk is not installed" in msg


def _is_copilot_scope_error(exc: Exception) -> bool:
    """True when the resolved token was found but doesn't have Copilot API access (HTTP 404)."""
    msg = str(exc).lower()
    return "http 404" in msg and "copilot" in msg


def _is_sdk_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "session was not created with authentication info" in msg


def _is_sdk_model_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "is not available" in msg and "model" in msg


# Ordered list of models to try when the configured model is unavailable in the SDK.
_SDK_FALLBACK_MODELS = [
    "gpt-4.1",
    "gpt-4o",
    "gpt-4",
    "claude-3.5-sonnet",
    "claude-3-sonnet",
    "gpt-3.5-turbo",
]


def _sdk_auth_error_message(api_key_env: str) -> str:
    return (
        "Copilot SDK authentication failed. "
        "The runtime could not use VS Code session auth and no valid token was supplied. "
        f"Set the {api_key_env} environment variable (or GH_TOKEN), "
        "or run 'gh auth login' and retry."
    )


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
