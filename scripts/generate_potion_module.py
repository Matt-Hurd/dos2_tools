"""
Generate the Module_PotionData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Exports all Potion stats (with inheritance
resolved) as a Lua table. Covers consumables, scrolls, food, grenades, etc.

Usage:
    python3 -m dos2_tools.scripts.generate_potion_module
    python3 -m dos2_tools.scripts.generate_potion_module --out Module_PotionData.lua
"""

import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import convert_type, to_lua_table  # noqa: F401 (convert_type re-exported for tests)
from dos2_tools.core.stats_helpers import build_typed_stat_dict, resolve_boosts_inline


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_PotionData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_PotionData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats

    # Filter to Potion stats only
    potion_stats = {
        k: v for k, v in stats_db.items()
        if v.get("_type") == "Potion"
    }

    print(f"  Found {len(potion_stats)} potion entries.")

    typed_data = build_typed_stat_dict(potion_stats)
    resolve_boosts_inline(typed_data)  # potions can reference boost entries too

    lua_str = to_lua_table(typed_data)
    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
