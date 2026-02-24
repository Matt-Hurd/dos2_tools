"""
Generate the Module_SkillData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Exports all SkillData stats (with inheritance
resolved) as a Lua table.

Note: Unlike armour/weapon, skill data is not filtered by a single `_type`
value — skills use types like "SkillData". All entries whose `_type`
starts with "Skill" are included, which covers the full skill taxonomy.

Usage:
    python3 -m dos2_tools.scripts.generate_skill_data_module
    python3 -m dos2_tools.scripts.generate_skill_data_module --out Module_SkillData.lua
"""

import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import convert_type, to_lua_table  # noqa: F401 (convert_type re-exported for tests)
from dos2_tools.core.stats_helpers import build_typed_stat_dict


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_SkillData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_SkillData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats

    # Filter to SkillData entries — _type starts with "Skill"
    skill_stats = {
        k: v for k, v in stats_db.items()
        if isinstance(v.get("_type"), str) and v["_type"].startswith("Skill")
    }

    print(f"  Found {len(skill_stats)} skill entries.")

    # Identify all unique _type values for diagnostics
    skill_types = sorted({v["_type"] for v in skill_stats.values()})
    print(f"  Skill types: {skill_types}")

    # No Boosts resolution needed for skills
    typed_data = build_typed_stat_dict(skill_stats)

    lua_str = to_lua_table(typed_data)
    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
