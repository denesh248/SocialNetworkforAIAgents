"""Interactive CLI for HardAsk."""

from __future__ import annotations

import argparse
import platform
import sys

from hardware_qa import __version__
from hardware_qa.discover import discover_capabilities
from hardware_qa.orchestrator import handle_turn
from hardware_qa.session import SessionState


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hardask",
        description="Local hardware Q&A assistant (allow-listed tools only).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use fixture data instead of live system commands.",
    )
    args = parser.parse_args()

    caps = discover_capabilities(demo_mode=args.demo)
    session = SessionState()

    mode = "DEMO (fixture data)" if caps.demo_mode else f"LIVE {platform.system()} inspection"
    print(f"HardAsk v{__version__} — {mode}")
    print(f"Tools available: {len(caps.available_tools)} | missing: {len(caps.missing_tools)}")
    if caps.missing_tools:
        print(f"  missing: {', '.join(caps.missing_tools)}")
    print("Type a hardware question, or 'exit' to quit.\n")

    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            break
        try:
            reply = handle_turn(question, caps, session)
        except Exception as exc:
            reply = f"Sorry, something went wrong: {exc}"
        print(f"assistant> {reply}\n")

    sys.exit(0)
