from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
)
INTERVAL_TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)
TIMEFRAME_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")


def parse_timeframe(value: str) -> Optional[timedelta]:
    normalized = value.strip().lower()
    if normalized in ("all", "none", ""):
        return None

    match = TIMEFRAME_RE.match(normalized)
    if not match:
        raise ValueError('Invalid timeframe "%s". Expected values like 24h, 3 days, 2w, or all.' % value)

    amount = int(match.group(1))
    unit = match.group(2)
    if unit in ("h", "hr", "hrs", "hour", "hours"):
        return timedelta(hours=amount)
    if unit in ("d", "day", "days"):
        return timedelta(days=amount)
    if unit in ("w", "wk", "wks", "week", "weeks"):
        return timedelta(weeks=amount)

    raise ValueError('Unsupported timeframe unit "%s".' % unit)


def parse_interval_time(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in INTERVAL_TIME_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(
        'Invalid interval time "%s". Use formats like 2025-08-03 00:00, '
        "2025-08-03T00:00:00, or 2025-08-03T00:00:00Z." % value
    )


def parse_log_timestamp(value: str) -> datetime:
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError("Unsupported log timestamp: %s" % value)


def format_seconds(value: float) -> str:
    return "%.3f sec" % value


def format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_time_filter_label(
    since_value: str,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> str:
    if from_time or to_time:
        start_label = format_timestamp(from_time) if from_time else "(beginning)"
        end_label = format_timestamp(to_time) if to_time else "(latest)"
        if since_value.strip().lower() not in ("", "all", "none"):
            return "%s -> %s, plus since %s" % (start_label, end_label, since_value)
        return "%s -> %s" % (start_label, end_label)
    return since_value


def build_time_filter_phrase(
    since_value: str,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> str:
    if from_time or to_time:
        start_label = format_timestamp(from_time) if from_time else "the beginning of the log"
        end_label = format_timestamp(to_time) if to_time else "the latest entry"
        if since_value.strip().lower() not in ("", "all", "none"):
            return "the period from %s to %s, plus the last %s" % (start_label, end_label, since_value)
        return "the period from %s to %s" % (start_label, end_label)

    normalized = since_value.strip().lower()
    if normalized in ("", "all", "none"):
        return "all time"

    match = TIMEFRAME_RE.match(normalized)
    if not match:
        return since_value

    amount = int(match.group(1))
    unit = match.group(2)
    if unit in ("h", "hr", "hrs", "hour", "hours"):
        label = "hour" if amount == 1 else "hours"
    elif unit in ("d", "day", "days"):
        label = "day" if amount == 1 else "days"
    elif unit in ("w", "wk", "wks", "week", "weeks"):
        label = "week" if amount == 1 else "weeks"
    else:
        return since_value
    return "the last %d %s" % (amount, label)


def build_scope_phrase(title: str) -> str:
    match = re.match(r"^single user \((.+)\)$", title)
    if match:
        return "user %s" % match.group(1)
    return "all users" if title == "all users" else title
