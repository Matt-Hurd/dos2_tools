"""
Generate the Module_WeaponData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Exports all weapon stats (with inheritance
resolved) as a Lua table. Boosts entries are resolved to their stat
data inline, matching the ArmourData pattern.

Usage:
    python3 -m dos2_tools.scripts.generate_weapon_module
    python3 -m dos2_tools.scripts.generate_weapon_module --out Module_WeaponData.lua
"""

import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import convert_type, to_lua_table  # noqa: F401 (convert_type re-exported for tests)
from dos2_tools.core.stats_helpers import build_typed_stat_dict, resolve_boosts_inline


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_WeaponData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_WeaponData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats

    # Filter to weapon stats only
    weapon_stats = {
        k: v for k, v in stats_db.items()
        if v.get("_type") == "Weapon"
    }

    print(f"  Found {len(weapon_stats)} weapon entries.")

    typed_data = build_typed_stat_dict(weapon_stats)
    resolve_boosts_inline(typed_data)

    lua_str = to_lua_table(typed_data)
    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
