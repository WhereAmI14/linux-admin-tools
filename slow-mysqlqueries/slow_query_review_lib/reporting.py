from __future__ import annotations

import os
import pwd
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .models import SYSTEM_OWNER, SlowQueryRecord
from .time_utils import build_scope_phrase, format_seconds, format_timestamp


class Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.reset = "\033[0m" if enabled else ""
        self.bold = "\033[1m" if enabled else ""
        self.header = "\033[1;38;5;39m" if enabled else ""
        self.label = "\033[1;38;5;81m" if enabled else ""
        self.good = "\033[38;5;82m" if enabled else ""
        self.warn = "\033[1;38;5;214m" if enabled else ""
        self.bad = "\033[1;38;5;203m" if enabled else ""
        self.dim = "\033[38;5;244m" if enabled else ""
        self.accent = "\033[1;38;5;82m" if enabled else ""

    def color(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return "".join((code, text, self.reset))


def summarize(records: Sequence[SlowQueryRecord]) -> Dict[str, object]:
    query_times = [record.query_time for record in records]
    return {
        "count": len(records),
        "average_query_time": (sum(query_times) / len(query_times)) if query_times else 0.0,
        "max_query_time": max(query_times) if query_times else 0.0,
        "first_seen": min((record.timestamp for record in records), default=None),
        "last_seen": max((record.timestamp for record in records), default=None),
    }


def build_owner_stats(records: Sequence[SlowQueryRecord], top_n: int) -> List[Tuple[str, int, float, float]]:
    buckets: Dict[str, List[SlowQueryRecord]] = defaultdict(list)
    for record in records:
        buckets[record.attributed_owner].append(record)

    rows = []
    for owner, owner_records in buckets.items():
        total = sum(record.query_time for record in owner_records)
        maximum = max(record.query_time for record in owner_records)
        rows.append((owner, len(owner_records), total, maximum))

    rows.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return rows[:top_n]


def build_database_stats(records: Sequence[SlowQueryRecord], top_n: int) -> List[Tuple[str, int, float]]:
    buckets: Dict[str, List[SlowQueryRecord]] = defaultdict(list)
    for record in records:
        if record.database:
            buckets[record.database].append(record)

    rows = []
    for database, database_records in buckets.items():
        maximum = max(record.query_time for record in database_records)
        rows.append((database, len(database_records), maximum))

    rows.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return rows[:top_n]


def render_summary(
    title: str,
    records: Sequence[SlowQueryRecord],
    log_file: str,
    time_filter_label: str,
    time_filter_phrase: str,
    top_n: int,
    palette: Palette,
    include_owner_breakdown: bool,
) -> str:
    summary = summarize(records)
    lines = [
        palette.color("# slow-query-review", palette.header),
        "%s %s" % (palette.color("Log file:", palette.label), log_file),
        "%s %s" % (palette.color("Scope:", palette.label), title),
        "%s %s" % (palette.color("Time filter:", palette.label), time_filter_label),
    ]

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
    lines.append("Average query time:      %s" % format_seconds(summary["average_query_time"]))
    lines.append("Slowest query:           %s" % format_seconds(summary["max_query_time"]))

    if include_owner_breakdown and records:
        lines.append("")
        lines.append(palette.color("cPanel accounts with slow queries", palette.accent))
        lines.append("-" * 33)
        lines.append(
            palette.color(
                "%-20s %8s   %14s   %12s" % ("ACCOUNT", "QUERIES", "TOTAL TIME", "SLOWEST"),
                palette.bold,
            )
        )
        for owner, count, total, maximum in build_owner_stats(records, top_n):
            lines.append("%-20s %8d   %14s   %12s" % (owner, count, format_seconds(total), format_seconds(maximum)))

    database_rows = build_database_stats(records, top_n)
    if database_rows:
        lines.append("")
        lines.append(palette.color("Databases with the most slow queries", palette.accent))
        lines.append("-" * 36)
        lines.append(
            palette.color(
                "%-30s %8s   %12s" % ("DATABASE", "QUERIES", "SLOWEST"),
                palette.bold,
            )
        )
        for database, count, maximum in database_rows:
            lines.append("%-30s %8d   %12s" % (truncate(database, 30), count, format_seconds(maximum)))

    slowest = sorted(records, key=lambda record: record.query_time, reverse=True)[:top_n]
    if slowest:
        lines.append("")
        section_title = "The %s slowest queries for %s during %s" % (
            len(slowest),
            build_scope_phrase(title),
            time_filter_phrase,
        )
        lines.append(palette.color(section_title, palette.accent))
        lines.append("-" * len(section_title))
        for record in slowest:
            owner_text = "%s%s" % (
                palette.color("owner=", palette.label),
                palette.color(record.attributed_owner, palette.accent),
            )
            executed_text = "%s%s" % (
                palette.color("executed_as=", palette.label),
                palette.color(record.db_user, palette.dim),
            )
            query_time_text = palette.color(format_seconds(record.query_time), palette.bad)
            lines.append(
                "%s   %s   %s   %s"
                % (format_timestamp(record.timestamp), owner_text, executed_text, query_time_text)
            )
            if record.database:
                lines.append(
                    "  %s%s"
                    % (
                        palette.color("db=", palette.label),
                        palette.color(record.database, palette.warn),
                    )
                )
            lines.append("  SQL: %s" % truncate(single_line(record.sql), 140))

    return "\n".join(lines)


def single_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def write_reports(
    grouped_records: Dict[str, List[SlowQueryRecord]],
    log_file: str,
    time_filter_label: str,
    time_filter_phrase: str,
    top_n: int,
) -> List[str]:
    written_paths = []
    for owner, records in grouped_records.items():
        if owner == SYSTEM_OWNER:
            continue

        output_dir = records[0].__dict__.get("_report_dir") or os.path.join("/home", owner)
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            written_paths.append("Skipped %s report: unable to create %s (%s)" % (owner, output_dir, exc))
            continue

        filename = "slow-query-report-%s.txt" % datetime.now().strftime("%d-%b-%Y")
        path = os.path.join(output_dir, filename)
        plain_palette = Palette(enabled=False)
        report = render_summary(
            "single user (%s)" % owner,
            records,
            log_file,
            time_filter_label,
            time_filter_phrase,
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


def render_raw_report(records: Sequence[SlowQueryRecord]) -> str:
    entries = [record.raw_entry.strip() for record in records if record.raw_entry.strip()]
    return "\n\n".join(entries) + ("\n" if entries else "")


def maybe_chown_to_user(path: str, owner: str) -> None:
    try:
        user_info = pwd.getpwnam(owner)
    except KeyError:
        return

    try:
        os.chown(path, user_info.pw_uid, user_info.pw_gid)
    except OSError:
        return


def write_raw_slow_query_report(
    owner: str,
    records: Sequence[SlowQueryRecord],
    report_dir: Optional[str] = None,
) -> str:
    output_dir = report_dir or os.path.join("/home", owner)
    os.makedirs(output_dir, exist_ok=True)

    filename = "slow-queries-%s.txt" % datetime.now().strftime("%d-%b-%Y")
    path = os.path.join(output_dir, filename)
    report_text = render_raw_report(records)

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(report_text)

    maybe_chown_to_user(path, owner)
    return path


def group_by_owner(records: Sequence[SlowQueryRecord]) -> Dict[str, List[SlowQueryRecord]]:
    grouped: Dict[str, List[SlowQueryRecord]] = defaultdict(list)
    for record in records:
        grouped[record.attributed_owner].append(record)
    return grouped


def attach_report_dir(grouped_records: Dict[str, List[SlowQueryRecord]], report_dir: Optional[str]) -> None:
    if not report_dir:
        return
    for records in grouped_records.values():
        for record in records:
            record.__dict__["_report_dir"] = report_dir
