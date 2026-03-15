#!/usr/bin/env bash
set -euo pipefail

OWNER="${SLOW_QUERY_REVIEW_OWNER:-WhereAmI14}"
REPO="${SLOW_QUERY_REVIEW_REPO:-linux-admin-tools}"
REF="${SLOW_QUERY_REVIEW_REF:-dev}"
FILES=(
    "slow-mysqlqueries/slow_query_review.py"
    "slow-mysqlqueries/slow_query_review_lib/__init__.py"
    "slow-mysqlqueries/slow_query_review_lib/app.py"
    "slow-mysqlqueries/slow_query_review_lib/cli.py"
    "slow-mysqlqueries/slow_query_review_lib/models.py"
    "slow-mysqlqueries/slow_query_review_lib/parser.py"
    "slow-mysqlqueries/slow_query_review_lib/reporting.py"
    "slow-mysqlqueries/slow_query_review_lib/time_utils.py"
)

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found in PATH." >&2
    exit 1
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/slow_query_review.XXXXXX")"
cleanup() {
    rm -rf "${tmp_dir}"
}
trap cleanup EXIT

download_file() {
    local relative_path="$1"
    local url="https://raw.githubusercontent.com/${OWNER}/${REPO}/${REF}/${relative_path}"
    local destination="${tmp_dir}/${relative_path#slow-mysqlqueries/}"

    mkdir -p "$(dirname "${destination}")"

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "${url}" -o "${destination}"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "${destination}" "${url}"
    else
        echo "curl or wget is required to download ${url}." >&2
        exit 1
    fi
}

for file in "${FILES[@]}"; do
    download_file "${file}"
done

entrypoint="${tmp_dir}/slow_query_review.py"
if [[ ! -f "${entrypoint}" ]]; then
    echo "Failed to download ${entrypoint}." >&2
    exit 1
fi

exec python3 "${entrypoint}" "$@"
