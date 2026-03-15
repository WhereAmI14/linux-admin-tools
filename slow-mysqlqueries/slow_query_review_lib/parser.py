from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import (
    DEFAULT_LOG_PATH,
    SERVER_NOISE_PREFIXES,
    SYSTEM_NAMES,
    SYSTEM_OWNER,
    SlowQueryRecord,
)
from .time_utils import parse_log_timestamp


USER_HOST_RE = re.compile(r"^# User@Host: ([^\[]+)\[([^\]]*)\] @ ([^ ]+) \[[^\]]*\]\s+Id:\s*(\d+)")
QUERY_STATS_RE = re.compile(
    r"^# Query_time:\s*([0-9.]+)\s+Lock_time:\s*([0-9.]+)\s+"
    r"Rows_sent:\s*(\d+)\s+Rows_examined:\s*(\d+)"
)
QUALIFIED_TABLE_RE = re.compile(r"`([A-Za-z0-9_]+)`\.`([A-Za-z0-9_]+)`")


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
            if not entry.startswith("."):
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
    accounts = meta.get("acct", []) if isinstance(meta, dict) else []
    users = []
    for account in accounts:
        if isinstance(account, dict) and account.get("user"):
            users.append(str(account["user"]))
    return users


def extract_qualified_database(sql: str) -> Optional[str]:
    match = QUALIFIED_TABLE_RE.search(sql)
    return match.group(1) if match else None


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
    records: List[SlowQueryRecord] = []
    current: Optional[Dict[str, object]] = None
    sql_lines: List[str] = []

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

            if line.startswith("SET timestamp=") or line.startswith(SERVER_NOISE_PREFIXES):
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
        database=(str(current["database"]) if current.get("database") not in (None, "") else None),
        sql=sql or "(empty statement)",
        execution_owner=execution_owner,
        attributed_owner=attributed_owner,
        owner_source=owner_source,
    )


def filter_records(
    records: Sequence[SlowQueryRecord],
    since_delta: Optional[timedelta],
    from_time: Optional[datetime],
    to_time: Optional[datetime],
    cpanel_user: Optional[str],
    include_system: bool,
) -> List[SlowQueryRecord]:
    filtered = list(records)

    if since_delta is not None:
        cutoff = datetime.now(timezone.utc) - since_delta
        filtered = [record for record in filtered if record.timestamp >= cutoff]
    if from_time is not None:
        filtered = [record for record in filtered if record.timestamp >= from_time]
    if to_time is not None:
        filtered = [record for record in filtered if record.timestamp <= to_time]

    if cpanel_user:
        target = cpanel_user.strip()
        legacy = target[:8]
        filtered = [
            record
            for record in filtered
            if record.attributed_owner == target
            or record.execution_owner == target
            or record.db_user == target
            or record.db_user.startswith(target + "_")
            or record.db_user.startswith(legacy + "_")
            or (record.database and record.database.startswith(target + "_"))
            or (record.database and record.database.startswith(legacy + "_"))
        ]

    if not include_system and cpanel_user is None:
        filtered = [record for record in filtered if record.attributed_owner != SYSTEM_OWNER]

    return filtered
