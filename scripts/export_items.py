import json
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import (
    parse_stats_txt, parse_lsj, parse_xml_localization,
    parse_item_progression_names, parse_item_progression_visuals, parse_lsj_templates
)
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.data_models import Item

def main():
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    loc_files = get_files_by_pattern(all_files, conf['patterns']['localization_xml'])
    loc_map = {}
    for f in loc_files: loc_map.update(parse_xml_localization(f))
    
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_stats = {}
    for f in stats_files: raw_stats.update(parse_stats_txt(f))
    
    final_stats = resolve_all_stats(raw_stats)
    unique_stats = {k: v for k, v in final_stats.items() if v.get("Unique") == "1"}
    
    prog_name_files = get_files_by_pattern(all_files, conf['patterns']['item_prog_names'])
    prog_names = {}
    for f in prog_name_files: prog_names.update(parse_item_progression_names(f))
    
    prog_vis_files = get_files_by_pattern(all_files, conf['patterns']['item_prog_visuals'])
    prog_visuals = {}
    for f in prog_vis_files: prog_visuals.update(parse_item_progression_visuals(f))

    prog_lsj_files = get_files_by_pattern(all_files, conf['patterns']['item_prog_lsj'])
    prog_keys = []
    for f in prog_lsj_files:
        data = parse_lsj(f)
        if data:
            keys = data.get("save", {}).get("regions", {}).get("TranslatedStringKeys", {}).get("TranslatedStringKey", [])
            prog_keys.extend(keys)

    merged_files = get_files_by_pattern(all_files, conf['patterns']['merged_lsj'])
    merged_files.extend(get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj']))
    
    merged_data = {}
    template_data = {}
    for f in merged_files:
        m, t = parse_lsj_templates(f)
        merged_data.update(m)
        template_data.update(t)

    items = {}
    
    for stats_id, stats in unique_stats.items():
        item = Item(stats_id=stats_id, stats=stats)
        item_group = stats.get("ItemGroup")
        
        # Gift Bag Pattern
        if item_group in prog_names:
            raw_name = prog_names[item_group].get('name')
            if raw_name:
                for key in prog_keys:
                    if key.get("UUID", {}).get("value") == raw_name:
                        h = key.get("Content", {}).get("handle")
                        item.display_name = loc_map.get(h)
                        item.description = prog_names[item_group].get('description')
                        item.link_method = "GiftBag"
                        break

        # Base Game Pattern
        if not item.display_name:
            for key in prog_keys:
                if key.get("ExtraData", {}).get("value") == stats_id:
                    h = key.get("Content", {}).get("handle")
                    item.display_name = loc_map.get(h)
                    item.link_method = "BaseGame"
                    if stats_id in prog_names:
                        item.description = prog_names[stats_id].get('description')
                    break
        
        if item_group in prog_visuals:
            item.root_template_uuid = prog_visuals[item_group].get('rootgroup')
            
        # Merged Override
        override = merged_data.get(stats_id)
        if override:
            item.link_method = "MergedOverride"
            dn_node = override.get("DisplayName")
            if isinstance(dn_node, dict) and "handle" in dn_node:
                item.display_name = loc_map.get(dn_node["handle"])
            
            tmpl_node = override.get("TemplateName")
            if isinstance(tmpl_node, dict) and "value" in tmpl_node:
                item.root_template_uuid = tmpl_node["value"]

        items[stats_id] = item.__dict__

    with open("unique_items.json", "w", encoding='utf-8') as f:
        json.dump(items, f, indent=4)
        
    print(f"Exported {len(items)} items.")

if __name__ == "__main__":
    main()