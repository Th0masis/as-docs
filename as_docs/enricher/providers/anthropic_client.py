from __future__ import annotations

import json
import os
import time
from typing import Any

from as_docs.config import AIConfig
from as_docs.enricher.providers.base import EnrichmentPayload
from as_docs.shared_helpers import extract_json_block

SYSTEM_INSTRUCTION = (
    "You are a documentation assistant for B&R Automation Studio projects. "
    "Return strict JSON only with keys: description, responsibilities, patterns, notes."
)


class AnthropicProvider:
    def __init__(self, ai_config: AIConfig) -> None:
        self._cfg = ai_config

        token_env = ai_config.api_key_env.strip() or "ANTHROPIC_API_KEY"
        api_key = os.getenv(token_env, "").strip()
        if not api_key:
            raise RuntimeError(
                f"No Anthropic API key found. Set environment variable '{token_env}'."
            )

        try:
            from anthropic import Anthropic
        except Exception as exc:  # pragma: no cover - import error path
            raise RuntimeError(
                "Anthropic SDK is not installed. Install package 'anthropic'."
            ) from exc

        kwargs: dict[str, Any] = {"api_key": api_key}
        if ai_config.api_base_url.strip():
            kwargs["base_url"] = ai_config.api_base_url.strip()
        self._client = Anthropic(**kwargs)

    def enrich_task(
        self, prompt: str, model: str, max_tokens: int
    ) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def enrich_pou(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        return self._request(prompt=prompt, model=model, max_tokens=max_tokens)

    def _request(self, prompt: str, model: str, max_tokens: int) -> EnrichmentPayload:
        max_attempts = self._cfg.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0,
                    system=SYSTEM_INSTRUCTION,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=float(self._cfg.timeout_seconds),
                )
                content = _extract_text_content(response)
                raw_json = extract_json_block(content, provider_name="Anthropic")
                parsed = json.loads(raw_json)
                return _normalize_payload(parsed)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Anthropic provider returned invalid JSON: {exc}"
                ) from exc
            except Exception as exc:
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"Anthropic provider request failed: {exc}"
                    ) from exc
                time.sleep(0.4 * attempt)

        raise RuntimeError("Anthropic provider request failed after retries.")


def _extract_text_content(response: Any) -> str:
    blocks = getattr(response, "content", None)
    if not blocks:
        raise RuntimeError("Anthropic provider returned an empty response.")

    text_parts: list[str] = []
    for block in blocks:
        block_type = getattr(block, "type", "")
        if block_type == "text":
            text_value = str(getattr(block, "text", "") or "")
            if text_value.strip():
                text_parts.append(text_value)

    merged = "\n".join(text_parts).strip()
    if not merged:
        raise RuntimeError("Anthropic provider response did not include text content.")

    return merged


def _normalize_payload(data: dict[str, Any]) -> EnrichmentPayload:
    desc = str(data.get("description", "")).strip()
    if not desc:
        raise RuntimeError(
            "Anthropic provider response is missing non-empty 'description'."
        )

    responsibilities = data.get("responsibilities", [])
    if not isinstance(responsibilities, list):
        raise TypeError(
            "Anthropic provider response field 'responsibilities' must be an array."
        )

    patterns = data.get("patterns", [])
    if not isinstance(patterns, list):
        patterns = []

    notes = str(data.get("notes", "")).strip()

    return EnrichmentPayload(
        description=desc,
        responsibilities=[
            str(item).strip() for item in responsibilities if str(item).strip()
        ],
        patterns=[str(item).strip() for item in patterns if str(item).strip()],
        notes=notes,
    )
