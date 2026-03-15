# linux-admin-tools

A collection of focused Bash utilities for Linux system administration tasks.

Scripts are organized by category. Each subdirectory contains its own README with usage details.

---

## Tools

### disk/

| Script | Description |
|--------|-------------|
| [inode-check.sh](disk/inode-check.sh) | Reports inode usage for a target directory — totals, per-subdirectory breakdown, and top folders by direct entry count |

---

## Requirements

- Bash 4+
- GNU coreutils (`du`, `find`, `sort`, `awk`)

Individual scripts may have additional requirements listed in their own README.

---

## Usage

Clone the repo and run scripts directly:

```bash
git clone https://github.com/WhereAmI14/linux-admin-tools.git
cd linux-admin-tools
bash disk/inode-check.sh [target_dir] [top_n]
```

---

## License

MIT