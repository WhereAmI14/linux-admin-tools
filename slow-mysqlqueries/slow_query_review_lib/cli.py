from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence, TextIO, Tuple

from .models import DEFAULT_LOG_PATH


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review MySQL slow queries and summarize them by cPanel owner.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--user", help="Review slow queries for a single cPanel user.")
    target.add_argument(
        "--all-users",
        action="store_true",
        help="Review and summarize all detected cPanel users.",
    )
    parser.add_argument(
        "--log-file",
        help="Path to the slow query log. Defaults to auto-detection or %s." % DEFAULT_LOG_PATH,
    )
    parser.add_argument(
        "--since",
        default="all",
        help='Timeframe filter such as "24h", "3 days", "2w", or "all".',
    )
    parser.add_argument(
        "--from",
        dest="from_time",
        help='Absolute interval start in UTC, for example "2025-08-03 00:00" or "2025-08-03T00:00:00Z".',
    )
    parser.add_argument(
        "--to",
        dest="to_time",
        help='Absolute interval end in UTC, for example "2025-08-04 00:00" or "2025-08-04T23:59:59Z".',
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of slow queries to show in the detailed section.",
    )
    parser.add_argument(
        "--write-user-reports",
        action="store_true",
        help=(
            "Write analytical reports for matched users. By default these are "
            "saved as /home/<cpuser>/slow-query-report-<date>.txt."
        ),
    )
    parser.add_argument(
        "--report-dir",
        help="Optional directory used instead of /home/<cpuser> when --write-user-reports is enabled.",
    )
    parser.add_argument(
        "--include-system",
        action="store_true",
        help="Include unattributed/system queries in all-user breakdowns.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors.",
    )
    return parser.parse_args(argv)


def open_prompt_stream() -> Tuple[Optional[TextIO], bool]:
    if getattr(sys.stdin, "isatty", lambda: False)():
        return sys.stdin, False
    try:
        return open("/dev/tty", "r", encoding="utf-8"), True
    except OSError:
        return None, False


def prompt_for_target(
    args: argparse.Namespace,
    input_stream: Optional[TextIO] = None,
    output_stream: Optional[TextIO] = None,
) -> argparse.Namespace:
    if args.user or args.all_users:
        return args

    stream = input_stream
    should_close = False
    if stream is None:
        stream, should_close = open_prompt_stream()
    if stream is None:
        args.all_users = True
        return args

    out = output_stream or sys.stderr

    try:
        out.write("Enter a cPanel user to review, or press Enter to scan all users: ")
        out.flush()
        user = stream.readline()
        if not user:
            args.all_users = True
            out.write("\nNo interactive input available. Defaulting to all users.\n")
            out.flush()
            return args

        user = user.strip()
        if user:
            args.user = user
        else:
            args.all_users = True
        return args
    finally:
        if should_close:
            stream.close()


def prompt_for_time_filter(
    args: argparse.Namespace,
    input_stream: Optional[TextIO] = None,
    output_stream: Optional[TextIO] = None,
) -> argparse.Namespace:
    if args.from_time or args.to_time:
        return args
    if args.since.strip().lower() not in ("", "all", "none"):
        return args

    stream = input_stream
    should_close = False
    if stream is None:
        stream, should_close = open_prompt_stream()
    if stream is None:
        args.since = "all"
        return args

    out = output_stream or sys.stderr

    try:
        out.write('Enter a time filter such as "7d", "3 days", or press Enter for all time: ')
        out.flush()
        value = stream.readline()
        if not value:
            args.since = "all"
            out.write("\nNo interactive input available. Defaulting to all time.\n")
            out.flush()
            return args

        args.since = value.strip() or "all"
        return args
    finally:
        if should_close:
            stream.close()


def should_use_color(disabled: bool) -> bool:
    if disabled or os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())
