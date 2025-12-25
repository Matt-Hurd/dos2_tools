import json
import os
import argparse
import re
from collections import defaultdict
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import (
    parse_stats_txt, parse_lsj_templates, 
    parse_item_combo_properties, parse_item_combos, 
    parse_object_category_previews
)
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.formatters import sanitize_filename
from dos2_tools.core.stats_engine import resolve_all_stats

def parse_and_group_locations(location_tuples):
    grouped = defaultdict(list)
    pattern = re.compile(r"([-\d\.,]+)\s*\(([^)]+)\)(?:\s*inside\s*(.+))?")

    for loc_str, uuid in location_tuples:
        match = pattern.search(loc_str)
        if match:
            coords = match.group(1)
            region = match.group(2)
            container = match.group(3)
            
            if container:
                loc_name = f"{container}"
            else:
                loc_name = "Ground Spawn"

            safe_uuid = uuid if uuid else ""
            key = (region, loc_name, safe_uuid)
            grouped[key].append(coords)
        else:
            safe_uuid = uuid if uuid else ""
            grouped[("Unknown", "Unknown", safe_uuid)].append(loc_str)
            
    return grouped

def get_region_name(file_path):
    parts = file_path.replace('\\', '/').split('/')
    if "Levels" in parts:
        return parts[parts.index("Levels")+1]
    if "Globals" in parts:
        return parts[parts.index("Globals")+1]
    return "Unknown"

def format_coordinate(transform_node):
    if not transform_node: return None
    if isinstance(transform_node, list) and len(transform_node) > 0:
        pos_node = transform_node[0].get("Position")
        if pos_node:
            val = pos_node.get("value", "")
            return val.replace(" ", ",")
    return None

def resolve_node_name(node_data, loc_map, uuid_map):
    display_node = node_data.get("DisplayName")
    if display_node and isinstance(display_node, dict):
        handle = display_node.get("handle")
        if handle in loc_map:
            return loc_map[handle]

    stats_node = node_data.get("Stats")
    stats_id = None
    if isinstance(stats_node, dict):
        stats_id = stats_node.get("value")
    elif isinstance(stats_node, str):
        stats_id = stats_node
        
    if stats_id and stats_id != "None":
        return get_localized_text(stats_id, uuid_map, loc_map)
    
    name_node = node_data.get("Name")
    if isinstance(name_node, dict):
        val = name_node.get("value")
        if val: return val

    return None

def extract_book_id(node_data):
    actions = node_data.get("OnUsePeaceActions")
    if not actions:
        return None
    
    if isinstance(actions, list):
        for action_block in actions:
            action_list = action_block.get("Action", [])
            if not isinstance(action_list, list):
                action_list = [action_list]
                
            for act in action_list:
                a_type = act.get("ActionType", {})
                if isinstance(a_type, dict) and a_type.get("value") == 11:
                    attributes = act.get("Attributes", [])
                    if not isinstance(attributes, list):
                        attributes = [attributes]
                    
                    for attr in attributes:
                        book_node = attr.get("BookId")
                        if book_node and isinstance(book_node, dict):
                            return book_node.get("value")
    return None

def load_recipe_prototype_data(all_files, conf):
    print("Loading Recipe prototypes...")
    recipe_files = get_files_by_pattern(all_files, conf['patterns']['recipes'])
    recipe_map = defaultdict(list)

    for f_path in recipe_files:
        data = json.loads(open(f_path, 'r', encoding='utf-8').read())
        
        save = data.get("save", {})
        regions = save.get("regions", {})
        recipes_node = regions.get("Recipes", {})
        recipe_list = recipes_node.get("Recipe", [])
        
        if not isinstance(recipe_list, list):
            recipe_list = [recipe_list]
            
        for r in recipe_list:
            title_node = r.get("Title", {})
            recipe_id_node = r.get("RecipeID", {})
            output_node = r.get("Recipes", {})
            
            title = title_node.get("value")
            r_id = recipe_id_node.get("value")
            output_str = output_node.get("value")
            
            if not output_str:
                continue

            outputs = [x.strip() for x in output_str.split(',') if x.strip()]
            
            if title:
                recipe_map[title].extend(outputs)

            if r_id and r_id != title:
                recipe_map[r_id].extend(outputs)

    return recipe_map

