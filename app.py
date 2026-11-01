"""SDD Trainer — single CLI entry point (rag_GigaChat convention).

Phase 0: prints skeleton status. Phase 1 (``add-console-trainer``) wires the
interactive console trainer here; phase 2 adds the FastAPI server mode.
"""
from __future__ import annotations

import argparse

import sdd_trainer


def main() -> None:
    """Parse CLI arguments and dispatch (real modes arrive in phase 1)."""
    parser = argparse.ArgumentParser(
        prog="sdd-trainer",
        description="SDD Trainer — AI tutor for Spec-Driven Development and OpenSpec",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"sdd-trainer {sdd_trainer.__version__}",
    )
    parser.parse_args()
    print(
        "SDD Trainer: skeleton is ready (phase 0). "
        "Console trainer arrives with the 'add-console-trainer' change (phase 1)."
    )


if __name__ == "__main__":
    main()
