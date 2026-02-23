"""
Export DOS2 items to JSON.

Thin CLI using GameData(). Exports unique items with display names,
stats info, root template UUIDs, and version provenance.

Usage:
    python3 -m dos2_tools.scripts.export_items
    python3 -m dos2_tools.scripts.export_items --out unique_items.json --all
"""

import json
import argparse

from dos2_tools.core.game_data import GameData


def main():
    parser = argparse.ArgumentParser(description="Export DOS2 item data to JSON")
    parser.add_argument(
        "--out", default="unique_items.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Export all items (default: only Unique == 1)"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization
    stats_db = game.stats
    templates_by_stats = game.templates_by_stats
    templates_by_mapkey = game.templates_by_mapkey

    items = {}

    for stats_id, stats_data in stats_db.items():
        if not args.all and stats_data.get("Unique") != "1":
            continue

        # Resolve display name
        display_name = game.resolve_display_name(stats_id)

        # Get root template info
        rt_uuid = stats_data.get("RootTemplate")
        icon_uuid = None
        description = None

        if rt_uuid and rt_uuid in templates_by_mapkey:
            rt = templates_by_mapkey[rt_uuid]
            from dos2_tools.core.data_models import LSJNode
            rt_node = LSJNode(rt)

            icon_node = rt.get("Icon")
            if isinstance(icon_node, dict):
                icon_uuid = icon_node.get("value")

            desc_handle = rt_node.get_handle("Description")
            if desc_handle:
                description = loc.get_handle_text(desc_handle)

        # Version provenance
        modified_by = []
        for rel_path, entry in game.file_index.items():
            if "Stats/Generated/Data/" in rel_path and entry.was_overridden:
                for version in entry.modified_by:
                    if version not in modified_by:
                        modified_by.append(version)

        items[stats_id] = {
            "stats_id": stats_id,
            "display_name": display_name,
            "root_template_uuid": rt_uuid,
            "icon_uuid": icon_uuid,
            "description": description,
            "stats": {
                k: v for k, v in stats_data.items()
                if not k.startswith("_")
            },
        }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(items)} items to {args.out}")


if __name__ == "__main__":
    main()
