from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from as_docs.config import AIConfig
from as_docs.enricher.providers.base import EnrichmentPayload


class CopilotProvider:
    def __init__(self, ai_config: AIConfig) -> None:
        self._cfg = ai_config
        token = os.getenv(ai_config.api_key_env)
        if not token:
            raise RuntimeError(
                f"Copilot provider requires environment variable '{ai_config.api_key_env}'."
            )
        self._token = token

    def enrich_task(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def enrich_pou(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def _request(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a documentation assistant for B&R Automation Studio projects. "
                        "Return strict JSON only with keys: description, responsibilities, patterns, notes."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }

        max_attempts = self._cfg.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                body = self._post_json(payload)
                content = _extract_content_text(body)
                raw_json = _extract_json_block(content)
                parsed = json.loads(raw_json)
                return _normalize_payload(parsed)
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt >= max_attempts:
                    raise RuntimeError(f"Copilot provider request failed: {exc}") from exc
                time.sleep(0.4 * attempt)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Copilot provider returned invalid JSON: {exc}") from exc

        raise RuntimeError("Copilot provider request failed after retries.")

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload).encode("utf-8")
        req = Request(
            self._cfg.api_base_url,
            data=encoded,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return json.loads(text)


def _extract_content_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Copilot provider response has no choices.")
    msg = choices[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):
        chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "".join(chunks)
    if isinstance(content, str):
        return content
    raise RuntimeError("Copilot provider response content is in an unsupported format.")


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
