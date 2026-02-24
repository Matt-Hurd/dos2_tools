"""
Generate Module_Items.lua — a broad item stats Lua module for the DOS2 wiki.

Dumps all Object.txt and Potion.txt stats (with inheritance resolved and
RootTemplate SkillID injected) through a field whitelist, producing a compact
module used by wiki templates that need to look up item stats by ID.

Ported from dos2_tools_old/scripts/generate_items_lua.py.

Usage:
    python3 -m dos2_tools.scripts.generate_items_lua
    python3 -m dos2_tools.scripts.generate_items_lua --out Module_Items.lua
"""

import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.data_models import LSJNode
from dos2_tools.core.formatters import to_lua_table


# Whitelist of stat fields to include in the output module.
# Excludes internal/rarely-used fields to keep the module size manageable.
STAT_FIELDS = {
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
    "SkillID",
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
}

# Types sourced from Object.txt and Potion.txt
ITEM_TYPES = {"Object", "Potion"}


def main():
    parser = argparse.ArgumentParser(
        description="Generate Module_Items.lua broad item stats module for the DOS2 wiki"
    )
    parser.add_argument(
        "--out", default="Module_Items.lua",
        help="Output Lua file path (default: Module_Items.lua)"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    stats_db = game.stats
    templates_by_mapkey = game.templates_by_mapkey

    # Build a mapkey→SkillID index from root templates
    print("  Building RootTemplate SkillID index...")
    mapkey_to_skill = {}
    for rt_uuid, rt_data in templates_by_mapkey.items():
        skill_id = LSJNode(rt_data).get_value("SkillID")
        if skill_id:
            mapkey_to_skill[rt_uuid] = skill_id

    # Filter and build output
    final_lua_data = {}

    for entry_id, data in stats_db.items():
        entry_type = data.get("_type")
        if entry_type not in ITEM_TYPES:
            continue

        # Inject SkillID from RootTemplate if available
        template_guid = data.get("RootTemplate")
        enriched = dict(data)
        if template_guid and template_guid in mapkey_to_skill:
            enriched["SkillID"] = mapkey_to_skill[template_guid]

        # Apply field whitelist
        clean_data = {k: v for k, v in enriched.items() if k in STAT_FIELDS}
        if clean_data:
            final_lua_data[entry_id] = clean_data

    print(f"  Generating Lua module for {len(final_lua_data)} items...")

    lua_str = to_lua_table(final_lua_data)
    output_content = "return " + lua_str

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"Generated {args.out}")


if __name__ == "__main__":
    main()
