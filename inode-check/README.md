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

Run directly from GitHub and let it prompt for the target directory:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/inode-check/inode-check.sh | bash
```

Pass a target directory from `curl | bash`:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/inode-check/inode-check.sh | bash -s -- public_html
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/inode-check/inode-check.sh | bash -s -- --target-dir public_html
```

## Arguments

- `target_dir`: directory to inspect, defaults to the current directory
- `top_n`: number of folders to show in the direct-entry ranking, defaults to `10`
- `--target-dir`, `-d`: named form of `target_dir`
- `--top`, `-n`: named form of `top_n`

## Requirements

- `bash`
- GNU `du` with `--inodes`
- `find`, `awk`, `sort`
