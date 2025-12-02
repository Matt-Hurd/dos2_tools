import os
import argparse
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt, parse_lsj_templates
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.formatters import sanitize_filename

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
    
    stats_files = []
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['objects']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['potions']))
    
    raw_stats = {}
    for f in stats_files:
        raw_stats.update(parse_stats_txt(f))
        
    resolved = resolve_all_stats(raw_stats)

    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    
    template_data = {}
    for f in merged_files:
        _, t = parse_lsj_templates(f)
        template_data.update(t)
    
    count = 0
    seen_names = set()
    
    object_categories = set()

    for entry_id, data in resolved.items():
        if 'RootTemplate' not in data:
            continue
            
        name = get_localized_text(entry_id, uuid_map, loc_map)
        if not name: continue
        
        safe_name = sanitize_filename(name)
        
        if safe_name in seen_names: continue
        seen_names.add(safe_name)
        
        
        if 'ObjectCategory' in data:
            object_categories.add(data['ObjectCategory'])
        
        description = None
        rt_uuid = data.get('RootTemplate')
        
        if rt_uuid and rt_uuid in template_data:
            tmpl = template_data[rt_uuid]
            desc_node = tmpl.get('Description')
            if isinstance(desc_node, dict) and 'handle' in desc_node:
                handle = desc_node['handle']
                if handle in loc_map:
                    description = loc_map[handle]

        fname = f"{safe_name}.wikitext"
        path = os.path.join(args.outdir, fname)
        
        if "Skillbook" in safe_name:
            content = f"{{{{InfoboxSkillbook\n|stats_id={entry_id}"
        else:
            content = f"{{{{InfoboxItem\n|stats_id={entry_id}"
            
        if description:
            # Escape pipes in description to prevent breaking the template
            safe_desc = description.replace('|', '{{!}}')
            content += f"\n|Description={safe_desc}"
            
        content += "\n}}"
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        count += 1
        
    print(f"Generated {count} item pages.")
    
    for x in sorted(object_categories):
        print(f"- {x}")

if __name__ == "__main__":
    main()