"""Model provider abstraction — DeepSeek and Ollama via a single factory.

Both DeepSeek and Ollama expose OpenAI-compatible /v1/chat/completions
endpoints, so we use ``ChatOpenAI`` for both and just vary the base_url.
"""

from __future__ import annotations

import os
import logging
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_llm() -> Any:
    """Return a LangChain chat model based on LLM_PROVIDER env var.

    Returns:
        A ``BaseChatModel`` instance (ChatOpenAI or ChatOllama).

    Raises:
        RuntimeError: If LLM_PROVIDER is not set or unsupported.
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    if not provider:
        raise RuntimeError(
            "LLM_PROVIDER not set. Set it in .env to 'deepseek' or 'ollama'."
        )

    if provider == "deepseek":
        return _deepseek()
    if provider == "ollama":
        return _ollama()

    raise RuntimeError(
        f"Unknown LLM_PROVIDER '{provider}'. Supported: deepseek, ollama."
    )


def _deepseek() -> Any:
    """Configure ChatDeepSeek for DeepSeek's API.

    Uses the official langchain-deepseek integration which handles
    tool calling format correctly (unlike ChatOpenAI pointed at
    DeepSeek's API, which can produce misformatted tool messages).
    """
    from langchain_deepseek import ChatDeepSeek

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. Add it to .env."
        )

    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    logger.info("Using DeepSeek model=%s base_url=%s", model, base_url)

    return ChatDeepSeek(
        model=model,
        api_key=api_key,
        api_base=base_url,
        temperature=temperature,
        timeout=60,
        max_retries=2,
    )


def _ollama() -> Any:
    """Configure ChatOllama for a local Ollama instance."""
    from langchain_ollama import ChatOllama

    model = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    logger.info("Using Ollama model=%s base_url=%s", model, base_url)

    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
    )
