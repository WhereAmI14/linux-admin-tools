# `slow_query_review.py`

Analytical replacement for the two existing shell scripts used to inspect MySQL slow queries on cPanel servers.

## Goals

- Parse the slow log once instead of rescanning it once per user.
- Support both modern cPanel/MySQL naming and older 8-character owner prefixes.
- Produce readable terminal output with colors.
- Keep the implementation compatible with Python 3.8 through 3.12.
- Optionally write analytical reports into `/home/<cpuser>/`.

## Usage

Review all users:

```bash
python3 slow_query_review.py --all-users
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

Use a custom log path:

```bash
python3 slow_query_review.py --all-users --log-file /path/to/mysql_slow.log
```

Write analytical reports per matched user:

```bash
python3 slow_query_review.py --all-users --write-user-reports
python3 slow_query_review.py --user easternm --write-user-reports
```

Write reports somewhere else:

```bash
python3 slow_query_review.py --all-users --write-user-reports --report-dir /root/slow-query-reports
```

Disable colors:

```bash
python3 slow_query_review.py --all-users --no-color
```

## CI

The repository includes GitHub Actions workflows at the repo root:

- `slow-mysqlqueries-dev-ci.yml` runs on pushes and pull requests targeting `dev`, and tests the tool on Python 3.8 through 3.12.
- `slow-mysqlqueries-sonar.yml` runs a SonarQube Cloud scan for this tool when a `SONAR_TOKEN` repository secret is present.

To enable SonarQube Cloud analysis, add a repository secret named `SONAR_TOKEN`.

## Notes

- Attribution prefers the selected database name when it maps cleanly to a cPanel owner. This helps catch queries executed as `root` against a user's database.
- If no cPanel account list is available, the tool falls back to prefix-based owner detection.
- `--include-system` keeps unattributed/system-level queries in the all-user summary. Without it, the all-user view focuses on cPanel-owned activity.
