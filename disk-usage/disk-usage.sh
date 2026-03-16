#!/usr/bin/env bash

if [[ -z "${BASH_VERSION:-}" ]]; then
    echo "This script must be run with bash." >&2
    exit 1
fi

set -euo pipefail

readonly DEFAULT_THRESHOLD_MB=300
readonly DEFAULT_TOP_DIRS=15

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

    if ! exec 3</dev/tty 2>/dev/null; then
        return 1
    fi

    if ! read -ru 3 -rp "$prompt" value; then
        exec 3<&-
        return 1
    fi

    exec 3<&-
    printf '%s' "$value"
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

classify_large_file() {
    local original_path="$1"
    local path="${original_path,,}"

    case "$path" in
        *.log|*.log.[0-9]*|*.out|*.err|*/log/*|*/logs/*|*/*_log|*-log)
            printf 'log'
            return
            ;;
    esac

    case "$path" in
        *.zip|*.tar|*.tar.gz|*.tgz|*.tar.bz2|*.tbz2|*.tbz|*.gz|*.bz2|*.xz|*.txz|*.7z|*.rar|*.zst|*.tar.zst|*.lz|*.lz4|*.zipx|*.cab)
            printf 'archive'
            return
            ;;
    esac

    printf 'other'
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

    while IFS=$'\t' read -r size path; do
        [[ -n "${size:-}" && -n "${path:-}" ]] || continue
        printf '%b%-14s%b %s\n' "$color" "$(human_size "$size")" "$RESET" "$path"
    done < "$input_file"

    printf '\n'
}

target_dir="${1:-}"
top_dirs="${DISK_USAGE_TOP_DIRS:-$DEFAULT_TOP_DIRS}"

if [[ "${target_dir:-}" == "-h" || "${target_dir:-}" == "--help" ]]; then
    usage
    exit 0
fi

if ! [[ "$top_dirs" =~ ^[0-9]+$ ]] || [[ "$top_dirs" -lt 1 ]]; then
    printf 'Error: DISK_USAGE_TOP_DIRS must be a positive integer.\n' >&2
    exit 1
fi

if [[ -z "$target_dir" ]]; then
    if prompt_value="$(read_tty "Path to inspect [default: $(pwd)]: ")"; then
        target_dir="${prompt_value:-$(pwd)}"
    else
        target_dir="$(pwd)"
    fi
fi

if [[ ! -d "$target_dir" ]]; then
    printf 'Error: %s is not a directory.\n' "$target_dir" >&2
    exit 1
fi

target_dir="$(realpath "$target_dir")"

directories_report="$(mktemp)"
large_files_report="$(mktemp)"
archives_report="$(mktemp)"
logs_report="$(mktemp)"
other_report="$(mktemp)"

cleanup() {
    rm -f "$directories_report" "$large_files_report" "$archives_report" "$logs_report" "$other_report"
}
trap cleanup EXIT

target_total_bytes="$(du -sx -B1 "$target_dir" 2>/dev/null | awk '{print $1}')"
 
du -x -B1 "$target_dir" 2>/dev/null \
    | sort -rn \
    | awk -v target="$target_dir" '$2 != target' \
    | awk -v limit="$top_dirs" 'NR <= limit' > "$directories_report"

find "$target_dir" -xdev -type f -size +"${DEFAULT_THRESHOLD_MB}"M -printf '%s\t%p\n' 2>/dev/null \
    | sort -rn > "$large_files_report"
# Read the large files report and classify each file into archives, logs, or others
while IFS=$'\t' read -r size path; do
    [[ -n "${size:-}" && -n "${path:-}" ]] || continue

    case "$(classify_large_file "$path")" in
        archive)
            printf '%s\t%s\n' "$size" "$path" >> "$archives_report"
            ;;
        log)
            printf '%s\t%s\n' "$size" "$path" >> "$logs_report"
            ;;
        *)
            printf '%s\t%s\n' "$size" "$path" >> "$other_report"
            ;;
    esac
done < "$large_files_report"


# Disk Usage Review
print_title "$BLUE" "Disk Usage Review"
print_kv "Target" "$target_dir"
print_kv "Threshold" "> ${DEFAULT_THRESHOLD_MB} MB"
print_kv "Total size" "$(human_size "$target_total_bytes")"
printf '\n'

# Output sections
print_table \
    "Largest Directories In Tree" \
    "$CYAN" \
    "$directories_report" \
    "SIZE" \
    "DIRECTORY" \
    "No subdirectories found."

print_table \
    "Compressed Archive Files Over 300 MB" \
    "$MAGENTA" \
    "$archives_report" \
    "SIZE" \
    "FILE" \
    "No large archive files found."

print_table \
    "Log Files Over 300 MB" \
    "$YELLOW" \
    "$logs_report" \
    "SIZE" \
    "FILE" \
    "No large log files found."

print_table \
    "Other Files Over 300 MB" \
    "$GREEN" \
    "$other_report" \
    "SIZE" \
    "FILE" \
    "No other large files found."
