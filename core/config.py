"""
Configuration for DOS2 game data extraction and processing.

Defines the load order, file patterns for locating game data,
and metadata about each game version/patch.
"""

import os

# The master load order. Later entries override earlier ones.
# Only includes directories that contain game-relevant data.
LOAD_ORDER = [
    "Icons", "Minimaps", "Shared", "Origins", "English",
    "Patch1", "Patch1_Gold", "Patch1_Hotfix1", "Patch1_Hotfix2", "Patch1_Hotfix4", "Patch1_TDE",
    "Patch2", "Patch3", "Patch4", "Patch4-1", "Patch5", "Patch6", "Patch7", "Patch7_Hotfix",
    "Patch8", "Patch9", "Patch10",
]

# Human-readable metadata for each load order entry.
# Used for version provenance display and filtering.
LOAD_ORDER_METADATA = {
    "Icons":            {"label": "Icons",                      "category": "base"},
    "Minimaps":         {"label": "Minimaps",                   "category": "base"},
    "Shared":           {"label": "Shared (Base)",              "category": "base"},
    "Origins":          {"label": "Origins (Base)",             "category": "base"},
    "English":          {"label": "English Localization",       "category": "base"},
    "Patch1":           {"label": "Patch 1",                    "category": "patch"},
    "Patch1_Gold":      {"label": "Patch 1 Gold",               "category": "patch"},
    "Patch1_Hotfix1":   {"label": "Patch 1 Hotfix 1",           "category": "patch"},
    "Patch1_Hotfix2":   {"label": "Patch 1 Hotfix 2",           "category": "patch"},
    "Patch1_Hotfix4":   {"label": "Patch 1 Hotfix 4",           "category": "patch"},
    "Patch1_TDE":       {"label": "The Dark Eye",               "category": "patch"},
    "Patch2":           {"label": "Patch 2",                    "category": "patch"},
    "Patch3":           {"label": "Patch 3 (Definitive Ed.)",   "category": "patch"},
    "Patch4":           {"label": "Patch 4",                    "category": "patch"},
    "Patch4-1":         {"label": "Patch 4.1",                  "category": "patch"},
    "Patch5":           {"label": "Patch 5 (Gift Bags 1)",      "category": "giftbag"},
    "Patch6":           {"label": "Patch 6 (Gift Bags 2)",      "category": "giftbag"},
    "Patch7":           {"label": "Patch 7",                    "category": "patch"},
    "Patch7_Hotfix":    {"label": "Patch 7 Hotfix",             "category": "patch"},
    "Patch8":           {"label": "Patch 8 (Gift Bags 3)",      "category": "giftbag"},
    "Patch9":           {"label": "Patch 9",                    "category": "patch"},
    "Patch10":          {"label": "Patch 10",                   "category": "patch"},
}

# Gift bag mod identifiers and their display names
GIFTBAG_MAP = {
    "CMP_EnemyRandomizer_Kamil": "Enemy Randomizer",
    "CMP_LevelUpEquipment": "Sorcerous Sundries",
    "AS_BlackCatPlus": "Nine Lives",
    "AS_GrowYourHerbs": "Herb Gardens",
    "AS_ToggleSpeedAddon": "Endless Runner",
    "CMP_SummoningImproved_Kamil": "Pet Power",
    "CMP_8AP_Kamil": "8 Action Points",
    "CMP_CraftingOverhaul": "Crafting Overhaul",
    "CMP_FTJRespec_Kamil": "Fort Joy Magic Mirror",
    "Character_Creation_Pack": "Divine Talents",
}

# UUIDs to exclude from processing
UUID_BLACKLIST = {
    "hac19df12gb0c8g43c6ga46fg23d85a679b68",
}

# Glob patterns for locating specific game data files.
# These are matched against relative paths within each load order directory.
FILE_PATTERNS = {
    "stats": [
        "Stats/Generated/Data/*.txt",
        "Public/**/Stats/Generated/Data/*.txt",
    ],
    "objects": [
        "Stats/Generated/Data/Object.txt",
        "Public/**/Stats/Generated/Data/Object.txt",
    ],
    "potions": [
        "Stats/Generated/Data/Potion.txt",
        "Public/**/Stats/Generated/Data/Potion.txt",
    ],
    "armors": [
        "Stats/Generated/Data/Armor.txt",
        "Public/**/Stats/Generated/Data/Armor.txt",
    ],
    "shields": [
        "Stats/Generated/Data/Shield.txt",
        "Public/**/Stats/Generated/Data/Shield.txt",
    ],
    "weapons": [
        "Stats/Generated/Data/Weapon.txt",
        "Public/**/Stats/Generated/Data/Weapon.txt",
    ],
    "item_prog_names": [
        "Public/**/Stats/Generated/Data/ItemProgressionNames.txt",
    ],
    "item_prog_visuals": [
        "Public/**/Stats/Generated/Data/ItemProgressionVisuals.txt",
    ],
    "item_prog_lsj": [
        "**/Localization/ItemProgression.lsj",
    ],
    "localization_xml": [
        "Localization/English/english.xml",
    ],
    "merged_lsj": [
        "Public/**/RootTemplates/_merged.lsj",
    ],
    "root_templates_lsj": [
        "Public/**/RootTemplates/*.lsj",
    ],
    "skills": [
        "Public/DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4/Stats/Generated/Data/Skill*.txt",
        "Public/Engine/Stats/Generated/Data/Skill*.txt",
        "Public/Game/Stats/Generated/Data/Skill*.txt",
        "Public/Shared/Stats/Generated/Data/Skill*.txt",
        "Public/ArmorSets/Stats/Generated/Data/Skill*.txt",
    ],
    "level_characters": [
        "Mods/**/Levels/**/Characters/_merged.lsj",
        "Mods/**/Globals/**/Characters/_merged.lsj",
        "Mods/**/Globals/**/Characters/**.lsj",
        "Mods/**/Levels/**/Characters/**.lsj",
    ],
    "level_items": [
        "Mods/**/Levels/**/Items/*.lsj",
        "Mods/**/Globals/**/Items/*.lsj",
    ],
    "recipes": [
        "Mods/**/Story/Journal/recipes_prototypes.lsj",
    ],
    "item_combo_properties": [
        "Public/DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4/Stats/Generated/ItemComboProperties.txt",
        "Public/Shared/Stats/Generated/ItemComboProperties.txt",
        "Public/ArmorSets/Stats/Generated/ItemComboProperties.txt",
    ],
    "item_combos": [
        "Public/**/Stats/Generated/ItemCombos.txt",
    ],
    "object_categories_item_combos": [
        "Public/**/Stats/Generated/ObjectCategoriesItemComboPreviewData.txt",
    ],
    "treasure_tables": [
        "Public/**/Stats/Generated/TreasureTable.txt",
    ],
}

# Valid game levels (excluding test/dev/arena levels)
VALID_LEVELS = [
    "ARX_Endgame",
    "ARX_Main",
    "CoS_Main",
    "CoS_Main_Ending",
    "FJ_FortJoy_Main",
    "LV_HoE_Main",
    "RC_Main",
    "TUT_Tutorial_A",
]


def get_config():
    """Returns the full configuration dictionary."""
    base_path = "exported"
    return {
        "base_path": base_path,
        "load_order_dirs": [os.path.join(base_path, d) for d in LOAD_ORDER],
        "patterns": FILE_PATTERNS,
    }
