import os
import json
from collections import defaultdict
from dos2_tools.core.config import UUID_BLACKLIST
from dos2_tools.core.parsers import parse_lsj, parse_xml_localization
from dos2_tools.core.file_system import get_files_by_pattern

CACHE_FILE = "cache_localization.json"

def scan_lsj_for_uuids(files):
    uuid_map = defaultdict(list)
    
    count = 0
    total = len(files)

    for file_path in files:
        count += 1
        if count % 100 == 0: print(f"  Scanning LSJ {count}/{total}...", end='\r')

        data = parse_lsj(file_path)
        if not data: continue
        
        nodes = data.get('save', {}).get('regions', {}).get('TranslatedStringKeys', {}).get('TranslatedStringKey', [])
        if not isinstance(nodes, list): nodes = [nodes]

        for node in nodes:
            uuid_val = node.get('UUID', {}).get('value')
            if not uuid_val or uuid_val in UUID_BLACKLIST:
                continue
            
            handle_val = node.get('Content', {}).get('handle')
            if handle_val:
                uuid_map[uuid_val].append({
                    'file': file_path,
                    'handle': handle_val
                })
    print(f"  Scanning LSJ Complete.            ")
    return dict(uuid_map)

def load_localization_data(all_files, config, force_refresh=False):
    if not force_refresh and os.path.exists(CACHE_FILE):
        print(f"Loading localization from {CACHE_FILE}...")
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Cache corrupted, rebuilding...")

    print("Building localization cache...")
    
    xml_files = get_files_by_pattern(all_files, config['patterns']['localization_xml'])
    loc_map = {}
    for f in xml_files: loc_map.update(parse_xml_localization(f))
    
    uuid_map = scan_lsj_for_uuids(all_files)
    
    data = {
        "handles": loc_map,
        "uuids": uuid_map
    }

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
        
    return data

def get_single_handle(uuid_val, uuid_map):
    entries = uuid_map.get(uuid_val)
    if not entries: return None
    # If loading from JSON cache, 'entries' is a list. If defaultdict, it's a list.
    # Sort by file length/name to ensure deterministic behavior
    entries.sort(key=lambda x: x['file'])
    return entries[0]['handle']

def get_localized_text(key, uuid_map, handle_map):
    if not key: return None
    key = key.replace(';', '')
    
    if key in handle_map:
        return handle_map[key]
    
    if key in uuid_map:
        handle = get_single_handle(key, uuid_map)
        if handle and handle in handle_map:
            return handle_map[handle]
            
    return None