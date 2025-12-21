import os
import argparse
from collections import defaultdict
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates
from dos2_tools.core.localization import load_localization_data, get_localized_text

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

def get_node_value(node_data, key):
    val_node = node_data.get(key)
    if isinstance(val_node, dict):
        return val_node.get("value")
    return val_node

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="wiki_redirects")
    parser.add_argument("--refresh-loc", action="store_true")
    args = parser.parse_args()
    
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Localization Data...")
    loc_data = load_localization_data(all_files, conf, force_refresh=args.refresh_loc)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    print("Loading RootTemplates...")
    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    
    rt_raw_data = {}
    for f in merged_files:
        _, t = parse_lsj_templates(f)
        rt_raw_data.update(t)

    seen_redirects = {}
    count = 0

    print("Processing items and generating redirects...")

    for rt_uuid, rt_data in rt_raw_data.items():
        item_type = get_node_value(rt_data, "Type")
        if item_type != "item": continue

        display_name = resolve_node_name(rt_data, loc_map, uuid_map)
        if not display_name: continue

        icon_name = get_node_value(rt_data, "Icon")
        if not icon_name: continue

        clean_display_name = display_name.replace(' ', '_')
        clean_icon = icon_name.replace(' ', '_')

        if not clean_display_name or not clean_icon: continue
        if "|" in clean_display_name or "|" in clean_icon:
            print(f"Skipping invalid names: '{clean_display_name}' or '{clean_icon}'")
            continue

        source_filename = f"{clean_display_name}_Icon.webp"
        target_filename = f"{clean_icon}_Icon.webp"

        if source_filename == target_filename:
            continue

        if source_filename in seen_redirects:
            existing_target = seen_redirects[source_filename]
            if existing_target != target_filename:
                pass 
        else:
            seen_redirects[source_filename] = target_filename
            
            file_path = os.path.join(args.outdir, f"{source_filename}.wikitext")
            with open(file_path, 'w', encoding='utf-8') as out:
                out.write(f"#REDIRECT [[File:{target_filename}]]")
            count += 1

    print(f"Done. Generated {count} redirect files.")

if __name__ == "__main__":
    main()