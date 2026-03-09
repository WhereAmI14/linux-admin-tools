# inode-check

Reports inode usage for a target directory.

## What It Shows

- total inodes under the target
- recursive inode totals for immediate subdirectories
- top folders by direct entry count

## Usage

```bash
bash inode-check.sh [target_dir] [top_n]
```

## Arguments

- `target_dir`: directory to inspect, defaults to the current directory
- `top_n`: number of folders to show in the direct-entry ranking, defaults to `10`

## Requirements

- `bash`
- GNU `du` with `--inodes`
- `find`, `awk`, `sort`
