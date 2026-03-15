#!/usr/bin/env bash
set -euo pipefail

OWNER="${SLOW_QUERY_REVIEW_OWNER:-WhereAmI14}"
REPO="${SLOW_QUERY_REVIEW_REPO:-linux-admin-tools}"
REF="${SLOW_QUERY_REVIEW_REF:-dev}"
SCRIPT_PATH="slow-mysqlqueries/slow_query_review.py"
RAW_URL="https://raw.githubusercontent.com/${OWNER}/${REPO}/${REF}/${SCRIPT_PATH}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found in PATH." >&2
    exit 1
fi

tmp_file="$(mktemp "${TMPDIR:-/tmp}/slow_query_review.XXXXXX.py")"
cleanup() {
    rm -f "${tmp_file}"
}
trap cleanup EXIT

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${RAW_URL}" -o "${tmp_file}"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "${tmp_file}" "${RAW_URL}"
else
    echo "curl or wget is required to download ${RAW_URL}." >&2
    exit 1
fi

exec python3 "${tmp_file}" "$@"
