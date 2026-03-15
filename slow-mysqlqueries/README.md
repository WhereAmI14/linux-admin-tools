# `slow_query_review.py`

Analytical replacement for the two existing shell scripts used to inspect MySQL slow queries on cPanel servers.

## Goals

- Parse the slow log once instead of rescanning it once per user.
- Support both modern cPanel/MySQL naming and older 8-character owner prefixes.
- Produce readable terminal output with colors.
- Keep the implementation compatible with Python 3.8 through 3.12.
- Write a raw per-user slow-query extract for single-user runs, and optionally write analytical reports into `/home/<cpuser>/`.

## Usage

Review all users:

```bash
python3 slow_query_review.py --all-users
```

Run directly from GitHub with the shell bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/dev/slow-mysqlqueries/slow-queries-checker.sh | bash -s -- --all-users
```

If you omit `--all-users` and `--user`, the tool prompts for a cPanel username. Press Enter with no value to scan all users. It then prompts for a relative time filter such as `7d` or `3 days`; press Enter to scan all time:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/dev/slow-mysqlqueries/slow-queries-checker.sh | bash
```

Review one cPanel user:

```bash
python3 slow_query_review.py --user easternm
```

Limit by timeframe:

```bash
python3 slow_query_review.py --all-users --since 7d
python3 slow_query_review.py --user easternm --since "3 days"
```

Limit by an absolute interval:

```bash
python3 slow_query_review.py --all-users --from "2025-08-03 00:00" --to "2025-08-04 23:59:59"
python3 slow_query_review.py --user easternm --from "2025-08-03T00:00:00Z" --to "2025-08-03T12:00:00Z"
```

Use a custom log path:

```bash
python3 slow_query_review.py --all-users --log-file /path/to/mysql_slow.log
```

Write analytical reports per matched user:

```bash
python3 slow_query_review.py --all-users --write-user-reports
python3 slow_query_review.py --user easternm --write-user-reports
```

Single-user runs also write a raw extracted slow-log report filtered to the selected time period:

```bash
python3 slow_query_review.py --user easternm --since 7d
```

This creates `/home/easternm/slow-queries-<date>.txt` by default, or writes it under `--report-dir` if one is provided.

Write reports somewhere else:

```bash
python3 slow_query_review.py --all-users --write-user-reports --report-dir /root/slow-query-reports
```

Disable colors:

```bash
python3 slow_query_review.py --all-users --no-color
```

The bootstrap script forwards arguments to the Python tool and honors these optional environment overrides:

```bash
SLOW_QUERY_REVIEW_REF=main
SLOW_QUERY_REVIEW_OWNER=WhereAmI14
SLOW_QUERY_REVIEW_REPO=linux-admin-tools
```

## CI

The repository includes GitHub Actions workflows at the repo root:

- `slow-mysqlqueries-dev-ci.yml` runs Ruff first, then tests the tool on Python 3.8 through 3.12.
- `slow-mysqlqueries-sonar.yml` runs a SonarQube Cloud scan for this tool when a `SONAR_TOKEN` repository secret is present.

To enable SonarQube Cloud analysis, add a repository secret named `SONAR_TOKEN`.

## Notes

- Attribution prefers the selected database name when it maps cleanly to a cPanel owner. This helps catch queries executed as `root` against a user's database.
- If no cPanel account list is available, the tool falls back to prefix-based owner detection.
- `--include-system` keeps unattributed/system-level queries in the all-user summary. Without it, the all-user view focuses on cPanel-owned activity.
- `--from` and `--to` use UTC. If you omit the timezone in the value, the tool treats it as UTC.
