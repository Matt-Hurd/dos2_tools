import json
import argparse
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_xml_localization
from dos2_tools.core.localization import scan_lsj_for_uuids, get_single_handle
from dos2_tools.core.formatters import to_lua_table, sanitize_lua_string

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["json", "lua"], default="json")
    parser.add_argument("--output", default="UUID_Localization")
    args = parser.parse_args()

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    xml_files = get_files_by_pattern(all_files, conf['patterns']['localization_xml'])
    loc_map = {}
    for xf in xml_files:
        loc_map.update(parse_xml_localization(xf))
        
    uuid_map = scan_lsj_for_uuids(all_files)
    
    final_output = {}
    for uuid in uuid_map:
        handle = get_single_handle(uuid, uuid_map)
        text = loc_map.get(handle, "MISSING_LOCALIZATION")
        final_output[uuid] = text

    if args.format == "json":
        fname = f"{args.output}.json"
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, indent=4, sort_keys=True)
    else:
        fname = f"{args.output}.lua"
        # Optimize for Lua map format instead of generic table
        with open(fname, 'w', encoding='utf-8') as f:
            f.write("return {\n")
            for u, t in sorted(final_output.items()):
                f.write(f'    ["{u}"] = "{sanitize_lua_string(t)}",\n')
            f.write("}\n")

    print(f"Exported {len(final_output)} keys to {fname}")

if __name__ == "__main__":
    main()