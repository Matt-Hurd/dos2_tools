import sys
import re
from collections import OrderedDict
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats

def _convert_type(value):
    if not isinstance(value, str):
        return value

    # Check for integer (including negative)
    if re.match(r"^-?\d+$", value):
        return int(value)
    
    val_lower = value.lower()
    if val_lower == 'true' or val_lower == 'yes':
        return True
    if val_lower == 'false' or val_lower == 'no':
        return False
        
    try:
        return float(value)
    except ValueError:
        pass
        
    # Handle quoted strings if they still exist
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
         return value[1:-1].replace('\\"', '"')
         
    return value.replace('"', '\\"')

def _to_lua_value(value, indent_level):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        lua_str = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{lua_str}"'
    if isinstance(value, (OrderedDict, dict)):
        return _to_lua_table(value, indent_level + 1)
    if isinstance(value, list):
        return _to_lua_list(value, indent_level + 1)
    if value is None:
        return "nil"
    
    lua_str = str(value).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{lua_str}"'

def _to_lua_table(data, indent_level=1):
    base_indent = '\t' * indent_level
    entry_indent = '\t' * (indent_level + 1)
    parts = []

    for key, value in data.items():
        # skip internal keys if any exist (starting with _)
        if str(key).startswith("_") and key != "_type": 
            continue
            
        lua_key = f'["{key}"]' if not re.match(r'^[a-zA-Z_]\w*$', str(key)) else str(key)
        lua_value = _to_lua_value(value, indent_level)
        parts.append(f'{entry_indent}{lua_key} = {lua_value},')
    
    if not parts:
        return "{}"
        
    return "{\n" + "\n".join(parts) + "\n" + base_indent + "}"

def _to_lua_list(data, indent_level=1):
    base_indent = '\t' * indent_level
    entry_indent = '\t' * (indent_level + 1)
    parts = []

    for item in data:
        lua_value = _to_lua_value(item, indent_level)
        parts.append(f'{entry_indent}{lua_value},')
    
    if not parts:
        return "{}"
        
    return "{\n" + "\n".join(parts) + "\n" + base_indent + "}"

def main():
    try:
        conf = get_config()
        all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
        
        armor_files = get_files_by_pattern(all_files, conf['patterns']['armors']) + get_files_by_pattern(all_files, conf['patterns']['shields'])
        
        print(f"Found {len(armor_files)} armor files. Parsing...")

        raw_stats = {}
        for filepath in armor_files:
            try:
                # dos2_tools returns dict of dicts with string values
                file_entries = parse_stats_txt(filepath)
                raw_stats.update(file_entries)
            except Exception as e:
                print(f"Error parsing file {filepath}: {e}", file=sys.stderr)

        print(f"Parsed {len(raw_stats)} total unique entries. Resolving inheritance...")
        
        resolved_stats = resolve_all_stats(raw_stats)
        
        print(f"Successfully resolved {len(resolved_stats)} entries.")

        final_data_typed = {}

        # 1. Convert types and store in OrderedDict
        for entry_id, data in resolved_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                typed_entry[key] = _convert_type(value)
            final_data_typed[entry_id] = typed_entry

        # 2. Resolve Boosts linking
        final_data_export = {}
        for entry_id, data in final_data_typed.items():
            if "Boosts" in data and isinstance(data["Boosts"], str):
                boost_keys_str = data["Boosts"]
                boost_keys = [key.strip() for key in boost_keys_str.split(';') if key.strip()]
                
                resolved_boosts_list = []
                for boost_key in boost_keys:
                    if boost_key in final_data_typed:
                        resolved_boosts_list.append(final_data_typed[boost_key])
                
                data["Boosts"] = resolved_boosts_list
            
            final_data_export[entry_id] = data

        lua_table_string = _to_lua_table(final_data_export)
        final_lua_module = "return " + lua_table_string
        
        output_filepath = "Module_ArmourData.lua"
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(final_lua_module)
            
        print(f"Successfully wrote Lua module to {output_filepath}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()