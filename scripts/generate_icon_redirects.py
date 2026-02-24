"""
Generate wiki icon redirect pages for DOS2 items.

Produces #REDIRECT [[File:...]] wikitext files that redirect from an item's
display-name-based icon filename to the actual icon filename stored in
the game files. Useful when an item's display name differs from its icon name.

Usage:
    python3 -m dos2_tools.scripts.generate_icon_redirects
    python3 -m dos2_tools.scripts.generate_icon_redirects --outdir wiki_redirects
"""

import os
import argparse

from dos2_tools.core.game_data import GameData


def get_node_value(node_data, key):
    """Extract a plain value from a template node field."""
    val_node = node_data.get(key)
    if isinstance(val_node, dict):
        return val_node.get("value")
    return val_node


def resolve_node_name(node_data, loc):
    """
    Resolve the display name for a root template node.
    Tries DisplayName handle first, then Stats localization, then Name field.
    """
    display_node = node_data.get("DisplayName")
    if display_node and isinstance(display_node, dict):
        handle = display_node.get("handle")
        if handle:
            text = loc.get_handle_text(handle)
            if text:
                return text

    stats_node = node_data.get("Stats")
    stats_id = None
    if isinstance(stats_node, dict):
        stats_id = stats_node.get("value")
    elif isinstance(stats_node, str):
        stats_id = stats_node

    if stats_id and stats_id != "None":
        text = loc.get_text(stats_id)
        if text:
            return text

    name_node = node_data.get("Name")
    if isinstance(name_node, dict):
        val = name_node.get("value")
        if val:
            return val

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate wiki icon redirect wikitext files for DOS2"
    )
    parser.add_argument(
        "--outdir", default="wiki_redirects",
        help="Output directory for redirect files (default: wiki_redirects)"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization
    rt_raw = game.templates_by_mapkey

    seen_redirects = {}
    count = 0

    print("Processing items and generating redirects...")

    for rt_uuid, rt_data in rt_raw.items():
        item_type = get_node_value(rt_data, "Type")
        if item_type != "item":
            continue

        display_name = resolve_node_name(rt_data, loc)
        if not display_name:
            continue

        icon_name = get_node_value(rt_data, "Icon")
        if not icon_name:
            continue

        clean_display_name = display_name.replace(" ", "_")
        clean_icon = icon_name.replace(" ", "_")

        if not clean_display_name or not clean_icon:
            continue
        if "|" in clean_display_name or "|" in clean_icon:
            print(f"  Skipping invalid names: '{clean_display_name}' or '{clean_icon}'")
            continue

        source_filename = f"{clean_display_name}_Icon.webp"
        target_filename = f"{clean_icon}_Icon.webp"

        # Skip self-redirects
        if source_filename == target_filename:
            continue

        if source_filename not in seen_redirects:
            seen_redirects[source_filename] = target_filename
            file_path = os.path.join(args.outdir, f"{source_filename}.wikitext")
            with open(file_path, "w", encoding="utf-8") as out:
                out.write(f"#REDIRECT [[File:{target_filename}]]")
            count += 1

    print(f"Done. Generated {count} redirect files in {args.outdir}/")


if __name__ == "__main__":
    main()
