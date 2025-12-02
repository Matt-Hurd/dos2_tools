import os
import json
import re
from collections import defaultdict
from copy import deepcopy
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_xml_localization, parse_stats_txt
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.formatters import sanitize_filename
from dos2_tools.core.stats_engine import resolve_all_stats

# Fields from Character.txt to export
STAT_FIELDS = [
    "Strength", "Finesse", "Intelligence", "Constitution", "Memory", "Wits",
    "Vitality", "MagicPoints", "Armor", "MagicArmor", # Note: 'Armor' is phys in some files
    "APMaximum", "APStart", "APRecovery",
    "FireResistance", "EarthResistance", "WaterResistance", "AirResistance", 
    "PoisonResistance", "PhysicalResistance", "PiercingResistance",
    "Initiative", "Movement", "CriticalChance", "Dodge", "Accuracy"
]

def parse_conditions(condition_list):
    if not condition_list: return ""
    conditions = []
    
    for cond in condition_list:
        if isinstance(cond, dict):
            if cond.get("HasNoPhysicalArmor", {}).get("value") is True:
                conditions.append("No Physical Armor")
            if cond.get("HasNoMagicalArmor", {}).get("value") is True:
                conditions.append("No Magic Armor")
            
            min_hp = cond.get("MinimumHealthPercentage", {}).get("value", 0)
            max_hp = cond.get("MaximumHealthPercentage", {}).get("value", 100)
            
            if min_hp > 0 and max_hp < 100:
                conditions.append(f"HP {min_hp}-{max_hp}%")
            elif min_hp > 0:
                conditions.append(f"HP > {min_hp}%")
            elif max_hp < 100:
                conditions.append(f"HP < {max_hp}%")
                
    return "; ".join(conditions)

def parse_skills(skill_list_node):
    parsed_skills = []
    if not skill_list_node: return parsed_skills
    
    for entry in skill_list_node:
        inner_skills = entry.get("Skill", [])
        if not isinstance(inner_skills, list): inner_skills = [inner_skills]
        
        for skill in inner_skills:
            skill_id = skill.get("Skill", {}).get("value")
            if not skill_id: continue
            
            modes = []
            if skill.get("CasualExplorer", {}).get("value") is True: modes.append("Explorer")
            if skill.get("Classic", {}).get("value") is True: modes.append("Classic")
            if skill.get("TacticianHardcore", {}).get("value") is True: modes.append("Tactician")
            if skill.get("HonorHardcore", {}).get("value") is True: modes.append("Honor")
            
            source_cond = parse_conditions(skill.get("SourceConditions", []))
            target_cond = parse_conditions(skill.get("TargetConditions", []))
            
            cond_str = ""
            if source_cond: cond_str += f"Self: {source_cond}"
            if target_cond: 
                if cond_str: cond_str += " | "
                cond_str += f"Target: {target_cond}"

            parsed_skills.append({
                "id": skill_id,
                "modes": "; ".join(modes),
                "score": skill.get("ScoreModifier", {}).get("value", 1.0),
                "start_round": skill.get("StartRound", {}).get("value", 0),
                "conditions": cond_str,
                "aiflags": skill.get("AIFlags", {}).get("value", 0)
            })
    return parsed_skills

def parse_tags(data):
    tags = []
    tag_root = data.get("Tags", [])
    if not isinstance(tag_root, list): return ""
    
    for entry in tag_root:
        inner_tags = entry.get("Tag", [])
        if not isinstance(inner_tags, list): inner_tags = [inner_tags]
        
        for t in inner_tags:
            val = t.get("Object", {}).get("value")
            if val: tags.append(val)
            
    return "; ".join(sorted(list(set(tags))))

def parse_trade_treasures(data):
    tables = []
    tt_root = data.get("TradeTreasures", [])
    if not isinstance(tt_root, list): return ""
    
    for entry in tt_root:
        val = entry.get("TreasureItem", {}).get("value")
        if val and val != "Empty":
            tables.append(val)
            
    return "; ".join(tables)

