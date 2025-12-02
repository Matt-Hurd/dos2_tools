import os
import json
from collections import defaultdict
from copy import deepcopy
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_xml_localization
from dos2_tools.core.localization import load_localization_data, get_localized_text

# Fields that are expected to be unique per instance and should be ignored during comparison
IGNORED_FIELDS = {
    "MapKey", "GlobalMapKey", "Transform", "PerceptionDirection", 
    "dwarf", "OriginalFileVersion", "_OriginalFileVersion_", 
    "LayerList", "GroupID", "VisualSet",
}

def get_flat_keys(data, prefix=""):
    """
    Recursively flattens a nested dictionary to dot-notation keys for comparison.
    Returns: { "Stats.value": "Human_Commoner", "Tags[0].value": "..." }
    """
    items = {}
    
    if isinstance(data, dict):
        for k, v in data.items():
            if k in IGNORED_FIELDS:
                continue
            
            # Handle standard LSJ value/handle pairs (simplify to just the value/text)
            if isinstance(v, dict) and 'value' in v and 'type' in v:
                items[f"{prefix}{k}"] = v['value']
            elif isinstance(v, (dict, list)):
                items.update(get_flat_keys(v, f"{prefix}{k}."))
            else:
                items[f"{prefix}{k}"] = v
                
    elif isinstance(data, list):
        for i, v in enumerate(data):
            # For lists of objects (like Scripts), we try to verify content, 
            # but order often matters in lists, so index-based comparison is usually fine.
            if isinstance(v, (dict, list)):
                items.update(get_flat_keys(v, f"{prefix}[{i}]."))
            else:
                items[f"{prefix}[{i}]"] = v
                
    return items

def analyze_variance(instances):
    """
    Compares a list of NPC objects.
    Returns a dict of keys that have more than 1 unique value across the set.
    """
    if not instances: return {}
    
    # Key -> Set of all values seen for this key
    value_registry = defaultdict(set)
    
    for npc in instances:
        flat_data = get_flat_keys(npc)
        for k, v in flat_data.items():
            # Convert list/dicts to string for hashing/set storage
            if isinstance(v, (dict, list)):
                v = json.dumps(v, sort_keys=True)
            value_registry[k].add(str(v))
            
    # Filter to only keys with variance
    variance_report = {}
    for key, values in value_registry.items():
        if len(values) > 1:
            variance_report[key] = list(values)
            
    return variance_report

def main():
    # --- CONFIGURATION ---
    TARGET_NAME = "Malady" # Set to None to scan EVERYTHING (warning: huge output)
    MIN_VARIANCE_COUNT = 0 # Only show variance if more than X fields differ
    # ---------------------

    print("Starting Deep Variance Audit...")
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    loc_data = load_localization_data(all_files, conf)
    
    # Unpack localization
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    print("Loading Templates...")
    template_files = get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj'])
    template_files.extend(get_files_by_pattern(all_files, ["Public/**/RootTemplates/_merged.lsj"]))
    
    root_templates = {}
    for f in template_files:
        _, by_map_key = parse_lsj_templates(f)
        root_templates.update(by_map_key)

    print("Loading Characters...")
    char_files = get_files_by_pattern(all_files, conf['patterns']['level_characters'])
    
    # Group full data objects by Name
    grouped_npcs = defaultdict(list)
    
    for f_path in char_files:
        if 'Test' in f_path or 'Develop' in f_path:
            continue
        _, level_objects = parse_lsj_templates(f_path)
        
        parts = f_path.replace('\\', '/').split('/')
        level_name = parts[parts.index("Levels")+1] if "Levels" in parts else "Unknown"

        for obj_uuid, level_data in level_objects.items():
            template_uuid = level_data.get("TemplateName", {}).get("value")
            
            # Merge Root + Level Data
            final_data = {}
            if template_uuid and template_uuid in root_templates:
                final_data = deepcopy(root_templates[template_uuid])
            final_data.update(level_data)

            # Resolve Name
            display_name_node = final_data.get("DisplayName")
            final_name = "Unknown"
            if display_name_node:
                handle = display_name_node.get("handle")
                if handle: final_name = loc_map.get(handle)
                if not final_name or final_name == "Unknown":
                    val = display_name_node.get("value")
                    if val:
                        loc_val = get_localized_text(val, uuid_map, loc_map)
                        final_name = loc_val if loc_val else val

            if not final_name: final_name = "Unknown"
            
            # Store metadata for context in the report
            final_data['_DEBUG_LEVEL'] = level_name
            final_data['_DEBUG_SOURCE'] = os.path.basename(f_path)
            
            grouped_npcs[final_name].append(final_data)

    print(f"Loaded {sum(len(v) for v in grouped_npcs.values())} NPC instances across {len(grouped_npcs)} unique names.")

    print("-" * 60)
    
    # Filter targets
    targets_to_scan = grouped_npcs.items()
    if TARGET_NAME:
        targets_to_scan = [(TARGET_NAME, grouped_npcs.get(TARGET_NAME, []))]

    for name, instances in targets_to_scan:
        if not instances:
            print(f"No instances found for '{name}'")
            continue
            
        count = len(instances)
        if count < 2:
            if not TARGET_NAME: continue # Skip singletons if doing a bulk scan
            print(f"'{name}': Only 1 instance found. Nothing to compare.")
            continue

        variance = analyze_variance(instances)
        
        if len(variance) <= MIN_VARIANCE_COUNT:
            if TARGET_NAME: print(f"'{name}': No significant variance found across {count} instances.")
            continue

        print(f"\nNAME: {name} ({count} instances)")
        print(f"VARIANCE DETECTED IN {len(variance)} FIELDS:")
        
        for field, values in variance.items():
            # If the value list is huge, truncate it
            display_values = values
            if len(values) > 5:
                display_values = values[:5] + [f"... and {len(values)-5} more"]
            
            print(f"  > {field}")
            for v in display_values:
                print(f"      - {v}")
                
        # Optional: Print where these instances are coming from
        levels = set(i.get('_DEBUG_LEVEL') for i in instances)
        print(f"  Found in levels: {', '.join(sorted(levels))}")

if __name__ == "__main__":
    main()