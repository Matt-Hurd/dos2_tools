"""
Generate an item source map: which NPCs drop/sell each item.

Thin CLI using GameData() + TreasureParser.flatten_probabilities().
Ported from generate_item_source_map.py.

Outputs item_sources.json: { item_name -> { drops: [...], sells: [...] } }
Each entry lists NPCs with probability and quantity range.

Usage:
    python3 -m dos2_tools.scripts.generate_item_source_map
    python3 -m dos2_tools.scripts.generate_item_source_map --out my_sources.json --max-level 20
"""

import json
import argparse
from collections import defaultdict
from copy import deepcopy

from dos2_tools.core.game_data import GameData
from dos2_tools.core.data_models import LSJNode
from dos2_tools.core.parsers import parse_lsj_templates

MAX_SIMULATION_LEVEL = 20


def collect_npc_tables(game_data):
    """
    Scan level character files and root templates to build
    npc_name -> {'drops': set, 'trades': set} map.
    """
    loc = game_data.localization
    char_files = game_data.get_file_paths("level_characters")
    templates_by_mapkey = game_data.templates_by_mapkey

    npc_map = {}

    for f_path in char_files:
        if "Test" in f_path or "Develop" in f_path:
            continue

        _, level_objects = parse_lsj_templates(f_path)

        for obj_uuid, level_data in level_objects.items():
            # Merge root template data with level override
            node = LSJNode(level_data)
            template_uuid = node.get_value("TemplateName")
            merged = {}
            if template_uuid and template_uuid in templates_by_mapkey:
                merged = deepcopy(templates_by_mapkey[template_uuid])
            merged.update(level_data)
            merged_node = LSJNode(merged)

            # Get display name
            handle = merged_node.get_handle("DisplayName")
            npc_name = loc.get_handle_text(handle) if handle else None
            if not npc_name:
                npc_name = merged_node.get_value("DisplayName")
            if not npc_name:
                continue

            # Get Treasures (drops) and TradeTreasures (vendor stock).
            # _extract_game_object already unwraps these into plain list[str],
            # so we iterate directly rather than going through LSJNode.get_list().
            drops = set()
            trades = set()

            for field, dest in (("Treasures", drops), ("TradeTreasures", trades)):
                for val in merged.get(field, []):
                    if isinstance(val, str) and val not in ("Empty", ""):
                        dest.add(val)

            if not drops and not trades:
                continue

            if npc_name not in npc_map:
                npc_map[npc_name] = {"drops": set(), "trades": set()}
            npc_map[npc_name]["drops"].update(drops)
            npc_map[npc_name]["trades"].update(trades)

    return npc_map


def analyze_table(loot_engine, table_id, max_level, table_cache):
    """
    Compute per-item probability and quantity across all levels.
    Returns { item_id: { prob, min_qty, max_qty } }
    """
    if table_id in table_cache:
        return table_cache[table_id]

    aggregated = {}
    levels = range(1, max_level + 1, 2)

    for lvl in levels:
        root = loot_engine.build_loot_tree(table_id, lvl)
        if not root:
            continue
        flat = loot_engine.flatten_probabilities(root)
        for item_id, info in flat.items():
            if item_id not in aggregated:
                aggregated[item_id] = {"prob": 0.0, "min_qty": 9999, "max_qty": 0}
            aggregated[item_id]["prob"] = max(aggregated[item_id]["prob"], info["prob"])
            aggregated[item_id]["min_qty"] = min(aggregated[item_id]["min_qty"], info["min_qty"])
            aggregated[item_id]["max_qty"] = max(aggregated[item_id]["max_qty"], info["max_qty"])

    table_cache[table_id] = aggregated
    return aggregated


def main():
    parser = argparse.ArgumentParser(
        description="Generate item source map (which NPCs drop/sell each item)"
    )
    parser.add_argument(
        "--out", default="item_sources.json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--max-level", type=int, default=MAX_SIMULATION_LEVEL,
        help=f"Maximum level to simulate (default: {MAX_SIMULATION_LEVEL})"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization
    loot_engine = game.loot_engine

    print("Collecting NPC tables...")
    npc_map = collect_npc_tables(game)
    print(f"  Found {len(npc_map)} NPCs with loot tables.")

    table_cache = {}
    item_source_map = {}

    total = len(npc_map)
    for i, (npc_name, tables) in enumerate(npc_map.items(), 1):
        if i % 100 == 0:
            print(f"  Processing NPC {i}/{total}...")

        for table_id, source_key in (
            (tid, "drops") for tid in tables["drops"]
        ):
            items_data = analyze_table(loot_engine, table_id, args.max_level, table_cache)
            for item_id, stats in items_data.items():
                item_name = loc.get_text(item_id) or item_id
                if item_name not in item_source_map:
                    item_source_map[item_name] = {"drops": [], "sells": []}
                target = item_source_map[item_name]["drops"]
                existing = next((x for x in target if x["npc"] == npc_name), None)
                if not existing:
                    target.append({
                        "npc": npc_name,
                        "chance": round(stats["prob"], 4),
                        "min": stats["min_qty"],
                        "max": stats["max_qty"],
                    })
                else:
                    existing["chance"] = max(existing["chance"], stats["prob"])
                    existing["min"] = min(existing["min"], stats["min_qty"])
                    existing["max"] = max(existing["max"], stats["max_qty"])

        for table_id in tables["trades"]:
            items_data = analyze_table(loot_engine, table_id, args.max_level, table_cache)
            for item_id, stats in items_data.items():
                item_name = loc.get_text(item_id) or item_id
                if item_name not in item_source_map:
                    item_source_map[item_name] = {"drops": [], "sells": []}
                target = item_source_map[item_name]["sells"]
                existing = next((x for x in target if x["npc"] == npc_name), None)
                if not existing:
                    target.append({
                        "npc": npc_name,
                        "chance": round(stats["prob"], 4),
                        "min": stats["min_qty"],
                        "max": stats["max_qty"],
                    })
                else:
                    existing["chance"] = max(existing["chance"], stats["prob"])
                    existing["min"] = min(existing["min"], stats["min_qty"])
                    existing["max"] = max(existing["max"], stats["max_qty"])

    # Sort results
    for item in item_source_map:
        item_source_map[item]["drops"].sort(key=lambda x: x["chance"], reverse=True)
        item_source_map[item]["sells"].sort(key=lambda x: x["chance"], reverse=True)

    print(f"Exporting {len(item_source_map)} items to {args.out}...")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(item_source_map, f, indent=2, ensure_ascii=False)
    print("Done.")


if __name__ == "__main__":
    main()
