import os
import argparse
import json
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.formatters import sanitize_filename

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

'''
example of openqable container to ignore
						"OnUsePeaceActions": [
							{
								"Action": [
									{
										"ActionType": {
											"type": 4,
											"value": 1
										},
										"Attributes": [
											{}
										]
									}
								]
							}
						],
'''

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
                if val == 1:  # 1 = Open Container
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-loc", action="store_true")
    args = parser.parse_args()

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    # 1. Load Localization
    print("Loading Localization...")
    loc_data = load_localization_data(all_files, conf, force_refresh=args.refresh_loc)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    # 2. Parse and Resolve Stats
    print("Parsing Stats files...")
    stats_files = []
    # Collect all relevant stat files (Objects, Potions, Stats generally)
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['objects']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['potions']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['stats']))

    raw_stats = {}
    for f in stats_files:
        raw_stats.update(parse_stats_txt(f))

    print(f"Resolving inheritance for {len(raw_stats)} stat entries...")
    stats_db = resolve_all_stats(raw_stats)

    # 3. Load RootTemplates
    print("Loading RootTemplates...")
    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    
    rt_raw_data = {}
    for f in merged_files:
        _, t = parse_lsj_templates(f)
        rt_raw_data.update(t)

    found_pages = set()

    print("Filtering items...")
    for rt_uuid, rt_data in rt_raw_data.items():
        # Filter for Items only
        item_type = rt_data.get("Type")
        if isinstance(item_type, dict): 
            item_type = item_type.get("value")
        
        if item_type != "item": 
            continue

        # Check 1: Must have an inventory list define
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
        
        # Skip bad DLC
        if stats_id.startswith("CON_Seed_") or stats_id.startswith("GRN_") or stats_id.startswith("TRP_Trap_"):
            continue

        stat_entry = stats_db.get(stats_id)
        if not stat_entry:
            continue

        if not is_openable_container(rt_data):
            # Check 2: Must have stats and Constitution > 0
            if isinstance(stats_node, dict):
                stats_id = stats_node.get("value")
            elif isinstance(stats_node, str):
                stats_id = stats_node

            # Skip containers
            if stats_id.startswith("CONT_"):
                continue
            
            # Check Constitution (default is usually -1 or 0 for indestructible)
            constitution = stat_entry.get("Constitution", 0)
            try:
                constitution = int(constitution)
            except (ValueError, TypeError):
                constitution = 0

            if constitution <= 0:
                continue
            
            # Check Vitality (must not be -1)
            vitality = stat_entry.get("Vitality", 0)
            try:
                vitality = int(vitality)
            except (ValueError, TypeError):
                vitality = 0

            if vitality == -1:
                continue
            
            # if stat_entry.get("ObjectCategory") == "Painting":
            #     continue

        # If we pass all checks, resolve name and add
        name = resolve_node_name(rt_data, loc_map, uuid_map)
        if name:
            safe_name = sanitize_filename(name)
            print(  f"Found item: {safe_name} (RT: {rt_uuid}, Stats: {stats_id}, ObjectCategory: {stat_entry.get('ObjectCategory')})")
            # print(stat_entry.get("Weight"), stat_entry.get("Value"))
            found_pages.add(safe_name)

    print(f"Found {len(found_pages)} items.")
    # for page in sorted(found_pages):
    #     print(page)

if __name__ == "__main__":
    main()