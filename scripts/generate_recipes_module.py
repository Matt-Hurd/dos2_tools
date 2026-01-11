import os
import argparse
import json
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_item_combos, parse_object_category_previews
from dos2_tools.core.localization import load_localization_data, get_localized_text

def escape_lua_string(s):
    if not s:
        return "nil"
    clean = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    return f'"{clean}"'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outfile", default="RecipeData.lua")
    args = parser.parse_args()

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    loc_data = load_localization_data(all_files, conf)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    item_combos_files = get_files_by_pattern(all_files, conf['patterns']['item_combos'])
    all_item_combos = {}
    for f in item_combos_files:
        all_item_combos.update(parse_item_combos(f))

    lua_lines = []
    lua_lines.append("return {")

    sorted_combos = sorted(all_item_combos.items())

    for combo_name, combo_content in sorted_combos:
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
                found_name = get_localized_text(obj_id, uuid_map, loc_map)
                if found_name:
                    display_name = found_name
            
            ingredients.append({
                "id": obj_id,
                "type": obj_type,
                "transform": transform,
                "name": display_name
            })

        result_items = []
        for i in range(1, 6):
            res_id = results.get(f"Result {i}")
            if not res_id:
                continue
            
            res_name = get_localized_text(res_id, uuid_map, loc_map) or res_id
            result_items.append({
                "id": res_id,
                "name": res_name
            })

        # if not ingredients or not result_items:
        #     continue

        lua_lines.append(f'    ["{combo_name}"] = {{')
        
        if station:
            lua_lines.append(f'        station = {escape_lua_string(station)},')

        lua_lines.append('        ingredients = {')
        for ing in ingredients:
            lua_lines.append(f'            {{ id = {escape_lua_string(ing["id"])}, type = {escape_lua_string(ing["type"])}, name = {escape_lua_string(ing["name"])}, transform = {escape_lua_string(ing["transform"])} }},')
        lua_lines.append('        },')

        lua_lines.append('        results = {')
        for res in result_items:
            lua_lines.append(f'            {{ id = {escape_lua_string(res["id"])}, name = {escape_lua_string(res["name"])} }},')
        lua_lines.append('        }')
        
        lua_lines.append('    },')

    lua_lines.append("}")

    with open(args.outfile, "w", encoding="utf-8") as f:
        f.write("\n".join(lua_lines))

if __name__ == "__main__":
    main()