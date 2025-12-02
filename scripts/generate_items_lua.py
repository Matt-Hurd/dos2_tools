import os
import sys
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt, parse_lsj_templates
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.formatters import to_lua_table

STAT_FIELDS = [
    "AccuracyBoost",
    "Act",
    "Act part",
    "Act strength",
    "ActionPoints",
    "AiCalculationStatsOverride",
    "AirResistance",
    "AirSpecialist",
    "APCostBoost",
    "APMaximum",
    "APRecovery",
    "APStart",
    "Armor",
    "ArmorBoost",
    "AuraAllies",
    "AuraEnemies",
    "AuraRadius",
    "BloodSurfaceType",
    "BonusWeapon",
    "BoostConditions",
    "ChanceToHitBoost",
    "ComboCategory",
    "Constitution",
    "CriticalChance",
    "Damage",
    "Damage Multiplier",
    "Damage Range",
    "DamageBoost",
    "DamageType",
    "DodgeBoost",
    "Duration",
    "EarthResistance",
    "EarthSpecialist",
    "ExtraProperties",
    "Finesse",
    "FireResistance",
    "FireSpecialist",
    "Flags",
    "IgnoredByAI",
    "Initiative",
    "Intelligence",
    "InventoryTab",
    "IsConsumable",
    "IsFood",
    "LifeSteal",
    "Luck",
    "MagicArmor",
    "MagicArmorBoost",
    "MagicPoints",
    "MaxAmount",
    "MaxLevel",
    "Memory",
    "MinAmount",
    "MinLevel",
    "Movement",
    "MovementSpeedBoost",
    "Necromancy",
    "ObjectCategory",
    "PainReflection",
    "Persuasion",
    "PhysicalResistance",
    "PiercingResistance",
    "PoisonResistance",
    "Priority",
    "RangeBoost",
    "Reflection",
    "RootTemplate",
    "RuneEffectAmulet",
    "RuneEffectUpperbody",
    "RuneEffectWeapon",
    "RuneLevel",
    "SavingThrow",
    "Sight",
    "SPCostBoost",
    "StackId",
    "StatusEffect",
    "StatusIcon",
    "StatusMaterial",
    "Strength",
    "SummonLifelinkModifier",
    "Telekinesis",
    "UnknownBeforeConsume",
    "UseAPCost",
    "Value",
    "Vitality",
    "VitalityBoost",
    "VitalityPercentage",
    "WarriorLore",
    "WaterResistance",
    "WaterSpecialist",
    "Weight",
    "Wits",
]

def filter_stats(data):
    filtered = {}
    for k, v in data.items():
        if k in STAT_FIELDS:
            filtered[k] = v
    return filtered

def main():
    conf = get_config()
    
    print("Resolving file load order...")
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Item Stats (Object.txt and Potion.txt)...")
    stats_files = []
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['objects']))
    stats_files.extend(get_files_by_pattern(all_files, conf['patterns']['potions']))
    
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
        template_guid = data.get("RootTemplate")
        if template_guid and template_guid in root_templates_by_guid:
            template_data = root_templates_by_guid[template_guid]
            
            if "SkillID" in template_data:
                data["SkillID"] = template_data["SkillID"]

        clean_data = filter_stats(data)
        if clean_data:
            final_lua_data[entry_id] = clean_data

    print(f"Generating Lua module for {len(final_lua_data)} items...")
    
    lua_str = to_lua_table(final_lua_data)
    output_content = "return " + lua_str
    
    output_path = "Module_Items.lua"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_content)
        
    print(f"Success. Written to {output_path}")

if __name__ == "__main__":
    main()