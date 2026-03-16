#!/usr/bin/env bash

if [[ -z "${BASH_VERSION:-}" ]]; then
    echo "This script must be run with bash." >&2
    exit 1
fi

set -euo pipefail

readonly DEFAULT_THRESHOLD_MB=300
readonly DEFAULT_TOP_DIRS=15
readonly INVOCATION_DIR="$(pwd -P)"
readonly THRESHOLD_LABEL="${DEFAULT_THRESHOLD_MB} MB"

USE_COLOR=0
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" ]]; then
    USE_COLOR=1
fi

if [[ "$USE_COLOR" -eq 1 ]]; then
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
    BLUE=$'\033[34m'
    CYAN=$'\033[36m'
    GREEN=$'\033[32m'
    YELLOW=$'\033[33m'
    MAGENTA=$'\033[35m'
else
    BOLD=""
    RESET=""
    BLUE=""
    CYAN=""
    GREEN=""
    YELLOW=""
    MAGENTA=""
fi

read_tty() {
    local prompt="$1"
    local value=""

    if ! { exec 3</dev/tty; } 2>/dev/null; then
        return 1
    fi

    if ! read -ru 3 -rp "$prompt" value; then
        exec 3<&-
        return 1
    fi

    exec 3<&-
    printf '%s' "$value"
}

usage() {
    cat <<EOF
Usage: $(basename "$0") [PATH]

Scan disk usage under PATH.

If PATH is omitted, the script prompts for one. Submitting an empty prompt
defaults to the directory where the script was executed.

Environment:
  DISK_USAGE_TOP_DIRS   Number of largest directories to show (default: ${DEFAULT_TOP_DIRS})
EOF
}

add_warning() {
    WARNINGS+=("$1")
}

print_warnings() {
    local warning

    if [[ "${#WARNINGS[@]}" -eq 0 ]]; then
        return 0
    fi

    print_title "$YELLOW" "Warnings"
    for warning in "${WARNINGS[@]}"; do
        printf '%s\n' "$warning"
    done
    printf '\n'
}
# Convert bytes to human-readable format
human_size() {
    local bytes="$1"

    awk -v bytes="$bytes" '
        function human(v) {
            split("B KB MB GB TB PB", units, " ")
            unit = 1
            while (v >= 1024 && unit < length(units)) {
                v /= 1024
                unit++
            }

            if (v >= 100 || unit == 1) {
                return sprintf("%.0f %s", v, units[unit])
            }

            return sprintf("%.1f %s", v, units[unit])
        }

        BEGIN {
            print human(bytes)
        }
    '
}

print_title() {
    local color="$1"
    local text="$2"
    printf '%b%s%b\n' "${BOLD}${color}" "$text" "$RESET"
}

print_kv() {
    local label="$1"
    local value="$2"
    printf '%b%-18s%b %s\n' "$BOLD" "$label" "$RESET" "$value"
}

print_table() {
    local title="$1"
    local color="$2"
    local input_file="$3"
    local size_header="$4"
    local path_header="$5"
    local empty_message="$6"

    print_title "$color" "$title"

    if [[ ! -s "$input_file" ]]; then
        printf '%s\n\n' "$empty_message"
        return
    fi

    printf '%b%-14s %s%b\n' "$BOLD" "$size_header" "$path_header" "$RESET"
    printf '%b%-14s %s%b\n' "$BOLD" "--------------" "----------------------------------------" "$RESET"

    awk -F'\t' -v color="$color" -v reset="$RESET" '
        function human(v, units, n, u) {
            n = split("B KB MB GB TB PB", units, " ")
            u = 1
            while (v >= 1024 && u < n) {
                v /= 1024
                u++
            }

            if (v >= 100 || u == 1) {
                return sprintf("%.0f %s", v, units[u])
            }

            return sprintf("%.1f %s", v, units[u])
        }

        NF >= 2 && $1 != "" && $2 != "" {
            printf "%s%-14s%s %s\n", color, human($1), reset, $2
        }
    ' "$input_file"

    printf '\n'
}

target_dir="${1:-}"
top_dirs="${DISK_USAGE_TOP_DIRS:-$DEFAULT_TOP_DIRS}"
WARNINGS=()

if [[ "${target_dir:-}" == "-h" || "${target_dir:-}" == "--help" ]]; then
    usage
    exit 0
fi

if ! [[ "$top_dirs" =~ ^[0-9]+$ ]] || [[ "$top_dirs" -lt 1 ]]; then
    printf 'Error: DISK_USAGE_TOP_DIRS must be a positive integer.\n' >&2
    exit 1
fi

