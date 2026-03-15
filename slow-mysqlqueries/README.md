# slow-mysqlqueries

Reviews MySQL slow-query logs for cPanel users.

## Use

Local:

```bash
python3 slow_query_review.py
python3 slow_query_review.py --all-users
python3 slow_query_review.py --user easternm --since 7d
python3 slow_query_review.py --user easternm --from "2025-08-03 00:00" --to "2025-08-04 23:59:59"
```

From GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/dev/slow-mysqlqueries/slow-queries-checker.sh | bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/dev/slow-mysqlqueries/slow-queries-checker.sh | bash -s -- --all-users
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/dev/slow-mysqlqueries/slow-queries-checker.sh | bash -s -- --user easternm --since 7d
```

## Notes

- If no user is given, the tool prompts for one. Press Enter to scan all users.
- It also prompts for a time filter like `7d` or `3 days`. Press Enter for all time.
- Single-user runs write a raw report: `/home/<cpuser>/slow-queries-<date>.txt`
- `--write-user-reports` also writes an analytical summary report.
- `--from` and `--to` are treated as UTC.
