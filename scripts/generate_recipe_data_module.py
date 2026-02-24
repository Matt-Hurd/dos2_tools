"""
Generate the Module_RecipeData.lua Lua module for the DOS2 wiki.

Thin CLI using GameData(). Exports all crafting recipes (from ItemCombos)
as a Lua table, preserving ingredient requirements, result items, and
recipe metadata.

Usage:
    python3 -m dos2_tools.scripts.generate_recipe_data_module
    python3 -m dos2_tools.scripts.generate_recipe_data_module --out Module_RecipeData.lua
"""

import argparse

from dos2_tools.core.game_data import GameData


def escape_lua_string(s):
    if not s:
        return "nil"
    clean = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    return f'"{clean}"'


# Hardcoded display-name overrides for stats IDs where the data-driven lookup
# produces an incorrect or ambiguous result.
#
# BOOK_Paper_Sheet_A: matches many templates; the common name is "Sheet of Paper".
# WPN_UNIQUE_AtaraxianScythe: localization handle resolves to a wrong string.
NAME_OVERRIDES = {
    "BOOK_Paper_Sheet_A": "Sheet of Paper",
    "WPN_UNIQUE_AtaraxianScythe": "The Swornbreaker",
}


def build_recipe_lua(item_combos, game):
    """
    Build Lua lines matching the old RecipeData.lua format exactly.

    Output format per entry:
        ["combo_id"] = {
            station = "...",          -- optional
            ingredients = {
                { id = "...", type = "...", name = "...", transform = "..." },
            },
            results = {
                { id = "...", name = "..." },
            }
        },
    """
    lua_lines = []
    lua_lines.append("return {")

    for combo_id, combo_data in sorted(item_combos.items()):
        data = combo_data.get("Data", {})
        results = combo_data.get("Results", {})

        station = data.get("CraftingStation", "")

        # Collect ingredients from numbered Object/Type/Transform keys
        ingredients = []
        for i in range(1, 6):
            obj_id = data.get(f"Object {i}")
            if not obj_id:
                break
            obj_type = data.get(f"Type {i}", "")
            transform = data.get(f"Transform {i}", "")

            # Resolve display name by ingredient type
            display_name = NAME_OVERRIDES.get(obj_id)
            if display_name is None:
                display_name = obj_id
                if obj_type == "Object":
                    # NOTE: A stats ID used as a recipe ingredient (Type = "Object") is not
                    # a unique in-world item — many distinct RootTemplates can share the same
                    # Stats value.  For example, "BOOK_Paper_Sheet_A" is the stat entry for
                    # generic paper, but the game lets *any* item with that stat be used.
                    # We resolve to the display name of the first matching template we find,
                    # which may not match what players usually call the ingredient.  Listing
                    # every possible template per stat entry is out of scope here.
                    template_data = game.templates_by_stats.get(obj_id)
                    loc_name = game.resolve_display_name(obj_id, template_data=template_data)
                    if loc_name:
                        display_name = loc_name
                elif obj_type == "Category":
                    preview = game.combo_previews.get(obj_id, {})
                    tooltip = preview.get("Tooltip")
                    if tooltip:
                        display_name = tooltip

            ingredients.append({
                "id": obj_id,
                "type": obj_type,
                "transform": transform,
                "name": display_name,
            })

        # Collect results from numbered Result keys
        result_items = []
        for i in range(1, 6):
            res_id = results.get(f"Result {i}")
            if not res_id:
                break
            res_template = game.templates_by_stats.get(res_id)
            res_name = (
                NAME_OVERRIDES.get(res_id)
                or game.resolve_display_name(res_id, template_data=res_template)
                or res_id
            )
            result_items.append({"id": res_id, "name": res_name})

        lua_lines.append(f'    ["{combo_id}"] = {{')

        if station:
            lua_lines.append(f'        station = {escape_lua_string(station)},')

        lua_lines.append('        ingredients = {')
        for ing in ingredients:
            lua_lines.append(
                f'            {{ id = {escape_lua_string(ing["id"])}, '
                f'type = {escape_lua_string(ing["type"])}, '
                f'name = {escape_lua_string(ing["name"])}, '
                f'transform = {escape_lua_string(ing["transform"])} }},'
            )
        lua_lines.append('        },')

        lua_lines.append('        results = {')
        for res in result_items:
            lua_lines.append(
                f'            {{ id = {escape_lua_string(res["id"])}, '
                f'name = {escape_lua_string(res["name"])} }},'
            )
        lua_lines.append('        }')

        lua_lines.append('    },')

    lua_lines.append("}")
    return "\n".join(lua_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_RecipeData.lua for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_RecipeData.lua",
        help="Output Lua file path"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)

    print(f"  Loaded {len(game.item_combos)} crafting recipes.")

    final_lua = build_recipe_lua(game.item_combos, game)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(final_lua)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
