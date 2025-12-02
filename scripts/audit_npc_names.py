import os
from collections import defaultdict
from copy import deepcopy
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_xml_localization
from dos2_tools.core.localization import load_localization_data, get_localized_text

def main():
    print("Starting NPC Name Audit...")

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])

    loc_data = load_localization_data(all_files, conf)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    print("Loading Root Templates...")
    template_files = get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj'])
    template_files.extend(get_files_by_pattern(all_files, ["Public/**/RootTemplates/_merged.lsj"]))
    
    root_templates = {}
    for f in template_files:
        _, by_map_key = parse_lsj_templates(f)
        root_templates.update(by_map_key)
        
    print("Scanning Level Characters...")
    char_files = get_files_by_pattern(all_files, conf['patterns']['level_characters'])
    
    # name -> list of dicts with metadata
    name_registry = defaultdict(list)
    total_processed = 0

    for f_path in char_files:
        if 'Test' in f_path or 'Develop' in f_path:
            continue
        _, level_objects = parse_lsj_templates(f_path)
        
        parts = f_path.replace('\\', '/').split('/')
        level_name = "Unknown"
        if "Levels" in parts:
            idx = parts.index("Levels")
            if idx + 1 < len(parts):
                level_name = parts[idx + 1]

        for obj_uuid, level_data in level_objects.items():
            total_processed += 1
            template_uuid = level_data.get("TemplateName", {}).get("value")
            
            final_data = {}
            if template_uuid and template_uuid in root_templates:
                final_data = deepcopy(root_templates[template_uuid])
            
            final_data.update(level_data)

            # Resolve Name
            display_name_node = final_data.get("DisplayName")
            final_name = "Unknown"

            if display_name_node:
                handle = display_name_node.get("handle")
                if handle:
                    final_name = loc_map.get(handle)
                
                if not final_name or final_name == "Unknown":
                    val = display_name_node.get("value")
                    if val:
                        loc_val = get_localized_text(val, uuid_map, loc_map)
                        final_name = loc_val if loc_val else val

            if not final_name:
                final_name = "Unknown"

            unique_uuid = final_data.get("MapKey", {}).get("value")
            internal_name_node = final_data.get("Name", {})
            internal_name = internal_name_node.get("value", "Unknown") if isinstance(internal_name_node, dict) else "Unknown"

            name_registry[final_name].append({
                "guid": unique_uuid,
                "internal": internal_name,
                "level": level_name
            })

    print(f"\nProcessed {total_processed} total entities.")
    print("-" * 60)
    print(f"{'COUNT':<8} | {'NAME'}")
    print("-" * 60)

    # Sort by frequency (descending)
    sorted_registry = sorted(name_registry.items(), key=lambda item: len(item[1]), reverse=True)

    for name, entries in sorted_registry:
        count = len(entries)
        # Optional: Filter out singletons to reduce noise
        if count > 1: 
            print(f"{count:<8} | {name}")
            
    targets = ["Shark", "Conway Pryce", "Pilgrim"]
    print("\n--- Detailed Breakdown for Targets ---")
    for target in targets:
        if target in name_registry:
            print(f"\nTarget: {target} (Total: {len(name_registry[target])})")
            for entry in name_registry[target]: # Show first 5 examples
                print(f"  - GUID: {entry['guid']} | Level: {entry['level']} | Internal: {entry['internal']}")

if __name__ == "__main__":
    main()