valid_levels = [
    "ARX_Endgame",
    "ARX_Main",
    "CoS_Main",
    "CoS_Main_Ending",
    "FJ_FortJoy_Main",
    "LV_HoE_Main",
    "RC_Main",
    "TUT_Tutorial_A",
]

def scan_levels_for_items(all_files, conf, root_template_db, loc_map, uuid_map):
    base_template_locs = defaultdict(list)
    container_locs = defaultdict(list)
    unique_level_variants = {}
    found_regions = set()

    level_files = get_files_by_pattern(all_files, conf['patterns']['level_items'])
    
    for f_path in level_files:
        if not any(lv in f_path for lv in valid_levels):
            continue
        
        region = get_region_name(f_path)
        found_regions.add(region)

        _, level_objects = parse_lsj_templates(f_path)
        
        for map_key, obj_data in level_objects.items():
            
            coords = format_coordinate(obj_data.get("Transform"))
            if not coords: continue
            
            full_loc_str = f"{coords} ({region})"
            template_uuid = obj_data.get("TemplateName", "")
            
            if template_uuid:
                instance_name = resolve_node_name(obj_data, loc_map, uuid_map)
                
                default_rt_name = None
                default_rt_stats = None
                default_book_id = None

                if template_uuid in root_template_db:
                    rt_entry = root_template_db[template_uuid]
                    default_rt_name = rt_entry.get("name")
                    default_rt_stats = rt_entry.get("stats_id")
                    default_book_id = rt_entry.get("book_id")

                if instance_name and instance_name != default_rt_name:
                    safe_var_name = sanitize_filename(instance_name)
                    
                    if safe_var_name not in unique_level_variants:
                        stats_node = obj_data.get("Stats", {})
                        stats_val = stats_node.get("value") if isinstance(stats_node, dict) else stats_node
                        
                        if not stats_val and default_rt_stats:
                            stats_val = default_rt_stats
                            
                        current_book_id = extract_book_id(obj_data) or default_book_id

                        desc_override = None
                        desc_node = obj_data.get('Description')
                        if isinstance(desc_node, dict) and 'handle' in desc_node:
                            handle = desc_node['handle']
                            if handle in loc_map:
                                desc_override = loc_map[handle]

                        unique_level_variants[safe_var_name] = {
                            "name": instance_name,
                            "stats_id": stats_val,
                            "root_template_uuid": template_uuid,
                            "description": desc_override,
                            "book_id": current_book_id,
                            "locations": set(),
                            "is_variant": True
                        }
                    
                    unique_level_variants[safe_var_name]["locations"].add(full_loc_str)
                
                else:
                    base_template_locs[template_uuid].append(full_loc_str)

            item_list_root = obj_data.get("ItemList", [])
            if item_list_root:
                container_name = resolve_node_name(obj_data, loc_map, uuid_map) or "Container"
                
                for item_entry in item_list_root:
                    items = item_entry.get("Item", [])
                    if not isinstance(items, list): items = [items]
                    
                    for item in items:
                        t_uuid = item.get("TemplateID", {}).get("value")
                        stats_id = item.get("ItemName", {}).get("value")
                        
                        if t_uuid:
                            loc_desc = f"{full_loc_str} inside {container_name}"
                            base_template_locs[t_uuid].append(loc_desc)
                        elif stats_id:
                            loc_desc = f"{full_loc_str} inside {container_name}"
                            container_locs[stats_id].append(loc_desc)

    char_files = get_files_by_pattern(all_files, conf['patterns']['level_characters'])

    for f_path in char_files:
        if 'Test' in f_path or 'Develop' in f_path or "GM_" in f_path or "Arena" in f_path: continue

        region = get_region_name(f_path)
        found_regions.add(region)
        _, level_objects = parse_lsj_templates(f_path)

        for map_key, obj_data in level_objects.items():
            coords = format_coordinate(obj_data.get("Transform"))
            if not coords: continue

            npc_name = resolve_node_name(obj_data, loc_map, uuid_map)
            if npc_name:
                npc_name = f"[[{npc_name}]]|on_npc=Yes"
            else:
                npc_name = "Unknown NPC"

            full_loc_str = f"{coords} ({region})"

            item_list_root = obj_data.get("ItemList", [])
            if not item_list_root: continue

            for item_entry in item_list_root:
                items = item_entry.get("Item", [])
                if not isinstance(items, list): items = [items]

                for item in items:
                    t_uuid = item.get("TemplateID", {}).get("value")
                    stats_id = item.get("ItemName", {}).get("value")
                    
                    if t_uuid and t_uuid != "":
                        loc_desc = f"{full_loc_str} inside {npc_name}"
                        base_template_locs[t_uuid].append(loc_desc)
                    elif stats_id and stats_id != "":
                        loc_desc = f"{full_loc_str} inside {npc_name}"
                        container_locs[stats_id].append(loc_desc)

    return base_template_locs, container_locs, unique_level_variants, sorted(list(found_regions))

