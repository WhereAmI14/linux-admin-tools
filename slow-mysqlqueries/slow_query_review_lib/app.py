from __future__ import annotations

import sys
from typing import Optional, Sequence

from .cli import parse_args, prompt_for_target, prompt_for_time_filter, should_use_color
from .parser import detect_log_file, filter_records, load_cpanel_users, parse_slow_log
from .reporting import (
    Palette,
    attach_report_dir,
    group_by_owner,
    render_summary,
    write_raw_slow_query_report,
    write_reports,
)
from .time_utils import build_time_filter_label, build_time_filter_phrase, parse_interval_time, parse_timeframe


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    args = prompt_for_target(args)
    args = prompt_for_time_filter(args)
    palette = Palette(should_use_color(args.no_color))

    try:
        since_delta = parse_timeframe(args.since)
        from_time = parse_interval_time(args.from_time)
        to_time = parse_interval_time(args.to_time)
    except ValueError as exc:
        print(palette.color("Error: %s" % exc, palette.bad), file=sys.stderr)
        return 2

    if from_time and to_time and from_time > to_time:
        print(palette.color("Error: --from must be earlier than or equal to --to.", palette.bad), file=sys.stderr)
        return 2

    time_filter_label = build_time_filter_label(args.since, from_time, to_time)
    time_filter_phrase = build_time_filter_phrase(args.since, from_time, to_time)

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
        from_time=from_time,
        to_time=to_time,
        cpanel_user=args.user,
        include_system=args.include_system,
    )

    if not filtered_records:
        scope = "user %s" % args.user if args.user else "all users"
        print(palette.color("No slow query records matched %s with time filter %s." % (scope, time_filter_label), palette.warn))
        return 0

    if args.user:
        title = "single user (%s)" % args.user
        print(
            render_summary(
                title=title,
                records=filtered_records,
                log_file=log_file,
                time_filter_label=time_filter_label,
                time_filter_phrase=time_filter_phrase,
                top_n=args.top,
                palette=palette,
                include_owner_breakdown=False,
            )
        )
        try:
            raw_report_path = write_raw_slow_query_report(args.user, filtered_records, args.report_dir)
            print(palette.color("Raw slow-query report: %s" % raw_report_path, palette.good))
        except OSError as exc:
            print(palette.color("Skipped raw slow-query report: %s" % exc, palette.warn))
        if args.write_user_reports:
            grouped = {args.user: list(filtered_records)}
            attach_report_dir(grouped, args.report_dir)
            for item in write_reports(grouped, log_file, time_filter_label, time_filter_phrase, args.top):
                print(palette.color("Analytical report: %s" % item, palette.good))
        return 0

    print(
        render_summary(
            title="all users",
            records=filtered_records,
            log_file=log_file,
            time_filter_label=time_filter_label,
            time_filter_phrase=time_filter_phrase,
            top_n=args.top,
            palette=palette,
            include_owner_breakdown=True,
        )
    )

    if args.write_user_reports:
        grouped = group_by_owner(filtered_records)
        attach_report_dir(grouped, args.report_dir)
        written = write_reports(grouped, log_file, time_filter_label, time_filter_phrase, args.top)
        if written:
            print("")
            print(palette.color("Report files", palette.accent))
            print("-" * 12)
            for item in written:
                code = palette.good if not item.startswith("Skipped ") else palette.warn
                print(palette.color(item, code))

    return 0
