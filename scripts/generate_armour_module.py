"""
Generate the Module_ArmourData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Ported from generate_armour_module.py.
Exports all armor and shield stats (with inheritance resolved) as a Lua table.
Boosts entries are resolved to their stat data inline.

Usage:
    python3 -m dos2_tools.scripts.generate_armour_module
    python3 -m dos2_tools.scripts.generate_armour_module --out Module_ArmourData.lua
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
        description="Generate Module_ArmourData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_ArmourData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats

    # Filter to armor and shield stats
    armor_shield_stats = {
        k: v for k, v in stats_db.items()
        if v.get("_type") in ("Armor", "Shield")
    }

    print(f"  Found {len(armor_shield_stats)} armor/shield entries.")

    # Convert types
    typed_data = {}
    for entry_id, data in armor_shield_stats.items():
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

    # Use the canonical Lua serializer from formatters if available,
    # otherwise fall back to inline implementation
    try:
        lua_str = to_lua_table(typed_data)
    except (ImportError, AttributeError):
        # Inline Lua serializer fallback
        def lua_value(val, depth=1):
            indent = "\t" * depth
            inner = "\t" * (depth + 1)
            if isinstance(val, bool):
                return str(val).lower()
            if isinstance(val, (int, float)):
                return str(val)
            if isinstance(val, str):
                escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                return f'"{escaped}"'
            if isinstance(val, dict):
                if not val:
                    return "{}"
                parts = []
                for k, v in val.items():
                    lua_k = f'["{k}"]' if not re.match(r"^[a-zA-Z_]\w*$", str(k)) else str(k)
                    parts.append(f"{inner}{lua_k} = {lua_value(v, depth + 1)},")
                return "{\n" + "\n".join(parts) + "\n" + indent + "}"
            if isinstance(val, list):
                if not val:
                    return "{}"
                parts = [f"{inner}{lua_value(v, depth + 1)}," for v in val]
                return "{\n" + "\n".join(parts) + "\n" + indent + "}"
            if val is None:
                return "nil"
            return f'"{val}"'

        lua_str = lua_value(typed_data, depth=0)

    final_lua = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