def generate_crafting_wikitext(target_stats_id, target_categories, target_properties, all_combos, loc_map, uuid_map, resolved_all_stats, combo_props, category_previews):
    creation_rows = []
    product_rows = []

    for combo_id, combo in all_combos.items():
        data = combo.get("Data", {})
        results = combo.get("Results", {})
        
        result_id = results.get("Result 1")
        
        is_creation = (result_id == target_stats_id)
        is_product = False
        
        if not is_creation:
            for i in range(1, 6):
                obj_id = data.get(f"Object {i}")
                obj_type = data.get(f"Type {i}")
                
                if not obj_id: continue
                
                if obj_type == "Object" and obj_id == target_stats_id:
                    is_product = True
                    break
                
                if obj_type == "Category" and target_categories:
                    if obj_id in target_categories:
                        is_product = True
                        break
                
                if obj_type == "Property" and target_properties:
                    if obj_id in target_properties:
                        is_product = True
                        break

        if not is_creation and not is_product:
            continue

        row_text = "{{#invoke:CraftingRecipe|row"
        
        station = data.get("CraftingStation")
        if station:
            row_text += f"\n| station = {station}"

        for i in range(1, 6):
            obj_id = data.get(f"Object {i}")
            obj_type = data.get(f"Type {i}")
            transform = data.get(f"Transform {i}")
            
            if not obj_id: continue
            
            row_text += f"\n| mat{i} = {obj_id}"
            if obj_type: row_text += f"\n| mat{i}_type = {obj_type}"
            if transform: row_text += f"\n| mat{i}_transform = {transform}"
            
            name = None
            icon = None
            
            if obj_type == "Object":
                name = get_localized_text(obj_id, uuid_map, loc_map)
            
            elif obj_type == "Category":
                name = obj_id
                if obj_id in category_previews:
                    icon_val = category_previews[obj_id].get("Icon")
                    if icon_val: icon = f"{icon_val}_Icon.webp"
            
            elif obj_type == "Property":
                name = obj_id
                if obj_id in combo_props:
                    icon_val = combo_props[obj_id].get("data", {}).get("PreviewIcon")
                    if icon_val: icon = f"{icon_val}_Icon.webp"
            
            if name:
                row_text += f"\n| mat{i}_name = {name}"
            if icon:
                row_text += f"\n| mat{i}_icon = {icon}"

        if result_id:
            row_text += f"\n| res1 = {result_id}"
            res_name = get_localized_text(result_id, uuid_map, loc_map)
            if res_name:
                row_text += f"\n| res1_name = {res_name}"

        row_text += "\n}}"

        if is_creation:
            creation_rows.append(row_text)
        elif is_product:
            product_rows.append(row_text)
            
    def wrap_table(rows):
        if not rows: return None
        header = '{{CraftingTable/Header}}\n'
        body = '\n'.join(rows)
        footer = '\n{{CraftingTable/Footer}}'
        return header + body + footer

    return wrap_table(creation_rows), wrap_table(product_rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="item_wikitext")
    parser.add_argument("--refresh-loc", action="store_true")
    args = parser.parse_args()
    
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    loc_data = load_localization_data(all_files, conf, force_refresh=args.refresh_loc)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']
    
    recipe_proto_db = load_recipe_prototype_data(all_files, conf)

    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    
    weapon_stats_files = get_files_by_pattern(all_files, conf['patterns']['weapons'])
    armor_stats_files = get_files_by_pattern(all_files, conf['patterns']['armors'])
    all_stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])

    weapon_stats = {}
    for f in weapon_stats_files:
        weapon_stats.update(parse_stats_txt(f))
        
    armor_stats = {}
    for f in armor_stats_files:
        armor_stats.update(parse_stats_txt(f))
    
    all_stats = {}
    for f in all_stats_files:
        all_stats.update(parse_stats_txt(f))
    
    combos_files = get_files_by_pattern(all_files, conf['patterns']['item_combo_properties'])
    combos = {}
    for f in combos_files:
        combos.update(parse_item_combo_properties(f))

    resolved_armor_stats = resolve_all_stats(armor_stats)
    resolved_weapon_stats = resolve_all_stats(weapon_stats)
    resolved_all_stats = resolve_all_stats(all_stats)
    
    combo_prop_files = get_files_by_pattern(all_files, conf['patterns']['item_combo_properties'])
    combo_props = {}
    for f in combo_prop_files:
        combo_props.update(parse_item_combo_properties(f))

    cat_preview_files = get_files_by_pattern(all_files, conf['patterns']['object_categories_item_combos'])
    category_previews = {}
    for f in cat_preview_files:
        category_previews.update(parse_object_category_previews(f))

    item_combos_files = get_files_by_pattern(all_files, conf['patterns']['item_combos'])
    all_item_combos = {}
    for f in item_combos_files:
        all_item_combos.update(parse_item_combos(f))
    
    rt_raw_data = {}
    for f in merged_files:
        _, t = parse_lsj_templates(f)
        rt_raw_data.update(t)

    root_template_db = {} 
    
    for rt_uuid, rt_data in rt_raw_data.items():
        if rt_uuid == "ad65bf18-c9e9-4978-8e1e-488ef6a61f01":
            continue
        item_type = rt_data.get("Type")
        if isinstance(item_type, dict): item_type = item_type.get("value")
        if item_type != "item": continue

        name = resolve_node_name(rt_data, loc_map, uuid_map)
        
        desc = None
        desc_node = rt_data.get('Description')
        if isinstance(desc_node, dict) and 'handle' in desc_node:
            handle = desc_node['handle']
            if handle in loc_map:
                desc = loc_map[handle]
        
        stats_node = rt_data.get("Stats")
        stats_id = stats_node.get("value") if isinstance(stats_node, dict) else stats_node
        book_id = extract_book_id(rt_data)

        root_template_db[rt_uuid] = {
            "name": name,
            "stats_id": stats_id,
            "description": desc,
            "book_id": book_id,
            "raw_data": rt_data
        }

    template_loc_map, container_loc_map, unique_variants, all_regions = scan_levels_for_items(
        all_files, conf, root_template_db, loc_map, uuid_map
    )

    print("Aggregating Wiki Pages...")
    
    pages_to_write = defaultdict(lambda: {
        "name": None,
        "stats_id": None, 
        "description": None, 
        "locations": set(), 
        "root_template_uuid": None,
        "book_id": None,
        "properties": []
    })

    for rt_uuid, db_entry in root_template_db.items():
        name = db_entry["name"]
        if not name: continue

        safe_name = sanitize_filename(name)
        page_entry = pages_to_write[safe_name]
        
        page_entry["name"] = name
        page_entry["root_template_uuid"] = rt_uuid
        page_entry["stats_id"] = db_entry["stats_id"]
        page_entry["description"] = db_entry["description"]
        page_entry["book_id"] = db_entry["book_id"]
        
        if rt_uuid in template_loc_map:
            for loc in template_loc_map[rt_uuid]:
                page_entry["locations"].add((loc, rt_uuid))

        s_id = db_entry["stats_id"]
        if s_id and s_id in container_loc_map:
            for loc in container_loc_map[s_id]:
                page_entry["locations"].add((loc, None))
                
        stats = resolved_all_stats.get(s_id)
        if s_id:
            for prop_uuid, prop_info in combo_props.items():
                entries = prop_info.get("entries", [])
                for prop_entry in entries:
                    p_type = prop_entry.get("Type")
                    p_id = prop_entry.get("ObjectID")
                    if p_type == "Object" and p_id == s_id:
                        page_entry["properties"].append(prop_uuid)
                    if stats and p_type == "Category":
                        cats = stats.get("ComboCategory", "").split(";")
                        if p_id in cats:
                            page_entry["properties"].append(prop_uuid)

    for safe_name, var_data in unique_variants.items():
        page_entry = pages_to_write[safe_name]
        
        page_entry["name"] = var_data["name"]
        page_entry["root_template_uuid"] = var_data["root_template_uuid"]
        page_entry["stats_id"] = var_data["stats_id"]
        page_entry["book_id"] = var_data.get("book_id")
        
        if var_data["description"]:
            page_entry["description"] = var_data["description"]
        elif not page_entry["description"]:
             parent_uuid = var_data["root_template_uuid"]
             if parent_uuid in root_template_db:
                 page_entry["description"] = root_template_db[parent_uuid]["description"]

        u_uuid = var_data["root_template_uuid"]
        for loc in var_data["locations"]:
            page_entry["locations"].add((loc, u_uuid))

    print(f"Generating Wiki Pages for {len(pages_to_write)} unique items...")

    count = 0
    for safe_name, data in pages_to_write.items():
        real_name = data["name"] or safe_name
        stats_id = data["stats_id"] or "Unknown"
        description = data["description"]
        book_id = data["book_id"]
        page_header_uuid = data["root_template_uuid"] or ""
        properties = data.get("properties", [])
        
        item_categories = []
        if stats_id in resolved_all_stats:
            cat_str = resolved_all_stats[stats_id].get("ComboCategory", "")
            if cat_str:
                item_categories = [c.strip() for c in cat_str.split(",") if c.strip()]

        raw_locations = sorted(list(data["locations"]))
        grouped_locations = parse_and_group_locations(raw_locations)

        fname = f"{safe_name}.txt"
        path = os.path.join(args.outdir, fname)

        template = "InfoboxItem"
        if "Skillbook" in safe_name:
            template = "InfoboxSkillbook"
        elif stats_id in resolved_weapon_stats:
            template = "InfoboxWeapon"
        elif stats_id in resolved_armor_stats:
            template = "InfoboxArmour"
        
        content = f"{{{{{template}\n|name={real_name}\n|stats_id={stats_id}\n|root_template_uuid={page_header_uuid}"

        if description:
            safe_desc = description.replace('|', '{{!}}')
            content += f"\n|description={safe_desc}"
        
        if properties:
            props_str = ",".join(set(properties))
            content += f"\n|properties={props_str}"
        
        content += "\n}}\n"
        
        if book_id:
            if book_id in loc_map:
                book_text = loc_map[book_id]
            elif book_id in uuid_map:
                book_text = uuid_map[book_id]
            
            if isinstance(book_text, list):
                found_text = None
                for ref in book_text:
                    if isinstance(ref, dict) and "handle" in ref:
                        h = ref["handle"]
                        if h in loc_map:
                            val = loc_map[h]
                            if isinstance(val, str):
                                found_text = val
                                break
                book_text = found_text

            if book_text and isinstance(book_text, str):
                safe_bt = book_text.replace('|', '{{!}}')
                content += f"\n{{{{BookText|text={safe_bt}}}}}\n"
            
            if book_id in recipe_proto_db:
                recipes = recipe_proto_db[book_id]
                for r in recipes:
                    content += f"\n{{{{BookTeaches|recipe={r}}}}}\n"

        if grouped_locations:
            content += "\n== Locations ==\n"
            sorted_keys = sorted(grouped_locations.keys())
            
            for (region, loc_name, specific_uuid) in sorted_keys:
                coords_list = grouped_locations[(region, loc_name, specific_uuid)]
                coords_str = ";".join(coords_list)
                uuid_to_use = specific_uuid if specific_uuid else page_header_uuid
                content += f"{{{{ItemLocation|stats_id={stats_id}|root_template_uuid={uuid_to_use}|region={region}|location_name={loc_name}|coordinates={coords_str}}}}}\n"
            
            content += "\n{{ItemLocationTable}}\n"

        if stats_id and stats_id != "Unknown":
            creation_table, product_table = generate_crafting_wikitext(
                stats_id, item_categories, properties, all_item_combos, loc_map, uuid_map, resolved_all_stats, combo_props, category_previews
            )
            
            if creation_table:
                content += "\n== Crafting ==\n"
                content += creation_table + "\n"
            
            if product_table:
                if not creation_table:
                     content += "\n== Crafting ==\n"
                content += "\n=== Used in ===\n"
                content += product_table + "\n"

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        count += 1

if __name__ == "__main__":
    main()