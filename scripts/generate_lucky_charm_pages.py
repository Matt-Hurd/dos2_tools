"""
Generate Lucky Charm container map wikitext.

Thin CLI using GameData(). Ported from generate_lucky_charm_pages.py.
Identifies openable containers with valid inventories across root templates,
then scans level files to map them to game regions.

Produces a wikitext file with per-region ItemRegionMap calls.

Usage:
    python3 -m dos2_tools.scripts.generate_lucky_charm_pages
    python3 -m dos2_tools.scripts.generate_lucky_charm_pages --output LuckyCharm_Map.wikitext
"""

import argparse
from collections import defaultdict

from dos2_tools.core.game_data import GameData
from dos2_tools.core.parsers import parse_lsj_templates, get_region_name




def is_openable_container(node_data):
    """Check if the template has an OnUsePeaceAction of type 1 (open container)."""
    on_use = node_data.get("OnUsePeaceActions")
    if not on_use or not isinstance(on_use, list):
        return False
    for action_entry in on_use:
        actions = action_entry.get("Action")
        if not actions:
            continue
        if not isinstance(actions, list):
            actions = [actions]
        for action in actions:
            action_type = action.get("ActionType", {})
            if isinstance(action_type, dict):
                if action_type.get("value") == 1:
                    return True
    return False


def has_valid_inventory(inventory_node):
    """Check if the template has at least one InventoryItem entry."""
    if not inventory_node or not isinstance(inventory_node, list):
        return False
    for node in inventory_node:
        invs = node.get("Inventorys")
        if not invs:
            continue
        if not isinstance(invs, list):
            invs = [invs]
        for inv_entry in invs:
            item_val = inv_entry.get("InventoryItem")
            if isinstance(item_val, dict) and item_val.get("value"):
                return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate Lucky Charm container map wikitext"
    )
    parser.add_argument(
        "--output", default="LuckyCharm_Map.wikitext",
        help="Output wikitext file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    templates_by_mapkey = game.templates_by_mapkey
    stats_db = game.stats

    print("Filtering templates for Lucky Charm containers...")
    valid_uuids = set()

    for rt_uuid, rt_data in templates_by_mapkey.items():
        # Must be an item type
        item_type = rt_data.get("Type")
        if isinstance(item_type, dict):
            item_type = item_type.get("value")
        if item_type != "item":
            continue

        # Must have a valid inventory (has items inside it)
        if not has_valid_inventory(rt_data.get("InventoryList")):
            continue

        # Must have a stats entry
        stats_node = rt_data.get("Stats")
        stats_id = None
        if isinstance(stats_node, dict):
            stats_id = stats_node.get("value")
        elif isinstance(stats_node, str):
            stats_id = stats_node

        if not stats_id or stats_id == "None":
            continue

        # Skip seeds, greens, traps
        if any(stats_id.startswith(p) for p in ("CON_Seed_", "GRN_", "TRP_Trap_")):
            continue

        stat_entry = stats_db.get(stats_id)
        if not stat_entry:
            continue

        # If not openable via action type 1, must pass extra heuristics
        if not is_openable_container(rt_data):
            if stats_id.startswith("CONT_"):
                continue
            # Must have Constitution (HP proxy for destructible objects)
            try:
                constitution = int(stat_entry.get("Constitution", 0) or 0)
            except (ValueError, TypeError):
                constitution = 0
            if constitution <= 0:
                continue
            # Skip indestructible objects
            try:
                vitality = int(stat_entry.get("Vitality", 0) or 0)
            except (ValueError, TypeError):
                vitality = 0
            if vitality == -1:
                continue

        valid_uuids.add(rt_uuid)

    print(f"  Found {len(valid_uuids)} potential Lucky Charm container types.")

    # Scan level item files to place containers into regions
    print("Scanning level files for container placements...")
    region_uuid_map = defaultdict(set)
    level_files = game.get_file_paths("level_items")

    for f_path in level_files:
        if any(x in f_path for x in ("Test", "Develop", "GM_", "Arena")):
            continue
        region = get_region_name(f_path)
        _, level_objects = parse_lsj_templates(f_path)
        for obj in level_objects.values():
            template_uuid = obj.get("TemplateName")
            if template_uuid in valid_uuids:
                region_uuid_map[region].add(template_uuid)

    # Render output
    regions_to_output = [
        "FJ_FortJoy_Main",
        "RC_Main",
        "CoS_Main",
        "Arx_Main",
    ]

    content = "__NOTOC__\n= Lucky Charm Item Map =\n"
    content += "This map displays all openable containers and destructibles found by the script.\n"

    for region in regions_to_output:
        uuids = region_uuid_map.get(region, set())
        if not uuids:
            print(f"  Warning: No containers found in {region}")
            continue
        uuid_string = ",".join(sorted(uuids))
        content += f"\n== {region} ==\n"
        content += f"{{{{ItemRegionMap|region={region}|uuids={uuid_string}}}}}\n"

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Wrote wikitext to {args.output}")


if __name__ == "__main__":
    main()
