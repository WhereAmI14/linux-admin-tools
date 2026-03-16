# linux-admin-tools

Small admin scripts for Linux and cPanel servers.

## Tools

- `disk-usage/`: disk usage review for a target directory
- `inode-check/`: inode usage report for a target directory
- `slow-mysqlqueries/`: MySQL slow-query review tool for cPanel accounts

## Quick Use

```bash
git clone https://github.com/WhereAmI14/linux-admin-tools.git
cd linux-admin-tools
```

Inode check:

```bash
bash inode-check/inode-check.sh
```

Disk usage:

```bash
bash disk-usage/disk-usage.sh
```

Slow MySQL queries:

```bash
python3 slow-mysqlqueries/slow_query_review.py
```
