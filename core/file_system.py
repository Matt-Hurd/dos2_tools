"""
Version-aware file system for DOS2 game data.

Resolves the game's load order (Shared → Origins → Patch1 → ... → Patch10)
and tracks which version introduced each file and which versions modified it.
This replaces the old "last-writer-wins" flattening approach.
"""

import os
import re
import json

from dos2_tools.core.config import LOAD_ORDER
from dos2_tools.core.data_models import FileEntry


# Cache filename for the version-aware file index
CACHE_FILE = "cache_file_index.json"


def resolve_load_order(root_dir, cache_file=None):
    """
    Walk the load order directories and build a version-aware file index.

    Returns a dict keyed by relative path (below the load order directory),
    where each value is a FileEntry tracking provenance.

    For example, if Shared/Mods/Foo/Items/bar.lsj exists and
    Patch5/Mods/Foo/Items/bar.lsj also exists, the relative key is
    "Mods/Foo/Items/bar.lsj" and the FileEntry records:
      - introduced_by = "Shared"
      - modified_by = ["Shared", "Patch5"]
      - resolved_path = <path to Patch5 version>  (last wins)

    Args:
        root_dir: Base directory containing the load order folders (e.g. "exported")
        cache_file: Optional path to a JSON cache file for faster reloads

    Returns:
        dict[str, FileEntry]: Map of relative_path -> FileEntry
    """
    if cache_file and os.path.exists(cache_file):
        return _load_cache(cache_file)

    file_index = {}

    for layer in LOAD_ORDER:
        layer_path = os.path.join(root_dir, layer)
        if not os.path.exists(layer_path):
            continue

        for dirpath, _, filenames in os.walk(layer_path):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, layer_path)
                # Normalize to forward slashes for consistency
                rel_path = rel_path.replace("\\", "/")

                if rel_path in file_index:
                    # File exists in an earlier layer — record override
                    entry = file_index[rel_path]
                    entry.resolved_path = abs_path
                    entry.modified_by.append(layer)
                else:
                    # First time seeing this file
                    file_index[rel_path] = FileEntry(
                        resolved_path=abs_path,
                        relative_path=rel_path,
                        introduced_by=layer,
                        modified_by=[layer],
                    )

    if cache_file:
        _save_cache(file_index, cache_file)

    return file_index


def get_file_history(file_index, relative_path):
    """
    Get the version history for a specific file.

    Args:
        file_index: The file index from resolve_load_order()
        relative_path: Relative path to query (forward slashes)

    Returns:
        list[str]: Ordered list of load order entries that contain this file,
                   or empty list if the file is not found.
    """
    entry = file_index.get(relative_path)
    if entry:
        return list(entry.modified_by)
    return []


def get_all_resolved_paths(file_index):
    """
    Get a flat list of all resolved (final) file paths.

    This is the equivalent of the old resolve_load_order() return value,
    useful for backward compatibility with pattern matching.

    Returns:
        list[str]: All resolved absolute file paths.
    """
    return [entry.resolved_path for entry in file_index.values()]


def get_files_by_pattern(file_index, patterns):
    """
    Filter the file index using glob-style patterns.

    Matches patterns against the relative paths in the file index.
    Returns a list of FileEntry objects whose relative paths match.

    Args:
        file_index: The file index from resolve_load_order(), or a list of paths
        patterns: A single pattern string or list of glob patterns

    Returns:
        list[FileEntry]: Matching file entries (if dict input)
        list[str]: Matching file paths (if list input, for backward compat)
    """
    if isinstance(patterns, str):
        patterns = [patterns]

    regex_patterns = [_glob_to_regex(p) for p in patterns]

    # Support both the new dict-based index and legacy list-of-paths
    if isinstance(file_index, dict):
        matched = []
        for rel_path, entry in file_index.items():
            norm_path = rel_path.replace("\\", "/")
            for regex in regex_patterns:
                if regex.search(norm_path):
                    matched.append(entry)
                    break
        return matched
    else:
        # Legacy mode: list of absolute paths
        matched = []
        for f in file_index:
            norm_path = f.replace("\\", "/")
            for regex in regex_patterns:
                if regex.search(norm_path):
                    matched.append(f)
                    break
        return matched


def get_load_priority(filepath):
    """
    Get the numeric load priority for a file path.

    Lower numbers = earlier in the load order (lower priority).
    Used for sorting files by their override order.
    """
    parts = filepath.replace("\\", "/").split("/")
    for index, folder in enumerate(LOAD_ORDER):
        if folder in parts:
            return index
    return len(LOAD_ORDER)


def _glob_to_regex(pattern):
    """
    Convert a glob-style pattern to a compiled regex.

    Handles:
      - ** → match anything including path separators
      - *  → match anything except path separators
      - .  → escaped literal dot
    """
    p = pattern.replace("\\", "/")
    p = p.replace(".", r"\.")
    # Must replace ** before *, since * is a subset
    p = p.replace("**", "〰DOUBLESTAR〰")
    p = p.replace("*", r"[^/]*")
    p = p.replace("〰DOUBLESTAR〰", ".*")
    return re.compile(p + "$", re.IGNORECASE)


def _save_cache(file_index, cache_file):
    """Serialize the file index to JSON."""
    data = {}
    for rel_path, entry in file_index.items():
        data[rel_path] = {
            "resolved_path": entry.resolved_path,
            "introduced_by": entry.introduced_by,
            "modified_by": entry.modified_by,
        }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load_cache(cache_file):
    """Deserialize the file index from JSON."""
    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    file_index = {}
    for rel_path, info in data.items():
        file_index[rel_path] = FileEntry(
            resolved_path=info["resolved_path"],
            relative_path=rel_path,
            introduced_by=info["introduced_by"],
            modified_by=info["modified_by"],
        )
    return file_index
