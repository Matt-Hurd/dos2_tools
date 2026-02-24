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

import re
import argparse
from collections import OrderedDict

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import to_lua_table


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

    # Convert types (no Boosts resolution needed for skills)
    typed_data = {}
    for entry_id, data in skill_stats.items():
        typed_entry = OrderedDict()
        for key, value in data.items():
            if key.startswith("_") and key != "_type":
                continue
            typed_entry[key] = convert_type(value)
        typed_data[entry_id] = typed_entry

    lua_str = to_lua_table(typed_data)
    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
