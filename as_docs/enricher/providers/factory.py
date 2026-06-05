from __future__ import annotations

from as_docs.config import Config
from as_docs.enricher.providers.anthropic_client import AnthropicProvider
from as_docs.enricher.providers.base import AIProvider
from as_docs.enricher.providers.copilot_client import CopilotProvider


def create_provider(config: Config) -> AIProvider:
    if config.ai.provider == "copilot":
        return CopilotProvider(config.ai)

    if config.ai.provider == "anthropic":
        return AnthropicProvider(config.ai)

    raise RuntimeError(f"Unsupported ai.provider '{config.ai.provider}'.")
