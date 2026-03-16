# disk-usage

Shows the largest directories and large files under a target path.

## Use

Local:

```bash
bash disk-usage.sh [path]
```

From GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/disk-usage/disk-usage.sh | bash
curl -fsSL https://raw.githubusercontent.com/WhereAmI14/linux-admin-tools/main/disk-usage/disk-usage.sh | bash -s -- /home/user
```

## Notes

- If no path is given, the script prompts for one.
- Press Enter at the prompt to scan the current working directory.
- `DISK_USAGE_TOP_DIRS` controls how many directories are shown. Default: `15`.
- Large-file sections use a threshold of `300 MB`.