def get_variant_signature(data):
    stats = data.get("Stats", {}).get("value", "Unknown")
    level = data.get("LevelOverride", {}).get("value", 0)
    
    equip = "None"
    eq_node = data.get("Equipment", {})
    if isinstance(eq_node, dict): equip = eq_node.get("value", "None")
    
    skills = parse_skills(data.get("SkillList", []))
    skill_sig = "|".join(sorted(s['id'] for s in skills))
    
    loot = "None"
    treasures = data.get("Treasures", [])
    if treasures and isinstance(treasures, list):
         for t in treasures:
             val = t.get("TreasureItem", {}).get("value")
             if val and val != "Empty":
                 loot = val
                 break

    trade = parse_trade_treasures(data)
    tags = parse_tags(data)
                 
    return (stats, level, equip, skill_sig, loot, trade, tags)

def clean_label_string(text):
    text = text.replace('_', ' ')
    noise_patterns = [
        r'^(?:WPN|ARM|EQ|RC|FTJ|ARX|LV|TUT)\b',
        r'^(?:Humans?|Lizards?|Elves|Dwarves|Undead)\b',
        r'^(?:Ranged|Melee|Magic)\b',
        r'^(?:Common|Uncommon|Rare|Legendary|Divine|Unique)\b'
    ]
    current_text = text
    while True:
        prev_text = current_text
        for p in noise_patterns:
            current_text = re.sub(p, '', current_text, flags=re.IGNORECASE).strip()
        if current_text == prev_text: break
            
    current_text = re.sub(r'\s+[A-Z]$', '', current_text)
    current_text = re.sub(r'\s+\d+$', '', current_text)
    return current_text if current_text else text

def generate_variant_label(sig, all_sigs):
    stats, level, equip, skill_sig, loot, trade, tags = sig
    if len(all_sigs) == 1: return "Standard"
        
    labels = []
    
    levels = set(s[1] for s in all_sigs)
    if len(levels) > 1: labels.append(f"Lvl {level}")
        
    equips = set(s[2] for s in all_sigs)
    if len(equips) > 1: labels.append(clean_label_string(equip))
        
    stat_ids = set(s[0] for s in all_sigs)
    if len(stat_ids) > 1:
        clean_stat = clean_label_string(stats)
        if clean_stat not in " ".join(labels): labels.append(clean_stat)

    if not labels: return f"Variant {all_sigs.index(sig) + 1}"
    return " - ".join(labels)

