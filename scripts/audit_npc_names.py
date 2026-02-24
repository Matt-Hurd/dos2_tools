"""
Audit NPC display name frequencies across all loaded level characters.

Scans level character LSJ files, resolves each character's display name
via localization, and reports how frequently each name appears. Useful
for identifying generic NPCs vs. unique named characters.

Ported from dos2_tools_old/scripts/audit_npc_names.py.

Usage:
    python3 -m dos2_tools.scripts.audit_npc_names
    python3 -m dos2_tools.scripts.audit_npc_names --min-count 2 --targets Shark "Conway Pryce"
"""

import argparse
from collections import defaultdict
from copy import deepcopy

from dos2_tools.core.game_data import GameData
from dos2_tools.core.parsers import parse_lsj_templates


def main():
    parser = argparse.ArgumentParser(
        description="Audit NPC name frequencies across level characters"
    )
    parser.add_argument(
        "--min-count", type=int, default=2,
        help="Minimum occurrence count to display (default: 2)"
    )
    parser.add_argument(
        "--targets", nargs="*", default=["Shark", "Conway Pryce", "Pilgrim"],
        help="Specific names to show detailed breakdown for"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    print("Starting NPC Name Audit...")
    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization

    # name → list of dicts with metadata
    name_registry = defaultdict(list)
    total_processed = 0

    char_files = game.get_file_paths("level_characters")

    for f_path in char_files:
        if "Test" in f_path or "Develop" in f_path:
            continue
        _, level_objects = parse_lsj_templates(f_path)

        parts = f_path.replace("\\", "/").split("/")
        level_name = "Unknown"
        if "Levels" in parts:
            idx = parts.index("Levels")
            if idx + 1 < len(parts):
                level_name = parts[idx + 1]

        for obj_uuid, level_data in level_objects.items():
            total_processed += 1
            template_uuid = level_data.get("TemplateName", {}).get("value")

            final_data = {}
            if template_uuid and template_uuid in game.templates_by_mapkey:
                final_data = deepcopy(game.templates_by_mapkey[template_uuid])
            final_data.update(level_data)

            # Resolve display name
            final_name = "Unknown"
            display_node = final_data.get("DisplayName")
            if display_node and isinstance(display_node, dict):
                handle = display_node.get("handle")
                if handle:
                    text = loc.get_handle_text(handle)
                    if text:
                        final_name = text
                if final_name == "Unknown":
                    val = display_node.get("value")
                    if val:
                        text = loc.get_text(val)
                        final_name = text if text else val

            unique_uuid = final_data.get("MapKey", {}).get("value")
            internal_name_node = final_data.get("Name", {})
            internal_name = (
                internal_name_node.get("value", "Unknown")
                if isinstance(internal_name_node, dict)
                else "Unknown"
            )

            name_registry[final_name].append({
                "guid": unique_uuid,
                "internal": internal_name,
                "level": level_name,
            })

    print(f"\nProcessed {total_processed} total entities.")
    print("-" * 60)
    print(f"{'COUNT':<8} | {'NAME'}")
    print("-" * 60)

    sorted_registry = sorted(
        name_registry.items(), key=lambda item: len(item[1]), reverse=True
    )

    for name, entries in sorted_registry:
        if len(entries) >= args.min_count:
            print(f"{len(entries):<8} | {name}")

    if args.targets:
        print("\n--- Detailed Breakdown for Targets ---")
        for target in args.targets:
            if target in name_registry:
                entries = name_registry[target]
                print(f"\nTarget: {target} (Total: {len(entries)})")
                for entry in entries:
                    print(
                        f"  - GUID: {entry['guid']} "
                        f"| Level: {entry['level']} "
                        f"| Internal: {entry['internal']}"
                    )


if __name__ == "__main__":
    main()
