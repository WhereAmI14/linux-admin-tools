#!/usr/bin/env bash

set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cat <<'EOF'
Usage: inode-check.sh [target_dir] [top_n]

  target_dir  Directory to inspect. Defaults to the current directory.
  top_n       Number of folders to show in the direct-entry ranking. Defaults to 10.
EOF
    exit 0
fi

target_dir="${1:-.}"
top_n="${2:-10}"

format_path() {
    local path="$1"
    if [[ "$path" == "$target_dir" ]]; then
        printf '.'
        return
    fi

    path="${path#"$target_dir"/}"
    printf '%s' "$path"
}

print_du_table() {
    while IFS=$'\t' read -r left right; do
        local count path

        if [[ "$left" =~ ^[0-9]+$ ]]; then
            count="$left"
            path="$right"
        else
            count="$right"
            path="$left"
        fi

        [[ "$count" =~ ^[0-9]+$ ]] || continue
        printf '%10s  %s\n' "$count" "$(format_path "$path")"
    done
}

if [[ ! -d "$target_dir" ]]; then
    printf 'Error: %s is not a directory.\n' "$target_dir" >&2
    exit 1
fi

if ! [[ "$top_n" =~ ^[0-9]+$ ]] || [[ "$top_n" -lt 1 ]]; then
    printf 'Error: top_n must be a positive integer.\n' >&2
    exit 1
fi

if ! du --help 2>/dev/null | grep -q -- '--inodes'; then
    printf 'Error: this script requires GNU du with --inodes support.\n' >&2
    exit 1
fi

target_dir="$(realpath "$target_dir")"

printf 'Inode report for %s\n\n' "$target_dir"

printf 'Total inodes under target: '
du --inodes -s -x "$target_dir" \
    | awk -F '\t' '
        $1 ~ /^[0-9]+$/ { print $1; next }
        $2 ~ /^[0-9]+$/ { print $2; next }
    '

printf 'Recursive inode totals for immediate subdirectories\n'
printf '%10s  %s\n' 'INODES' 'PATH'
find "$target_dir" -mindepth 1 -maxdepth 1 -type d -print0 \
    | xargs -0r du --inodes -s -x \
    | sort -rn \
    | print_du_table

printf '\nTop %s folders by direct entries\n' "$top_n"
printf '%10s  %s\n' 'ENTRIES' 'PATH'
find "$target_dir" -mindepth 1 -xdev -printf '%h\0' \
    | awk -v RS='\0' '
        { counts[$0]++ }
        END {
            for (dir in counts) {
                printf "%d\t%s\n", counts[dir], dir
            }
        }
    ' \
    | sort -rn \
    | head -n "$top_n" \
    | while IFS=$'\t' read -r count path; do
        printf '%10s  %s\n' "$count" "$(format_path "$path")"
    done
