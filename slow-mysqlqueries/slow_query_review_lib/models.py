from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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