def main():
    print("Starting NPC Wiki Export...")
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    out_dir = "npc_wikitext"
    if not os.path.exists(out_dir): os.makedirs(out_dir)

    loc_data = load_localization_data(all_files, conf)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    # --- NEW: Load and Resolve Character Stats ---
    print("Loading Character Stats...")
    # Add Character.txt pattern if not present in config, or assume it's under stats pattern
    # The config has "stats": ["Stats/Generated/Data/*.txt"...] which covers Character.txt
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    # Filter only Character.txt to avoid processing unrelated stats
    char_stats_files = [f for f in stats_files if f.endswith("Character.txt")]
    
    raw_stats = {}
    for f in char_stats_files:
        raw_stats.update(parse_stats_txt(f))
    
    resolved_stats = resolve_all_stats(raw_stats)
    print(f"Resolved {len(resolved_stats)} character stat entries.")
    # ---------------------------------------------

    print("Loading Templates...")
    template_files = get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj'])
    template_files.extend(get_files_by_pattern(all_files, ["Public/**/RootTemplates/_merged.lsj"]))
    
    root_templates = {}
    for f in template_files:
        _, by_map_key = parse_lsj_templates(f)
        root_templates.update(by_map_key)

    print("Loading Characters...")
    char_files = get_files_by_pattern(all_files, conf['patterns']['level_characters'])
    
    grouped_npcs = defaultdict(list)
    
    for f_path in char_files:
        if 'Test' in f_path or 'Develop' in f_path: continue
        _, level_objects = parse_lsj_templates(f_path)
        
        parts = f_path.replace('\\', '/').split('/')
        region_name = parts[parts.index("Levels")+1] if "Levels" in parts else "Unknown"
        if region_name == "Unknown":
            region_name = parts[parts.index("Globals")+1] if "Globals" in parts else "Unknown"

        for obj_uuid, level_data in level_objects.items():
            template_uuid = level_data.get("TemplateName", {}).get("value")
            final_data = {}
            if template_uuid and template_uuid in root_templates:
                final_data = deepcopy(root_templates[template_uuid])
            final_data.update(level_data)

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

            if not final_name or final_name == "Unknown": continue
            final_data['_REGION'] = region_name
            grouped_npcs[final_name].append(final_data)

    print(f"Grouped into {len(grouped_npcs)} unique names.")
    
    for name, instances in grouped_npcs.items():
        safe_name = sanitize_filename(name)
        if not safe_name: continue
        
        variants = defaultdict(list)
        for inst in instances:
            sig = get_variant_signature(inst)
            variants[sig].append(inst)
            
        all_sigs = list(variants.keys())
        
        output_lines = ["{{InfoboxNPC", f"| name = {name}", "}}"]
        
        for sig, var_instances in variants.items():
            label = generate_variant_label(sig, all_sigs)
            primary = var_instances[0]
            
            stats_id = primary.get("Stats", {}).get("value", "")
            level = primary.get("LevelOverride", {}).get("value", "")
            
            # --- UPDATED COORDINATES FORMAT ---
            coords = []
            for v in var_instances:
                transform = v.get("Transform")
                if isinstance(transform, list) and transform:
                    pos = transform[0].get("Position", {}).get("value", "")
                    # Format: x,y,z,Region (Machine Readable)
                    if pos: 
                        clean_pos = pos.replace(" ", ",")
                        coords.append(f"{clean_pos},{v.get('_REGION')}")
            # ----------------------------------

            loot_table = "None"
            treasures = primary.get("Treasures", [])
            if treasures and isinstance(treasures, list):
                for t in treasures:
                    val = t.get("TreasureItem", {}).get("value")
                    if val and val != "Empty":
                        loot_table = val
                        break

            trade_loot = parse_trade_treasures(primary)
            tags = parse_tags(primary)

            output_lines.append("")
            output_lines.append("{{NPC Variant")
            output_lines.append(f"| label = {label}")
            output_lines.append(f"| guid = {primary.get('MapKey', {}).get('value', '')}")
            output_lines.append(f"| stats_id = {stats_id}")
            output_lines.append(f"| level = {level}")
            output_lines.append(f"| icon = {primary.get('Icon', {}).get('value', '')}")
            
            # --- NEW: Inject Resolved Stats ---
            if stats_id in resolved_stats:
                stat_block = resolved_stats[stats_id]
                for field in STAT_FIELDS:
                    # Check snake_case and PascalCase variants in stat block
                    val = stat_block.get(field) or stat_block.get(field.replace(" ", ""))
                    if val:
                        # Convert to snake_case for template param
                        param_name = re.sub(r'(?<!^)(?=[A-Z])', '_', field).lower()
                        output_lines.append(f"| {param_name} = {val}")
            # ----------------------------------

            output_lines.append(f"| treasure_id = {loot_table}")
            if trade_loot: output_lines.append(f"| trade_treasure_id = {trade_loot}")
            
            if len(coords) == 1: output_lines.append(f"| coordinates = {coords[0]}")
            elif len(coords) > 1: output_lines.append(f"| coordinates = {'; '.join(coords)}")
            
            if tags: output_lines.append(f"| tags = {tags}")
            output_lines.append("}}")
            
            raw_skills = parse_skills(primary.get("SkillList", []))
            for s in raw_skills:
                output_lines.append("{{NPC Skill")
                output_lines.append(f"| skill_id = {s['id']}")
                output_lines.append(f"| modes = {s['modes']}")
                if s['start_round'] > 0: output_lines.append(f"| start_round = {s['start_round']}")
                if s['conditions']: output_lines.append(f"| conditions = {s['conditions']}")
                output_lines.append("}}")
            
        output_lines.append("")
        output_lines.append("{{LocationTable}}")

        file_path = os.path.join(out_dir, f"{safe_name}.wikitext")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines))

    print(f"Generated {len(grouped_npcs)} files in {out_dir}/")

if __name__ == "__main__":
    main()