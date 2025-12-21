import os
import argparse
import json
from collections import defaultdict
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.formatters import sanitize_filename

'''
Current Issue: Certain instances may overwrite OnPeaceUseAction to become inoperable, but all of them get detected.
'''

def get_region_name(file_path):
    parts = file_path.replace('\\', '/').split('/')
    if "Levels" in parts:
        return parts[parts.index("Levels")+1]
    if "Globals" in parts:
        return parts[parts.index("Globals")+1]
    return "Unknown"

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

def is_openable_container(node_data):
    on_use_actions = node_data.get("OnUsePeaceActions")
    if not on_use_actions or not isinstance(on_use_actions, list):
        return False
        
    for action_entry in on_use_actions:
        actions = action_entry.get("Action")
        if not actions:
            continue
            
        if not isinstance(actions, list):
            actions = [actions]
            
        for action in actions:
            action_type = action.get("ActionType", {})
            if isinstance(action_type, dict):
                val = action_type.get("value")
                if val == 1: 
                    return True
    return False

def has_valid_inventory(inventory_node):
    if not inventory_node or not isinstance(inventory_node, list):
        return False
        
    for node in inventory_node:
        invs = node.get("Inventorys")
        if not invs:
            continue
            
        if not isinstance(invs, list):
            invs = [invs]
            
        for inv_entry in invs:
            item_val = inv_entry.get("InventoryItem")
            if isinstance(item_val, dict):
                val_str = item_val.get("value")
                if val_str:
                    return True
    return False

def scan_levels_for_specific_uuids(all_files, conf, valid_uuids):
    region_uuid_map = defaultdict(set)
    level_files = get_files_by_pattern(all_files, conf['patterns']['level_items'])
    
    print(f"Scanning {len(level_files)} level files for occurrences...")
    
    for f_path in level_files:
        if 'Test' in f_path or 'Develop' in f_path or "GM_" in f_path or "Arena" in f_path: 
            continue
            
        region = get_region_name(f_path)
        _, level_objects = parse_lsj_templates(f_path)
        
        for obj in level_objects.values():
            template_uuid = obj.get("TemplateName")
            if template_uuid in valid_uuids:
                region_uuid_map[region].add(template_uuid)
                
    return region_uuid_map

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-loc", action="store_true")
    parser.add_argument("--output", default="LuckyCharm_Map.wikitext")
    args = parser.parse_args()

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Localization...")
    loc_data = load_localization_data(all_files, conf, force_refresh=args.refresh_loc)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    print("Parsing Stats files...")
    stats_files = []
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['objects']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['potions']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['stats']))

    raw_stats = {}
    for f in stats_files:
        raw_stats.update(parse_stats_txt(f))

    print(f"Resolving inheritance for {len(raw_stats)} stat entries...")
    stats_db = resolve_all_stats(raw_stats)

    print("Loading RootTemplates...")
    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    
    rt_raw_data = {}
    for f in merged_files:
        _, t = parse_lsj_templates(f)
        rt_raw_data.update(t)

    valid_uuids = set()

    print("Filtering items...")
    for rt_uuid, rt_data in rt_raw_data.items():
        item_type = rt_data.get("Type")
        if isinstance(item_type, dict): 
            item_type = item_type.get("value")
        
        if item_type != "item": 
            continue

        inventory_node = rt_data.get("InventoryList")
        if not has_valid_inventory(inventory_node):
            continue

        stats_node = rt_data.get("Stats")
        stats_id = None
        if isinstance(stats_node, dict):
            stats_id = stats_node.get("value")
        elif isinstance(stats_node, str):
            stats_id = stats_node

        if not stats_id or stats_id == "None":
            continue
        
        if stats_id.startswith("CON_Seed_") or stats_id.startswith("GRN_") or stats_id.startswith("TRP_Trap_"):
            continue

        stat_entry = stats_db.get(stats_id)
        if not stat_entry:
            continue

        if not is_openable_container(rt_data):
            if isinstance(stats_node, dict):
                stats_id = stats_node.get("value")
            elif isinstance(stats_node, str):
                stats_id = stats_node

            if stats_id.startswith("CONT_"):
                continue
            
            constitution = stat_entry.get("Constitution", 0)
            try:
                constitution = int(constitution)
            except (ValueError, TypeError):
                constitution = 0

            if constitution <= 0:
                continue
            
            vitality = stat_entry.get("Vitality", 0)
            try:
                vitality = int(vitality)
            except (ValueError, TypeError):
                vitality = 0

            if vitality == -1:
                continue
            
        valid_uuids.add(rt_uuid)

    print(f"Identified {len(valid_uuids)} potential Lucky Charm container types.")

    region_map = scan_levels_for_specific_uuids(all_files, conf, valid_uuids)

    regions_to_output = [
        "FJ_FortJoy_Main", 
        "RC_Main", 
        "CoS_Main", 
        "Arx_Main"
    ]
    
    output_content = "__NOTOC__\n= Lucky Charm Item Map =\n"
    output_content += "This map displays all openable containers and destructibles found by the script.\n"

    for region in regions_to_output:
        uuids_in_region = region_map.get(region, set())
        
        if not uuids_in_region:
            print(f"Warning: No matching containers found in {region}")
            continue

        uuid_string = ",".join(sorted(list(uuids_in_region)))
        
        output_content += f"\n== {region} ==\n"
        output_content += f"{{{{ItemRegionMap|region={region}|uuids={uuid_string}}}}}\n"

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(output_content)
    
    print(f"Wrote wikitext to {args.output}")

if __name__ == "__main__":
    main()