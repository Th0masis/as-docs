from __future__ import annotations

from as_docs.config import Config
from as_docs.enricher.providers.base import AIProvider
from as_docs.enricher.providers.copilot_client import CopilotProvider


def create_provider(config: Config) -> AIProvider:
    if config.ai.provider == "copilot":
        return CopilotProvider(config.ai)

    if config.ai.provider == "anthropic":
        raise RuntimeError(
            "Anthropic runtime path is not enabled in this Phase 2 branch. "
            "Use ai.provider: copilot."
        )

    raise RuntimeError(f"Unsupported ai.provider '{config.ai.provider}'.")
