import os
import argparse
import re
from collections import defaultdict
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt, parse_lsj_templates
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.formatters import sanitize_filename

def parse_and_group_locations(location_strings):
    grouped = defaultdict(list)
    
    pattern = re.compile(r"([-\d\.,]+)\s*\(([^)]+)\)(?:\s*inside\s*(.+))?")

    for loc_str in location_strings:
        match = pattern.search(loc_str)
        if match:
            coords = match.group(1)
            region = match.group(2)
            container = match.group(3)

            if container:
                loc_name = f"{container}"
            else:
                loc_name = "Ground Spawn"

            key = (region, loc_name)
            grouped[key].append(coords)
        else:
            grouped[("Unknown", "Unknown")].append(loc_str)
            
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

def build_location_map(all_files, conf):
    print("Building world location map (this may take a moment)...")
    
    template_locs = defaultdict(list)
    
    container_locs = defaultdict(list)
    
    level_files = get_files_by_pattern(all_files, conf['patterns']['level_items'])
    
    for f_path in level_files:
        if 'Test' in f_path or 'Develop' in f_path or "GM_" in f_path or "Arena" in f_path or "_TMPL_Sandbox" in f_path: continue
        
        region = get_region_name(f_path)
        _, level_objects = parse_lsj_templates(f_path)
        
        for map_key, obj_data in level_objects.items():
            
            coords = format_coordinate(obj_data.get("Transform"))
            if not coords: continue
            
            full_loc_str = f"{coords} ({region})"
            
            template_uuid = obj_data.get("TemplateName", "")
            if template_uuid:
                template_locs[template_uuid].append(full_loc_str)
            
            item_list_root = obj_data.get("ItemList", [])
            if not item_list_root: continue
            
            container_name = obj_data.get("Name", {}).get("value", "Container")
            
            for item_entry in item_list_root:
                items = item_entry.get("Item", [])
                if not isinstance(items, list): items = [items]
                
                for item in items:
                    stats_id = item.get("ItemName", {}).get("value")
                    
                    if stats_id:
                        loc_desc = f"{full_loc_str} inside {container_name}"
                        container_locs[stats_id].append(loc_desc)

    print(f"Mapped {len(template_locs)} template locations and {len(container_locs)} container drops.")
    return template_locs, container_locs

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
    
    template_loc_map, container_loc_map = build_location_map(all_files, conf)
    
    stats_files = []
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['objects']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['potions']))
    
    raw_stats = {}
    for f in stats_files:
        raw_stats.update(parse_stats_txt(f))
    resolved_stats = resolve_all_stats(raw_stats)

    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    template_desc_data = {}
    for f in merged_files:
        _, t = parse_lsj_templates(f)
        template_desc_data.update(t)        
    
    print("Aggregating Item Data by RootTemplate...")

    pages_to_write = defaultdict(lambda: {
        "stats_id": None, 
        "description": None, 
        "locations": set(),
        "root_template_uuid": None
    })

    for rt_uuid, rt_data in template_desc_data.items():
        item_type = rt_data.get("Type")
        if isinstance(item_type, dict): item_type = item_type.get("value")
        
        if item_type != "item": 
            continue

        stats_id_node = rt_data.get("Stats")
        stats_id = None
        if isinstance(stats_id_node, dict):
            stats_id = stats_id_node.get("value")
        elif isinstance(stats_id_node, str):
            stats_id = stats_id_node

        name = None
        display_node = rt_data.get("DisplayName")
        if display_node and isinstance(display_node, dict):
            handle = display_node.get("handle")
            if handle in loc_map:
                name = loc_map[handle]
        
        if not name and stats_id:
             name = get_localized_text(stats_id, uuid_map, loc_map)

        if not name: 
            continue

        safe_name = sanitize_filename(name)
        page_entry = pages_to_write[safe_name]

        page_entry["root_template_uuid"] = rt_uuid

        if not page_entry["stats_id"] and stats_id and stats_id != "None":
            page_entry["stats_id"] = stats_id
            
        if not page_entry["description"]:
            desc_node = rt_data.get('Description')
            if isinstance(desc_node, dict) and 'handle' in desc_node:
                handle = desc_node['handle']
                if handle in loc_map:
                    page_entry["description"] = loc_map[handle]

        if rt_uuid in template_loc_map:
            page_entry["locations"].update(template_loc_map[rt_uuid])

        if stats_id and stats_id in container_loc_map:
            page_entry["locations"].update(container_loc_map[stats_id])

    print(f"Generating Wiki Pages for {len(pages_to_write)} unique items...")

    count = 0
    for safe_name, data in pages_to_write.items():
        stats_id = data["stats_id"] or "Unknown"
        description = data["description"]

        raw_locations = sorted(list(data["locations"]))
        grouped_locations = parse_and_group_locations(raw_locations)

        fname = f"{safe_name}.wikitext"
        path = os.path.join(args.outdir, fname)

        if "Skillbook" in safe_name:
            content = f"{{{{InfoboxSkillbook\n|stats_id={stats_id}\n|root_template_uuid={data['root_template_uuid']}"
        else:
            content = f"{{{{InfoboxItem\n|stats_id={stats_id}\n|root_template_uuid={data['root_template_uuid']}"
            
        if description:
            safe_desc = description.replace('|', '{{!}}')
            content += f"\n|description={safe_desc}"
        
        content += "\n}}\n"
        
        if grouped_locations:
            content += "\n== Locations ==\n"
            sorted_keys = sorted(grouped_locations.keys())
            
            for (region, loc_name) in sorted_keys:
                coords_list = grouped_locations[(region, loc_name)]
                coords_str = ";".join(coords_list)
                content += f"{{{{ItemLocation|stats_id={stats_id}|region={region}|location_name={loc_name}|coordinates={coords_str}}}}}\n"
            
            content += "\n{{LocationTable|table=Items}}\n"
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        count += 1
        
    print(f"Done. Wrote {count} files.")

if __name__ == "__main__":
    main()