"""
Audit UUID localization conflicts across all loaded game files.

Scans all LSJ files for UUID→handle mappings and reports any UUIDs
that map to different handles in different files (true conflicts).
Safe duplicates (same UUID → same handle) are counted but not listed.

Ported from dos2_tools_old/scripts/audit_conflicts.py.

Usage:
    python3 -m dos2_tools.scripts.audit_conflicts
"""

from dos2_tools.core.game_data import GameData


def main():
    # Load full localization (this populates uuid_map for us)
    game = GameData()
    uuid_map = game.localization.uuid_map

    print(f"  Total Unique UUIDs: {len(uuid_map)}")

    conflicts = []
    safe_dupes = []

    for uuid, entries in uuid_map.items():
        if len(entries) > 1:
            first_handle = entries[0]["handle"]
            is_conflict = any(e["handle"] != first_handle for e in entries[1:])
            if is_conflict:
                conflicts.append((uuid, entries))
            else:
                safe_dupes.append((uuid, entries))

    print(f"Safe Duplicates:    {len(safe_dupes)}")
    print(f"CONFLICTS:          {len(conflicts)}")

    if conflicts:
        print("\n!!! ACTIVE CONFLICTS DETECTED !!!")
        for uuid, entries in conflicts:
            print(f"\nUUID: {uuid}")
            for e in entries:
                print(f"  - File: {e['file']}\n    Handle: {e['handle']}")
    else:
        print("\nClean scan.")


if __name__ == "__main__":
    main()
