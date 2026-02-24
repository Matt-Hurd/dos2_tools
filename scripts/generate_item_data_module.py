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

import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import convert_type, to_lua_table  # noqa: F401 (convert_type re-exported for tests)
from dos2_tools.core.stats_helpers import build_typed_stat_dict, resolve_boosts_inline

# Default types to include
DEFAULT_TYPES = {"Object", "Potion"}


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

    typed_data = build_typed_stat_dict(item_stats)
    resolve_boosts_inline(typed_data)

    lua_str = to_lua_table(typed_data)
    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
