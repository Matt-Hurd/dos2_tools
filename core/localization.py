"""
Localization system for DOS2 game data.

Handles the two-tier localization system:
  1. Handle-based: contentuid -> text (from english.xml)
  2. UUID-based: UUID -> handle -> text (from LSJ files)

Wraps everything in a Localization class for clean composition
into the GameData central loader.
"""

import os
import json
from collections import defaultdict

from dos2_tools.core.config import UUID_BLACKLIST
from dos2_tools.core.parsers import parse_lsj, parse_xml_localization
from dos2_tools.core.file_system import get_files_by_pattern


CACHE_FILE = "cache_localization.json"


class Localization:
    """
    Localization resolver for DOS2 game data.

    Loads and caches the handle map (contentuid -> text) and
    UUID map (UUID -> list of {file, handle}) for resolving
    display names and descriptions.
    """

    def __init__(self, handle_map=None, uuid_map=None):
        self.handle_map = handle_map or {}
        self.uuid_map = uuid_map or {}

    def get_text(self, key):
        """
        Resolve a localization key to text.

        Tries the handle map first, then the UUID map.
        Handles semicolons that sometimes appear in keys.
        """
        if not key:
            return None
        key = key.replace(";", "")

        # Direct handle lookup
        if key in self.handle_map:
            return self.handle_map[key]

        # UUID -> handle -> text
        if key in self.uuid_map:
            handle = self._get_single_handle(key)
            if handle and handle in self.handle_map:
                return self.handle_map[handle]

        return None

    def get_handle_text(self, handle):
        """Look up text directly by handle (contentuid)."""
        if not handle:
            return None
        return self.handle_map.get(handle)

    def _get_single_handle(self, uuid_val):
        """Get the best handle for a UUID (deterministic by sorting)."""
        entries = self.uuid_map.get(uuid_val)
        if not entries:
            return None
        entries.sort(key=lambda x: x["file"])
        return entries[0]["handle"]


def load_localization(file_index, config, force_refresh=False):
    """
    Load localization data, using a JSON cache when available.

    Args:
        file_index: Version-aware file index from resolve_load_order()
        config: Config dict with patterns
        force_refresh: Force rebuild even if cache exists

    Returns:
        Localization: Ready-to-use localization resolver
    """
    if not force_refresh and os.path.exists(CACHE_FILE):
        print(f"Loading localization from {CACHE_FILE}...")
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Localization(
                handle_map=data.get("handles", {}),
                uuid_map=data.get("uuids", {}),
            )
        except json.JSONDecodeError:
            print("Cache corrupted, rebuilding...")

    print("Building localization cache...")

    # Parse XML localization files
    xml_entries = get_files_by_pattern(file_index, config["patterns"]["localization_xml"])
    handle_map = {}
    for entry in xml_entries:
        path = entry.resolved_path if hasattr(entry, "resolved_path") else entry
        handle_map.update(parse_xml_localization(path))

    # Scan LSJ files for UUID -> handle mappings
    all_paths = (
        [e.resolved_path for e in file_index.values()]
        if isinstance(file_index, dict)
        else file_index
    )
    uuid_map = _scan_lsj_for_uuids(all_paths)

    # Save cache
    data = {"handles": handle_map, "uuids": uuid_map}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    return Localization(handle_map=handle_map, uuid_map=uuid_map)


def _scan_lsj_for_uuids(files):
    """
    Scan all files for LSJ-format UUID -> handle mappings.

    Only processes .lsj files. Returns a dict of UUID -> [{file, handle}, ...].
    """
    uuid_map = defaultdict(list)
    lsj_files = [f for f in files if f.endswith(".lsj")]

    total = len(lsj_files)
    for count, file_path in enumerate(lsj_files, 1):
        if count % 100 == 0:
            print(f"  Scanning LSJ {count}/{total}...", end="\r")

        data = parse_lsj(file_path)
        if not data:
            continue

        nodes = (
            data.get("save", {})
            .get("regions", {})
            .get("TranslatedStringKeys", {})
            .get("TranslatedStringKey", [])
        )
        if not isinstance(nodes, list):
            nodes = [nodes]

        for node in nodes:
            uuid_val = node.get("UUID", {}).get("value")
            if not uuid_val or uuid_val in UUID_BLACKLIST:
                continue

            handle_val = node.get("Content", {}).get("handle")
            if handle_val:
                uuid_map[uuid_val].append({
                    "file": file_path,
                    "handle": handle_val,
                })

    print(f"  Scanning LSJ Complete.            ")
    return dict(uuid_map)
