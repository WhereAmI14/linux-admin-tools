#!/usr/bin/env python3
"""Analytical MySQL slow-query review tool for cPanel servers.

Compatible with Python 3.8 through 3.12.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_LOG_PATH = "/var/lib/mysql/mysql-slow.log"
SYSTEM_OWNER = "(system/root)"
SYSTEM_NAMES = {
    "root",
    "mysql",
    "information_schema",
    "performance_schema",
    "sys",
}
SERVER_NOISE_PREFIXES = (
    "/usr/sbin/mysqld, Version:",
    "Tcp port:",
    "Time                 Id Command    Argument",
)
TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
)
TIMEFRAME_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")
USER_HOST_RE = re.compile(
    r"^# User@Host: ([^\[]+)\[([^\]]*)\] @ ([^ ]+) \[[^\]]*\]\s+Id:\s*(\d+)"
)
QUERY_STATS_RE = re.compile(
    r"^# Query_time:\s*([0-9.]+)\s+Lock_time:\s*([0-9.]+)\s+"
    r"Rows_sent:\s*(\d+)\s+Rows_examined:\s*(\d+)"
)
QUALIFIED_TABLE_RE = re.compile(r"`([A-Za-z0-9_]+)`\.`([A-Za-z0-9_]+)`")


@dataclass
class SlowQueryRecord:
    timestamp: datetime
    timestamp_raw: str
    db_user: str
    login_user: str
    host: str
    connection_id: int
    query_time: float
    lock_time: float
    rows_sent: int
    rows_examined: int
    database: Optional[str]
    sql: str
    execution_owner: str
    attributed_owner: str
    owner_source: str


class Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.reset = "\033[0m" if enabled else ""
        self.header = "\033[1;38;5;39m" if enabled else ""
        self.label = "\033[1;38;5;81m" if enabled else ""
        self.good = "\033[38;5;82m" if enabled else ""
        self.warn = "\033[1;38;5;214m" if enabled else ""
        self.bad = "\033[1;38;5;203m" if enabled else ""
        self.dim = "\033[38;5;244m" if enabled else ""
        self.accent = "\033[1;38;5;159m" if enabled else ""

    def color(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return "".join((code, text, self.reset))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review MySQL slow queries and summarize them by cPanel owner."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--user", help="Review slow queries for a single cPanel user.")
    target.add_argument(
        "--all-users",
        action="store_true",
        help="Review and summarize all detected cPanel users.",
    )
    parser.add_argument(
        "--log-file",
        help="Path to the slow query log. Defaults to auto-detection or %s."
        % DEFAULT_LOG_PATH,
    )
    parser.add_argument(
        "--since",
        default="all",
        help='Timeframe filter such as "24h", "3 days", "2w", or "all".',
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of entries to show in top slow queries and fingerprints.",
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
        help=(
            "Optional directory used instead of /home/<cpuser> when "
            "--write-user-reports is enabled."
        ),
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


def should_use_color(disabled: bool) -> bool:
    if disabled or os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def parse_timeframe(value: str) -> Optional[timedelta]:
    normalized = value.strip().lower()
    if normalized in ("all", "none", ""):
        return None

    match = TIMEFRAME_RE.match(normalized)
    if not match:
        raise ValueError(
            'Invalid timeframe "%s". Expected values like 24h, 3 days, 2w, or all.'
            % value
        )

    amount = int(match.group(1))
    unit = match.group(2)
    if unit in ("h", "hr", "hrs", "hour", "hours"):
        return timedelta(hours=amount)
    if unit in ("d", "day", "days"):
        return timedelta(days=amount)
    if unit in ("w", "wk", "wks", "week", "weeks"):
        return timedelta(weeks=amount)

    raise ValueError('Unsupported timeframe unit "%s".' % unit)


def parse_log_timestamp(value: str) -> datetime:
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError("Unsupported log timestamp: %s" % value)


def detect_log_file(explicit_path: Optional[str]) -> str:
    if explicit_path:
        return explicit_path

    config_candidates = [
        "/etc/my.cnf",
        "/etc/mysql/my.cnf",
        "/etc/my.cnf.d/server.cnf",
        "/etc/my.cnf.d/mysql-server.cnf",
    ]
    pattern = re.compile(r"^\s*(?:slow_query_log_file|log_slow_query_file)\s*=\s*(\S+)")

    for config_path in config_candidates:
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    line = raw_line.split("#", 1)[0].strip()
                    match = pattern.match(line)
                    if match:
                        return match.group(1).strip().strip('"').strip("'")
        except OSError:
            continue

    return DEFAULT_LOG_PATH


def load_cpanel_users() -> List[str]:
    users = set()

    cpanel_users_dir = "/var/cpanel/users"
    if os.path.isdir(cpanel_users_dir):
        for entry in os.listdir(cpanel_users_dir):
            if entry.startswith("."):
                continue
            users.add(entry.strip())

    whmapi_path = shutil.which("whmapi1")
    if whmapi_path:
        whmapi = subprocess.run(
            [whmapi_path, "--output=json", "listaccts"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if whmapi.returncode == 0 and whmapi.stdout:
            users.update(parse_whmapi_users(whmapi.stdout))

    return sorted(user for user in users if user)


def parse_whmapi_users(payload: str) -> Iterable[str]:
    try:
        import json

        data = json.loads(payload)
    except Exception:
        return []

    meta = data.get("data", {}) if isinstance(data, dict) else {}
    accts = meta.get("acct", []) if isinstance(meta, dict) else []
    results = []
    for account in accts:
        if isinstance(account, dict):
            user = account.get("user")
            if user:
                results.append(str(user))
    return results


def normalize_sql(sql: str) -> str:
    normalized = sql.lower()
    normalized = re.sub(r"/\*![0-9]+\s*sql_no_cache\s*\*/", "SQL_NO_CACHE", normalized)
    normalized = re.sub(r"`[^`]+`", "`?`", normalized)
    normalized = re.sub(r"'[^']*'", "?", normalized)
    normalized = re.sub(r"\b\d+\b", "?", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or "(empty statement)"


def extract_qualified_database(sql: str) -> Optional[str]:
    match = QUALIFIED_TABLE_RE.search(sql)
    if match:
        return match.group(1)
    return None


def derive_owner_from_name(name: Optional[str], cpanel_users: Sequence[str]) -> Optional[str]:
    if not name:
        return None
    if name in SYSTEM_NAMES:
        return SYSTEM_OWNER

    matches = []
    for user in cpanel_users:
        legacy = user[:8]
        if name == user or name.startswith(user + "_") or name.startswith(legacy + "_"):
            matches.append(user)

    if matches:
        return max(matches, key=len)

    if "_" in name:
        return name.split("_", 1)[0]
    return name


def attribute_owner(
    db_user: str,
    database: Optional[str],
    sql: str,
    cpanel_users: Sequence[str],
) -> Tuple[str, str, str]:
    execution_owner = derive_owner_from_name(db_user, cpanel_users) or db_user

    db_owner = derive_owner_from_name(database, cpanel_users)
    if db_owner and db_owner != SYSTEM_OWNER:
        return execution_owner, db_owner, "database"

    qualified_database = extract_qualified_database(sql)
    qualified_owner = derive_owner_from_name(qualified_database, cpanel_users)
    if qualified_owner and qualified_owner != SYSTEM_OWNER:
        return execution_owner, qualified_owner, "qualified-table"

    if execution_owner:
        return execution_owner, execution_owner, "execution-user"

    return SYSTEM_OWNER, SYSTEM_OWNER, "fallback"


def parse_slow_log(path: str, cpanel_users: Sequence[str]) -> List[SlowQueryRecord]:
    records = []
    current = None
    sql_lines = []

    try:
        handle = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError("Unable to read log file %s: %s" % (path, exc))

    with handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")

            if line.startswith("# Time: "):
                record = finalize_record(current, sql_lines, cpanel_users)
                if record is not None:
                    records.append(record)
                current = {"timestamp_raw": line[len("# Time: ") :].strip()}
                sql_lines = []
                continue

            if current is None:
                continue

            if line.startswith("# User@Host: "):
                match = USER_HOST_RE.match(line)
                if match:
                    current["db_user"] = match.group(1).strip()
                    current["login_user"] = match.group(2).strip()
                    current["host"] = match.group(3).strip()
                    current["connection_id"] = int(match.group(4))
                continue

            if line.startswith("# Query_time: "):
                match = QUERY_STATS_RE.match(line)
                if match:
                    current["query_time"] = float(match.group(1))
                    current["lock_time"] = float(match.group(2))
                    current["rows_sent"] = int(match.group(3))
                    current["rows_examined"] = int(match.group(4))
                continue

            if line.startswith("use "):
                current["database"] = line[4:].rstrip(";").strip()
                continue

            if line.startswith("SET timestamp="):
                continue

            if line.startswith(SERVER_NOISE_PREFIXES):
                continue

            sql_lines.append(line)

    record = finalize_record(current, sql_lines, cpanel_users)
    if record is not None:
        records.append(record)

    return records


def finalize_record(
    current: Optional[Dict[str, object]],
    sql_lines: List[str],
    cpanel_users: Sequence[str],
) -> Optional[SlowQueryRecord]:
    if not current:
        return None

    required = (
        "timestamp_raw",
        "db_user",
        "login_user",
        "host",
        "connection_id",
        "query_time",
        "lock_time",
        "rows_sent",
        "rows_examined",
    )
    for key in required:
        if key not in current:
            return None

    sql = "\n".join(line for line in sql_lines if line).strip()
    execution_owner, attributed_owner, owner_source = attribute_owner(
        str(current["db_user"]),
        current.get("database"),
        sql,
        cpanel_users,
    )

    return SlowQueryRecord(
        timestamp=parse_log_timestamp(str(current["timestamp_raw"])),
        timestamp_raw=str(current["timestamp_raw"]),
        db_user=str(current["db_user"]),
        login_user=str(current["login_user"]),
        host=str(current["host"]),
        connection_id=int(current["connection_id"]),
        query_time=float(current["query_time"]),
        lock_time=float(current["lock_time"]),
        rows_sent=int(current["rows_sent"]),
        rows_examined=int(current["rows_examined"]),
        database=(
            str(current["database"]) if current.get("database") not in (None, "") else None
        ),
        sql=sql or "(empty statement)",
        execution_owner=execution_owner,
        attributed_owner=attributed_owner,
        owner_source=owner_source,
    )


def filter_records(
    records: Sequence[SlowQueryRecord],
    since_delta: Optional[timedelta],
    cpanel_user: Optional[str],
    include_system: bool,
) -> List[SlowQueryRecord]:
    filtered = list(records)

    if since_delta is not None:
        cutoff = datetime.now(timezone.utc) - since_delta
        filtered = [record for record in filtered if record.timestamp >= cutoff]

    if cpanel_user:
        target = cpanel_user.strip()
        target_legacy = target[:8]
        filtered = [
            record
            for record in filtered
            if record.attributed_owner == target
            or record.execution_owner == target
            or record.db_user == target
            or record.db_user.startswith(target + "_")
            or record.db_user.startswith(target_legacy + "_")
            or (record.database and record.database.startswith(target + "_"))
            or (record.database and record.database.startswith(target_legacy + "_"))
        ]

    if not include_system and cpanel_user is None:
        filtered = [
            record for record in filtered if record.attributed_owner != SYSTEM_OWNER
        ]

    return filtered


def percentile(values: Sequence[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(math.ceil((pct / 100.0) * len(ordered))) - 1
    index = max(0, min(index, len(ordered) - 1))
    return ordered[index]


def format_seconds(value: float) -> str:
    return "%.3f sec" % value


def summarize(records: Sequence[SlowQueryRecord]) -> Dict[str, object]:
    query_times = [record.query_time for record in records]
    rows_examined = sum(record.rows_examined for record in records)
    return {
        "count": len(records),
        "total_query_time": sum(query_times),
        "average_query_time": (sum(query_times) / len(query_times)) if query_times else 0.0,
        "p95_query_time": percentile(query_times, 95),
        "max_query_time": max(query_times) if query_times else 0.0,
        "rows_examined_total": rows_examined,
        "first_seen": min((record.timestamp for record in records), default=None),
        "last_seen": max((record.timestamp for record in records), default=None),
    }


def build_fingerprint_stats(
    records: Sequence[SlowQueryRecord], top_n: int
) -> List[Tuple[str, int, float, int]]:
    stats = {}
    for record in records:
        fingerprint = normalize_sql(record.sql)
        if fingerprint not in stats:
            stats[fingerprint] = {"count": 0, "max": 0.0, "rows": 0}
        stats[fingerprint]["count"] += 1
        stats[fingerprint]["max"] = max(stats[fingerprint]["max"], record.query_time)
        stats[fingerprint]["rows"] += record.rows_examined

    sorted_stats = sorted(
        stats.items(),
        key=lambda item: (-item[1]["count"], -item[1]["max"], item[0]),
    )
    return [
        (fingerprint, data["count"], data["max"], data["rows"])
        for fingerprint, data in sorted_stats[:top_n]
    ]


def build_owner_stats(
    records: Sequence[SlowQueryRecord], top_n: int
) -> List[Tuple[str, int, float, float]]:
    buckets = defaultdict(list)
    for record in records:
        buckets[record.attributed_owner].append(record)

    rows = []
    for owner, owner_records in buckets.items():
        total = sum(record.query_time for record in owner_records)
        maximum = max(record.query_time for record in owner_records)
        rows.append((owner, len(owner_records), total, maximum))

    rows.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return rows[:top_n]


def render_summary(
    title: str,
    records: Sequence[SlowQueryRecord],
    log_file: str,
    since_value: str,
    top_n: int,
    palette: Palette,
    include_owner_breakdown: bool,
) -> str:
    summary = summarize(records)
    lines = []

    lines.append(palette.color("# slow-query-review", palette.header))
    lines.append("%s %s" % (palette.color("Log file:", palette.label), log_file))
    lines.append("%s %s" % (palette.color("Scope:", palette.label), title))
    lines.append("%s %s" % (palette.color("Time filter:", palette.label), since_value))

    if summary["first_seen"] and summary["last_seen"]:
        lines.append(
            "%s %s -> %s"
            % (
                palette.color("Period covered:", palette.label),
                format_timestamp(summary["first_seen"]),
                format_timestamp(summary["last_seen"]),
            )
        )
    lines.append("")

    lines.append(palette.color("Summary", palette.accent))
    lines.append("-" * 7)
    lines.append(
        "Total slow queries:      %s"
        % palette.color(str(summary["count"]), palette.good if summary["count"] else palette.warn)
    )
    lines.append("Total query time:        %s" % format_seconds(summary["total_query_time"]))
    lines.append("Average query time:      %s" % format_seconds(summary["average_query_time"]))
    lines.append("P95 query time:          %s" % format_seconds(summary["p95_query_time"]))
    lines.append("Slowest query:           %s" % format_seconds(summary["max_query_time"]))
    lines.append(
        "Rows examined total:     %s"
        % "{:,}".format(int(summary["rows_examined_total"]))
    )

    if include_owner_breakdown and records:
        lines.append("")
        lines.append(palette.color("Top cPanel owners", palette.accent))
        lines.append("-" * 17)
        for owner, count, total, maximum in build_owner_stats(records, top_n):
            lines.append(
                "%-20s %5d queries   %10.3f sec total   max %7.3f sec"
                % (owner, count, total, maximum)
            )

    fingerprints = build_fingerprint_stats(records, top_n)
    if fingerprints:
        lines.append("")
        lines.append(palette.color("Top query fingerprints", palette.accent))
        lines.append("-" * 22)
        for index, (fingerprint, count, maximum, rows) in enumerate(fingerprints, 1):
            lines.append(
                "%d. %4dx   max %7.3f sec   rows_examined %s"
                % (index, count, maximum, "{:,}".format(rows))
            )
            lines.append("   %s" % truncate(fingerprint, 110))

    slowest = sorted(records, key=lambda record: record.query_time, reverse=True)[:top_n]
    if slowest:
        lines.append("")
        lines.append(palette.color("Top slow queries", palette.accent))
        lines.append("-" * 16)
        for record in slowest:
            lines.append(
                "%s   owner=%s   executed_as=%s   %s"
                % (
                    format_timestamp(record.timestamp),
                    record.attributed_owner,
                    record.db_user,
                    format_seconds(record.query_time),
                )
            )
            if record.database:
                lines.append("  db=%s" % record.database)
            lines.append("  SQL: %s" % truncate(single_line(record.sql), 140))

    return "\n".join(lines)


def single_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def write_reports(
    grouped_records: Dict[str, List[SlowQueryRecord]],
    log_file: str,
    since_value: str,
    top_n: int,
) -> List[str]:
    written_paths = []
    for owner, records in grouped_records.items():
        if owner == SYSTEM_OWNER:
            continue

        output_dir = grouped_records[owner][0].__dict__.get("_report_dir")
        if not output_dir:
            output_dir = os.path.join("/home", owner)

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            written_paths.append(
                "Skipped %s report: unable to create %s (%s)" % (owner, output_dir, exc)
            )
            continue

        filename = "slow-query-report-%s.txt" % datetime.now().strftime("%d-%b-%Y")
        path = os.path.join(output_dir, filename)
        plain_palette = Palette(enabled=False)
        report = render_summary(
            "single user (%s)" % owner,
            records,
            log_file,
            since_value,
            top_n,
            plain_palette,
            include_owner_breakdown=False,
        )
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(report)
                handle.write("\n")
            written_paths.append(path)
        except OSError as exc:
            written_paths.append("Skipped %s report: unable to write %s (%s)" % (owner, path, exc))
    return written_paths


def group_by_owner(records: Sequence[SlowQueryRecord]) -> Dict[str, List[SlowQueryRecord]]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record.attributed_owner].append(record)
    return grouped


def attach_report_dir(
    grouped_records: Dict[str, List[SlowQueryRecord]], report_dir: Optional[str]
) -> None:
    if not report_dir:
        return
    for records in grouped_records.values():
        for record in records:
            record.__dict__["_report_dir"] = report_dir


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    palette = Palette(should_use_color(args.no_color))

    try:
        since_delta = parse_timeframe(args.since)
    except ValueError as exc:
        print(palette.color("Error: %s" % exc, palette.bad), file=sys.stderr)
        return 2

    log_file = detect_log_file(args.log_file)
    cpanel_users = load_cpanel_users()

    try:
        records = parse_slow_log(log_file, cpanel_users)
    except RuntimeError as exc:
        print(palette.color(str(exc), palette.bad), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(palette.color("Error while parsing the log: %s" % exc, palette.bad), file=sys.stderr)
        return 1

    filtered_records = filter_records(
        records,
        since_delta=since_delta,
        cpanel_user=args.user,
        include_system=args.include_system,
    )

    if not filtered_records:
        scope = "user %s" % args.user if args.user else "all users"
        print(
            palette.color(
                "No slow query records matched %s with timeframe %s."
                % (scope, args.since),
                palette.warn,
            )
        )
        return 0

    if args.user:
        title = "single user (%s)" % args.user
        output = render_summary(
            title=title,
            records=filtered_records,
            log_file=log_file,
            since_value=args.since,
            top_n=args.top,
            palette=palette,
            include_owner_breakdown=False,
        )
        print(output)
        if args.write_user_reports:
            grouped = {args.user: list(filtered_records)}
            attach_report_dir(grouped, args.report_dir)
            for item in write_reports(grouped, log_file, args.since, args.top):
                print(palette.color("Report: %s" % item, palette.good))
        return 0

    title = "all users"
    output = render_summary(
        title=title,
        records=filtered_records,
        log_file=log_file,
        since_value=args.since,
        top_n=args.top,
        palette=palette,
        include_owner_breakdown=True,
    )
    print(output)

    if args.write_user_reports:
        grouped = group_by_owner(filtered_records)
        attach_report_dir(grouped, args.report_dir)
        written = write_reports(grouped, log_file, args.since, args.top)
        if written:
            print("")
            print(palette.color("Report files", palette.accent))
            print("-" * 12)
            for item in written:
                code = palette.good if not item.startswith("Skipped ") else palette.warn
                print(palette.color(item, code))

    return 0


if __name__ == "__main__":
    sys.exit(main())
