"""
Generate the Module_ItemData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Exports all Object and Potion stats (with
inheritance resolved) as a Lua table, covering all non-equipment items
including consumables, crafting ingredients, and generic objects.

Usage:
    python3 -m dos2_tools.scripts.generate_item_data_module
    python3 -m dos2_tools.scripts.generate_item_data_module --out Module_ItemData.lua
    python3 -m dos2_tools.scripts.generate_item_data_module --types Object Potion
"""

import re
import argparse
from collections import OrderedDict

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import to_lua_table

# Default types to include
DEFAULT_TYPES = {"Object", "Potion"}


def convert_type(value):
    """Convert string values to appropriate Python types."""
    if not isinstance(value, str):
        return value

    if re.match(r"^-?\d+$", value):
        return int(value)

    val_lower = value.lower()
    if val_lower in ("true", "yes"):
        return True
    if val_lower in ("false", "no"):
        return False

    try:
        return float(value)
    except ValueError:
        pass

    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return value[1:-1].replace('\\"', '"')

    return value.replace('"', '\\"')


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_ItemData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_ItemData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--types", nargs="+", default=list(DEFAULT_TYPES),
        help=f"Stat types to include (default: {sorted(DEFAULT_TYPES)})"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    include_types = set(args.types)

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats

    # Filter to selected types
    item_stats = {
        k: v for k, v in stats_db.items()
        if v.get("_type") in include_types
    }

    print(f"  Found {len(item_stats)} item entries (types: {sorted(include_types)}).")

    # Convert types
    typed_data = {}
    for entry_id, data in item_stats.items():
        typed_entry = OrderedDict()
        for key, value in data.items():
            if key.startswith("_") and key != "_type":
                continue
            typed_entry[key] = convert_type(value)
        typed_data[entry_id] = typed_entry

    # Resolve Boosts linking
    for entry_id, data in typed_data.items():
        if "Boosts" in data and isinstance(data["Boosts"], str):
            boost_keys = [k.strip() for k in data["Boosts"].split(";") if k.strip()]
            resolved_boosts = []
            for boost_key in boost_keys:
                if boost_key in typed_data:
                    resolved_boosts.append(typed_data[boost_key])
            data["Boosts"] = resolved_boosts

    lua_str = to_lua_table(typed_data)
    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