if [[ -z "$target_dir" ]]; then
    if prompt_value="$(read_tty "Path to scan [default: ${INVOCATION_DIR}]: ")"; then
        target_dir="${prompt_value:-$INVOCATION_DIR}"
    else
        target_dir="$INVOCATION_DIR"
    fi
fi

if [[ ! -d "$target_dir" ]]; then
    printf 'Error: %s is not a directory.\n' "$target_dir" >&2
    exit 1
fi

target_dir="$(realpath "$target_dir")"

if [[ ! -r "$target_dir" || ! -x "$target_dir" ]]; then
    printf 'Error: %s is not accessible by the current user.\n' "$target_dir" >&2
    exit 1
fi

report_dir="$(mktemp -d)"
directories_report="$report_dir/directories.tsv"
large_files_report="$report_dir/large-files.tsv"
archives_report="$report_dir/archives.tsv"
logs_report="$report_dir/logs.tsv"
other_report="$report_dir/other.tsv"
du_tree_stderr="$report_dir/du-tree.stderr"
find_stderr="$report_dir/find.stderr"
du_tree_report="$report_dir/du-tree.tsv"

cleanup() {
    rm -rf "$report_dir"
}
trap cleanup EXIT

: > "$directories_report"
: > "$large_files_report"
: > "$archives_report"
: > "$logs_report"
: > "$other_report"
: > "$du_tree_report"

du_tree_status=0
if du -x -B1 "$target_dir" > "$du_tree_report" 2> "$du_tree_stderr"; then
    :
else
    du_tree_status=$?
fi
target_total_bytes="$(awk -v target="$target_dir" '$2 == target { print $1; exit }' "$du_tree_report")"

sort -rn "$du_tree_report" \
    | awk -v target="$target_dir" -v limit="$top_dirs" '
        $2 != target && n < limit {
            print
            n++
        }
    ' > "$directories_report"

find_status=0
if find "$target_dir" -xdev -type f -size +"${DEFAULT_THRESHOLD_MB}"M -printf '%s\t%p\n' 2> "$find_stderr" \
    | sort -rn > "$large_files_report"; then
    :
else
    find_status=$?
fi

if [[ -z "${target_total_bytes:-}" ]]; then
    printf 'Error: unable to determine disk usage for %s.\n' "$target_dir" >&2
    exit 1
fi

awk -F'\t' -v archives_out="$archives_report" -v logs_out="$logs_report" -v other_out="$other_report" '
    NF >= 2 && $1 != "" && $2 != "" {
        path = tolower($2)

        if (path ~ /\.(log|out|err)$/ ||
            path ~ /\.log\.[0-9]+$/ ||
            path ~ /\/log\// ||
            path ~ /\/logs\// ||
            path ~ /\/[^/]*_log$/ ||
            path ~ /-log$/) {
            print > logs_out
        } else if (path ~ /\.(zip|tar|tar\.gz|tgz|tar\.bz2|tbz2|tbz|gz|bz2|xz|txz|7z|rar|zst|tar\.zst|lz|lz4|zipx|cab)$/) {
            print > archives_out
        } else {
            print > other_out
        }
    }
' "$large_files_report"

if [[ "$du_tree_status" -ne 0 || -s "$du_tree_stderr" ]]; then
    add_warning "Directory usage skipped some paths due to permission or filesystem errors."
fi

if [[ "$find_status" -ne 0 || -s "$find_stderr" ]]; then
    add_warning "Large file discovery skipped some paths due to permission or filesystem errors."
fi


# Disk Usage Review
print_title "$BLUE" "Disk Usage Review"
print_kv "Target" "$target_dir"
print_kv "Threshold" "> ${THRESHOLD_LABEL}"
print_kv "Total size" "$(human_size "$target_total_bytes")"
printf '\n'
print_warnings


# Output sections
print_table \
    "Largest Directories In Tree" \
    "$CYAN" \
    "$directories_report" \
    "SIZE" \
    "DIRECTORY" \
    "No subdirectories found."

print_table \
    "Compressed Archive Files Over ${THRESHOLD_LABEL}" \
    "$MAGENTA" \
    "$archives_report" \
    "SIZE" \
    "FILE" \
    "No large archive files found."

print_table \
    "Log Files Over ${THRESHOLD_LABEL}" \
    "$YELLOW" \
    "$logs_report" \
    "SIZE" \
    "FILE" \
    "No large log files found."

print_table \
    "Other Files Over ${THRESHOLD_LABEL}" \
    "$GREEN" \
    "$other_report" \
    "SIZE" \
    "FILE" \
    "No other large files found."
