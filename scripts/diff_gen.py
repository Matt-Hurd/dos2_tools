"""
General-purpose directory differ.

Compares two directories recursively and produces unified diff files for any
files that differ. Binary files (those that can't be decoded as UTF-8) are
skipped. Missing files in either directory are handled gracefully.

This script has no game-data dependencies and can be run standalone.

Ported from dos2_tools_old/scripts/diff_gen.py.

Usage:
    python3 -m dos2_tools.scripts.diff_gen <dir1> <dir2> <output_dir>

Example:
    python3 -m dos2_tools.scripts.diff_gen old_output/ new_output/ diffs/
"""

import sys
import difflib
from pathlib import Path


def get_file_lines(path):
    """Read file lines, returning None if the file is binary / unreadable."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readlines()
    except UnicodeDecodeError:
        return None


def main():
    if len(sys.argv) != 4:
        print("Usage: python -m dos2_tools.scripts.diff_gen <dir1> <dir2> <output_dir>")
        sys.exit(1)

    dir1 = Path(sys.argv[1])
    dir2 = Path(sys.argv[2])
    out_dir = Path(sys.argv[3])

    files1 = {p.relative_to(dir1) for p in dir1.rglob("*") if p.is_file()}
    files2 = {p.relative_to(dir2) for p in dir2.rglob("*") if p.is_file()}
    all_files = files1 | files2

    diff_count = 0

    for relative_path in sorted(all_files):
        p1 = dir1 / relative_path
        p2 = dir2 / relative_path

        lines1 = get_file_lines(p1)
        lines2 = get_file_lines(p2)

        # Skip binary files
        if lines1 is None or lines2 is None:
            continue

        diff = list(
            difflib.unified_diff(
                lines1,
                lines2,
                fromfile=str(p1),
                tofile=str(p2),
            )
        )

        if diff:
            diff_out_path = out_dir / relative_path.with_name(
                relative_path.name + ".diff"
            )
            diff_out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(diff_out_path, "w", encoding="utf-8") as f:
                f.writelines(diff)
            diff_count += 1

    print(f"Done. Generated {diff_count} diff file(s) in {out_dir}/")


if __name__ == "__main__":
    main()
