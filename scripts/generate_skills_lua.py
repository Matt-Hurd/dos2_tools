"""
Generate Module_Skills.lua — a full skill stats Lua module for the DOS2 wiki.

Dumps all Skill*.txt stats (with inheritance fully resolved) as a Lua table.
No field whitelist is applied — the full stat block is exported.

Ported from dos2_tools_old/scripts/generate_skills_lua.py.

Usage:
    python3 -m dos2_tools.scripts.generate_skills_lua
    python3 -m dos2_tools.scripts.generate_skills_lua --out Module_Skills.lua
"""

import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import to_lua_table


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_Skills.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_Skills.lua",
        help="Output Lua file path (default: Module_Skills.lua)"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats

    # Filter to Skill* type entries
    skill_stats = {
        k: v for k, v in stats_db.items()
        if isinstance(v.get("_type"), str) and v["_type"].startswith("Skill")
    }

    print(f"  Found {len(skill_stats)} skill entries.")

    # Strip internal keys before export
    final_lua_data = {}
    for entry_id, data in skill_stats.items():
        clean = {k: v for k, v in data.items() if not k.startswith("_")}
        if clean:
            final_lua_data[entry_id] = clean

    print(f"  Generating Lua module for {len(final_lua_data)} skills...")

    lua_str = to_lua_table(final_lua_data)
    output_content = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
