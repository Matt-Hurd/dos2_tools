"""
Generate wiki pages for items.

Thin CLI that demonstrates the new modular architecture:
  1. Load all game data via GameData (one line)
  2. Build the page aggregation index
  3. Generate wiki pages using wiki/items.py section generators
  4. Write output files

Supports the --sections flag for partial page generation.
"""

import os
import argparse
from collections import defaultdict

from dos2_tools.core.game_data import GameData
from dos2_tools.wiki.items import (
    scan_levels_for_items,
    generate_full_page,
    resolve_node_name,
    extract_action_data,
    SECTION_ORDER,
)


def build_page_index(game_data):
    """
    Build the per-page data index from game data.

    Aggregates stats, root templates, level locations, and unique
    variants into a dict of safe_name -> page_data.
    """
    loc = game_data.localization
    stats_db = game_data.stats
    combo_props = game_data.combo_properties

    # Build root template database
    rt_raw = game_data.templates_by_mapkey
    root_template_db = {}

    for rt_uuid, rt_data in rt_raw.items():
        # templates_by_mapkey now returns GameObject instances
        item_type = rt_data.type
        if item_type != "item":
            continue

        raw_dict = rt_data._to_raw_dict()
        name = resolve_node_name(raw_dict, loc)

        desc = None
        if rt_data.description and isinstance(rt_data.description, dict):
            handle = rt_data.description.get("handle")
            if handle:
                desc = loc.get_handle_text(handle)

        stats_id = rt_data.stats_id
        book_id, recipes = extract_action_data(raw_dict)

        root_template_db[rt_uuid] = {
            "name": name,
            "stats_id": stats_id,
            "description": desc,
            "book_id": book_id,
            "recipes": recipes,
            "raw_data": raw_dict,
        }

    # Scan levels
    print("Scanning levels for item placements...")
    template_locs, container_locs, unique_variants, all_regions = (
        scan_levels_for_items(game_data)
    )
    print(f"  Found items in regions: {', '.join(all_regions)}")

    # Build page index
    print("Aggregating page data...")
    pages = defaultdict(lambda: {
        "name": None,
        "stats_id": None,
        "description": None,
        "locations": set(),
        "root_template_uuid": None,
        "book_id": None,
        "taught_recipes": [],
        "properties": [],
    })

    # Pass 1: Stats entries
    for stats_id, stats_data in stats_db.items():
        rt_uuid = stats_data.get("RootTemplate")
        if not rt_uuid and "InventoryTab" not in stats_data:
            continue

        name = game_data.resolve_display_name(stats_id)
        if not name and rt_uuid and rt_uuid in root_template_db:
            name = root_template_db[rt_uuid]["name"]
        if not name or len(name) > 50:
            continue

        safe_name = name.strip()
        page = pages[safe_name]
        page["name"] = name
        page["stats_id"] = stats_id
        page["root_template_uuid"] = rt_uuid

        if rt_uuid and rt_uuid in root_template_db:
            rt_entry = root_template_db[rt_uuid]
            page["description"] = rt_entry["description"]
            page["book_id"] = rt_entry["book_id"]
            if rt_entry["recipes"]:
                page["taught_recipes"].extend(rt_entry["recipes"])

        if stats_id in container_locs:
            for loc_str in container_locs[stats_id]:
                page["locations"].add((loc_str, None))

        # Properties
        for prop_uuid, prop_info in combo_props.items():
            entries = prop_info.get("entries", [])
            for prop_entry in entries:
                p_type = prop_entry.get("Type")
                p_id = prop_entry.get("ObjectID")
                if p_type == "Object" and p_id == stats_id:
                    page["properties"].append(prop_uuid)
                if p_type == "Category":
                    cats = stats_data.get("ComboCategory", "").split(";")
                    if p_id in cats:
                        page["properties"].append(prop_uuid)

    # Pass 2: Root templates
    for rt_uuid, db_entry in root_template_db.items():
        name = db_entry["name"]
        if not name:
            continue

        safe_name = name.strip()
        page = pages[safe_name]
        page["name"] = name
        page["root_template_uuid"] = rt_uuid

        if not page["stats_id"]:
            page["stats_id"] = db_entry["stats_id"]
        if not page["description"]:
            page["description"] = db_entry["description"]
        if not page["book_id"]:
            page["book_id"] = db_entry["book_id"]
        if db_entry["recipes"]:
            page["taught_recipes"].extend(db_entry["recipes"])

        if rt_uuid in template_locs:
            for loc_str in template_locs[rt_uuid]:
                page["locations"].add((loc_str, rt_uuid))

        s_id = db_entry["stats_id"]
        if s_id and s_id in container_locs:
            for loc_str in container_locs[s_id]:
                page["locations"].add((loc_str, None))

    # Pass 3: Unique level variants
    for safe_name, var_data in unique_variants.items():
        page = pages[safe_name]
        page["name"] = var_data["name"]
        page["root_template_uuid"] = var_data["root_template_uuid"]
        page["stats_id"] = var_data["stats_id"]
        page["book_id"] = var_data.get("book_id")

        if var_data.get("recipes"):
            page["taught_recipes"].extend(var_data["recipes"])

        if var_data["description"]:
            page["description"] = var_data["description"]
        elif not page["description"]:
            parent_uuid = var_data["root_template_uuid"]
            if parent_uuid in root_template_db:
                page["description"] = root_template_db[parent_uuid]["description"]

        for loc_str in var_data["locations"]:
            page["locations"].add((loc_str, var_data["root_template_uuid"]))

    return pages


def main():
    parser = argparse.ArgumentParser(
        description="Generate wiki pages for DOS2 items"
    )
    parser.add_argument(
        "--outdir", default="item_wikitext",
        help="Output directory for generated wiki pages"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    parser.add_argument(
        "--sections", nargs="*", choices=SECTION_ORDER,
        help="Only generate these sections (default: all)"
    )
    parser.add_argument(
        "--filter", type=str, default=None,
        help="Only generate pages matching this name substring"
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # One line to load all game data
    game = GameData(refresh_loc=args.refresh_loc)

    # Build the page index
    pages = build_page_index(game)

    print(f"Generating wiki pages for {len(pages)} items...")

    count = 0
    for safe_name, page_data in pages.items():
        if args.filter and args.filter.lower() not in safe_name.lower():
            continue

        # Skip items with no root template UUID — nothing to anchor the page to
        if not page_data.get("root_template_uuid"):
            continue

        content = generate_full_page(page_data, game, sections=args.sections)

        if content:
            fname = f"{safe_name}.txt"
            path = os.path.join(args.outdir, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            count += 1

    print(f"Generated {count} wiki pages in {args.outdir}/")


if __name__ == "__main__":
    main()
