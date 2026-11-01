"""Logging helpers for SDD Trainer (rag_GigaChat convention).

Central logging setup: console handler, optional file handler, and
request-scoped context for tracing lesson flows. Implemented in phase 1
(``add-console-trainer`` change).
"""
from __future__ import annotations


def setup_logging(level: str = "INFO") -> None:
    """Configure application-wide logging (implemented in phase 1)."""
    pass


def get_logger(name: str):
    """Return a configured logger (implemented in phase 1)."""
    pass
