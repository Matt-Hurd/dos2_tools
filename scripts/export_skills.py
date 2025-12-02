import os
import argparse
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt, parse_xml_localization
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import scan_lsj_for_uuids, get_localized_text
from dos2_tools.core.formatters import sanitize_filename, to_wikitext_infobox

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="skill_wikitext")
    args = parser.parse_args()
    
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    xml_files = get_files_by_pattern(all_files, conf['patterns']['localization_xml'])
    loc_map = {}
    for xf in xml_files:
        loc_map.update(parse_xml_localization(xf))
        
    uuid_map = scan_lsj_for_uuids(all_files)
    
    skill_files = get_files_by_pattern(all_files, conf['patterns']['skills'])
    raw_stats = {}
    for sf in skill_files:
        raw_stats.update(parse_stats_txt(sf))
        
    resolved = resolve_all_stats(raw_stats)
    
    count = 0
    seen_names = set()
    
    for skill_id, data in resolved.items():
        raw_dn = data.get("DisplayName")
        if not raw_dn: continue
        
        name = get_localized_text(raw_dn, uuid_map, loc_map)
        if not name: continue
        
        safe_name = sanitize_filename(name)
        if safe_name in seen_names: continue
        seen_names.add(safe_name)
        
        fname = f"{safe_name}.wikitext"
        path = os.path.join(args.outdir, fname)
        
        params = {"skill_id": skill_id}
        content = to_wikitext_infobox("InfoboxSkill", params)
        content += f"\n\n{{{{SkillFooter|skill_id={skill_id}}}}}"
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        count += 1
        
    print(f"Generated {count} skill pages.")

if __name__ == "__main__":
    main()