"""Entry point for account inventory CLI."""

from __future__ import annotations

import sys

from cli import main_loop
from database import init_db


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    init_db()
    main_loop()


if __name__ == "__main__":
    main()
