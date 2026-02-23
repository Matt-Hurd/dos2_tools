"""
Generate RecipeData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Ported from generate_recipes_module.py.
Reads ItemCombos data and writes a Lua table with recipe ingredients, results,
and crafting station info.

Usage:
    python3 -m dos2_tools.scripts.generate_recipes_module
    python3 -m dos2_tools.scripts.generate_recipes_module --outfile RecipeData.lua
"""

import argparse

from dos2_tools.core.game_data import GameData


def escape_lua_string(s):
    """Escape a string value for Lua."""
    if not s:
        return "nil"
    clean = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{clean}"'


def main():
    parser = argparse.ArgumentParser(
        description="Generate RecipeData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--outfile", default="RecipeData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization
    item_combos = game.item_combos  # dict of combo_name -> combo data

    lua_lines = ["return {"]

    for combo_name, combo_content in sorted(item_combos.items()):
        data = combo_content.get("Data", {})
        results = combo_content.get("Results", {})

        station = data.get("CraftingStation", "")

        ingredients = []
        for i in range(1, 6):
            obj_id = data.get(f"Object {i}")
            obj_type = data.get(f"Type {i}")
            transform = data.get(f"Transform {i}")

            if not obj_id:
                continue

            display_name = obj_id
            if obj_type == "Object":
                found_name = loc.get_text(obj_id)
                if found_name:
                    display_name = found_name

            ingredients.append({
                "id": obj_id,
                "type": obj_type,
                "transform": transform,
                "name": display_name,
            })

        result_items = []
        for i in range(1, 6):
            res_id = results.get(f"Result {i}")
            if not res_id:
                continue
            res_name = loc.get_text(res_id) or res_id
            result_items.append({"id": res_id, "name": res_name})

        lua_lines.append(f'    ["{combo_name}"] = {{')

        if station:
            lua_lines.append(f"        station = {escape_lua_string(station)},")

        lua_lines.append("        ingredients = {")
        for ing in ingredients:
            lua_lines.append(
                f'            {{ id = {escape_lua_string(ing["id"])}, '
                f'type = {escape_lua_string(ing["type"])}, '
                f'name = {escape_lua_string(ing["name"])}, '
                f'transform = {escape_lua_string(ing["transform"])} }},'
            )
        lua_lines.append("        },")

        lua_lines.append("        results = {")
        for res in result_items:
            lua_lines.append(
                f'            {{ id = {escape_lua_string(res["id"])}, '
                f'name = {escape_lua_string(res["name"])} }},'
            )
        lua_lines.append("        }")

        lua_lines.append("    },")

    lua_lines.append("}")

    with open(args.outfile, "w", encoding="utf-8") as f:
        f.write("\n".join(lua_lines))

    print(f"Generated {args.outfile} ({len(item_combos)} recipes)")


if __name__ == "__main__":
    main()
