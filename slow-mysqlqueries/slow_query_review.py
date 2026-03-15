#!/usr/bin/env python3
"""Compatibility entrypoint for the slow query review tool."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from slow_query_review_lib import *  # noqa: E402,F401,F403
from slow_query_review_lib import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
