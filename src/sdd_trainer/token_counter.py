"""Token usage tracking for GigaChat calls (AIA_07).

Counts tokens per source (lesson, quiz, socratic node) to monitor consumption
and report course metrics. Implemented in phase 1 together with the GigaChat
client (``add-console-trainer`` change).
"""
from __future__ import annotations


class TokenCounter:
    """Accumulates token usage per call source."""

    def __init__(self) -> None:
        """Initialize empty usage counters (implemented in phase 1)."""
        pass

    def add_usage(self, source: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Record a single LLM call usage (implemented in phase 1)."""
        pass

    def total_tokens(self) -> int:
        """Return total tokens consumed so far (implemented in phase 1)."""
        pass

    def report(self) -> dict[str, int]:
        """Return a per-source usage report (implemented in phase 1)."""
        pass
