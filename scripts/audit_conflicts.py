from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order
from dos2_tools.core.localization import scan_lsj_for_uuids

def main():
    conf = get_config()
    files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Scanning UUIDs...")
    uuid_data = scan_lsj_for_uuids(files)
    
    conflicts = []
    safe_dupes = []

    for uuid, entries in uuid_data.items():
        if len(entries) > 1:
            first = entries[0]['handle']
            is_conflict = False
            for e in entries[1:]:
                if e['handle'] != first:
                    is_conflict = True
                    break
            if is_conflict:
                conflicts.append((uuid, entries))
            else:
                safe_dupes.append((uuid, entries))

    print(f"Total Unique UUIDs: {len(uuid_data)}")
    print(f"Safe Duplicates:    {len(safe_dupes)}")
    print(f"CONFLICTS:          {len(conflicts)}")

    if conflicts:
        print("\n!!! ACTIVE CONFLICTS DETECTED !!!")
        for uuid, entries in conflicts:
            print(f"\nUUID: {uuid}")
            for e in entries:
                print(f"  - File: {e['file']}\n    Handle: {e['handle']}")
    else:
        print("\nClean scan.")

if __name__ == "__main__":
    main()