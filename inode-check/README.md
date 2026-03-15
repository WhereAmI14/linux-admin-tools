# inode-check

Shows inode usage for a directory.

## Use

Local:

```bash
bash inode-check.sh [target_dir] [top_n]
```

From GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/inode-check/inode-check.sh | bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/inode-check/inode-check.sh | bash -s -- public_html
```

## Notes

- If no directory is given, the script prompts for one.
- `top_n` defaults to `10`.
- Requires GNU `du` with `--inodes`.
