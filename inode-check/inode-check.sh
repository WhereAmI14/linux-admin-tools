#!/usr/bin/env bash

set -euo pipefail

#RED=$'\033[31;1m'
#CYAN=$'\033[36;1m'
#YELLOW=$'\033[33;1m'
BLUE=$'\033[34;1m'
GREEN=$'\033[32;1m'
DEF=$'\033[0m'
BOLD=$'\033[1m'


print_help() {
    cat <<'EOF'
Usage: inode-check.sh [target_dir] [top_n]
       inode-check.sh [--target-dir DIR] [--top N]

  target_dir  Directory to inspect. Defaults to the current directory.
  top_n       Number of folders to show in the direct-entry ranking. Defaults to 10.
  --target-dir, -d  Directory to inspect.
  --top, -n         Number of folders to show in the direct-entry ranking.
EOF
}

open_prompt_stream() {
    if [[ -t 0 ]]; then
        printf '/dev/stdin'
        return
    fi

    if [[ -r /dev/tty ]]; then
        printf '/dev/tty'
        return
    fi

    printf ''
}

prompt_for_target_dir() {
    local prompt_stream reply
    prompt_stream="$(open_prompt_stream)"

    if [[ -z "$prompt_stream" ]]; then
        printf '%s\n' "$PWD"
        return
    fi

    printf 'Enter directory to inspect [%s]: ' "${BOLD}$PWD${DEF}" >&2
    IFS= read -r reply < "$prompt_stream" || true

    if [[ -n "$reply" ]]; then
        printf '%s\n' "$reply"
    else
        printf '%s\n' "$PWD"
    fi
}

target_dir=""
top_n="10"
positionals=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            print_help
            exit 0
            ;;
        -d|--target-dir)
            if [[ $# -lt 2 ]]; then
                printf 'Error: %s requires a value.\n' "$1" >&2
                exit 1
            fi
            target_dir="$2"
            shift 2
            ;;
        -n|--top)
            if [[ $# -lt 2 ]]; then
                printf 'Error: %s requires a value.\n' "$1" >&2
                exit 1
            fi
            top_n="$2"
            shift 2
            ;;
        --)
            shift
            while [[ $# -gt 0 ]]; do
                positionals+=("$1")
                shift
            done
            ;;
        -*)
            printf 'Error: unknown option %s\n' "$1" >&2
            exit 1
            ;;
        *)
            positionals+=("$1")
            shift
            ;;
    esac
done

if [[ ${#positionals[@]} -gt 2 ]]; then
    printf 'Error: too many positional arguments.\n' >&2
    print_help >&2
    exit 1
fi

if [[ -z "$target_dir" && ${#positionals[@]} -ge 1 ]]; then
    target_dir="${positionals[0]}"
fi

if [[ ${#positionals[@]} -ge 2 ]]; then
    top_n="${positionals[1]}"
fi

if [[ -z "$target_dir" ]]; then
    target_dir="$(prompt_for_target_dir)"
fi

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

# From this point, the ouput is defined

printf 'Inode report for %s\n\n' "${GREEN}$target_dir${DEF}"

printf 'Total inodes under target: '
du --inodes -s -x "$target_dir" \
    | awk -F '\t' -v blue='\033[34;1m' -v reset='\033[0m' '
        $1 ~ /^[0-9]+$/ { print blue $1 reset; next }
        $2 ~ /^[0-9]+$/ { print blue $2 reset; next }
    '

printf 'Recursive inode totals for immediate subdirectories\n'
printf '%10s  %s\n' "${BOLD}INODES${DEF}" "${BOLD}PATH${DEF}"
find "$target_dir" -mindepth 1 -maxdepth 1 -type d -print0 \
    | xargs -0r du --inodes -s -x \
    | sort -rn \
    | print_du_table

printf '\nTop %s folders by direct entries\n' "$top_n"
printf '%10s  %s\n' "${BOLD}ENTRIES${DEF}" "${BOLD}PATH${DEF}"
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
