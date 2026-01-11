import os
import sys
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt, parse_lsj_templates
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.formatters import to_lua_table

def main():
    conf = get_config()
    
    print("Resolving file load order...")
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Skill*.txt...")
    stats_files = []
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['skills']))
    
    raw_stats = {}
    for f in stats_files:
        raw_stats.update(parse_stats_txt(f))
        
    print(f"Resolving inheritance for {len(raw_stats)} entries...")
    resolved_stats = resolve_all_stats(raw_stats)
    
    print("Loading RootTemplates to find Skills...")
    template_files = get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj'])
    template_files.extend(get_files_by_pattern(all_files, conf['patterns']['merged_lsj']))
    
    root_templates_by_guid = {}
    
    total_tmpl = len(template_files)
    for idx, f in enumerate(template_files):
        print(f"Parsing templates {idx+1}/{total_tmpl}...", end='\r')
        _, by_map_key = parse_lsj_templates(f)
        root_templates_by_guid.update(by_map_key)
    print("\nTemplates loaded.")

    print("Mapping RootTemplate data to Stats...")
    final_lua_data = {}
    
    for entry_id, data in resolved_stats.items():
        final_lua_data[entry_id] = data

    print(f"Generating Lua module for {len(final_lua_data)} items...")
    
    lua_str = to_lua_table(final_lua_data)
    output_content = "return " + lua_str
    
    output_path = "Module_Skills.lua"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_content)
        
    print(f"Success. Written to {output_path}")

if __name__ == "__main__":
    main()