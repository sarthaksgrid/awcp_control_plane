"""
AWCP - LLM Gateway
==================
Unified interface to multiple LLM providers.

Week 2 DS-1 uses this as a provider-neutral summarization boundary.
The first implementation is intentionally deterministic so recursive
compression can run locally without provider credentials.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional


class LLMGateway:
    """
    Minimal gateway for DS-1 Week 2 context folding.

    The public shape is deliberately small: callers can ask for a summary
    without knowing whether the implementation is local, OpenAI, Claude, or
    another provider later.
    """

    def __init__(self, provider: Optional[Any] = None, mode: str = "local"):
        self.provider = provider
        self.mode = mode

    def summarize(
        self,
        content: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        target_tokens: int = 300,
    ) -> Dict[str, Any]:
        """
        Return a compact deterministic summary.

        Live provider routing can replace this internals later, but the return
        contract should stay stable for the RLM summarizer.
        """
        text = _to_text(content)
        important_lines = _select_important_lines(text.splitlines())

        if not important_lines:
            important_lines = [line.strip() for line in text.splitlines() if line.strip()][:5]

        summary = " ".join(important_lines[:5]).strip()
        if not summary:
            summary = "No trace content provided."

        return {
            "summary": _trim_to_token_budget(summary, target_tokens),
            "metadata": metadata or {},
            "token_count": estimate_tokens(summary),
            "provider": self.mode,
        }


def summarize(
    content: Any,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    target_tokens: int = 300,
) -> Dict[str, Any]:
    """Convenience function for callers that do not need a gateway instance."""
    return LLMGateway().summarize(content, metadata=metadata, target_tokens=target_tokens)


def estimate_tokens(value: Any) -> int:
    """Small local token estimate. Good enough for scratch validation."""
    text = _to_text(value)
    return max(1, len(text) // 4)


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except TypeError:
        return str(value)


def _select_important_lines(lines: Iterable[str]) -> List[str]:
    keywords = (
        "error",
        "fail",
        "exception",
        "timeout",
        "retry",
        "deny",
        "denied",
        "policy",
        "approval",
        "write",
        "update",
        "delete",
        "degraded",
        "risk",
        "rollback",
        "resume",
    )
    selected: List[str] = []
    for line in lines:
        clean = line.strip()
        if clean and any(keyword in clean.lower() for keyword in keywords):
            selected.append(clean)
    return selected


def _trim_to_token_budget(text: str, target_tokens: int) -> str:
    max_chars = max(40, target_tokens * 4)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."
