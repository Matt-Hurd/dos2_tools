import os

# Base game modules that are always loaded and considered "Vanilla"
BASE_GAME_MODULES = {
    "Shared",
    "Origins", # Often just "DivinityOrigins" in folder structure, but config used "Origins" in LOAD_ORDER
    "DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4",
    "Engine",
    "Game",
    "ArmorSets" # This might be considered a giftbag (The 4 Relics of Rivellon), but usually treated as base in Definitive Edition.
}

# Configured load order for PATCHES/Localization (these are directories, not necessarily "Modules" with stats)
BASE_LOAD_ORDER = [
    "Icons", "Minimaps", "Shared", "Origins", "English", 
    "Patch1", "Patch1_Gold", "Patch1_Hotfix1", "Patch1_Hotfix2", "Patch1_Hotfix4", "Patch1_TDE",
    "Patch2", "Patch3", "Patch4", "Patch4-1", "Patch5", "Patch6", "Patch7", "Patch7_Hotfix",
    "Patch8", "Patch9", "Patch10",
]

UUID_BLACKLIST = {
    "hac19df12gb0c8g43c6ga46fg23d85a679b68",
}

def get_config(active_modules=None):
    """
    Returns the configuration dictionary.

    :param active_modules: Optional list of additional module directory names to append to the load order.
    """
    base_path = "extracted"

    current_load_order = list(BASE_LOAD_ORDER)
    if active_modules:
        current_load_order.extend(active_modules)

    return {
        "base_path": base_path,
        "load_order_dirs": [os.path.join(base_path, d) for d in current_load_order],
        "active_modules": active_modules or [],
        "cache_file": "cache_resolved_load_order.txt",
        "patterns": {
            # Standard Stats
            "stats": ["Stats/Generated/Data/*.txt", "Public/**/Stats/Generated/Data/*.txt"],
            "objects": ["Stats/Generated/Data/Object.txt", "Public/**/Stats/Generated/Data/Object.txt"],
            "potions": ["Stats/Generated/Data/Potion.txt", "Public/**/Stats/Generated/Data/Potion.txt"],
            "armors": ["Stats/Generated/Data/Armor.txt", "Public/**/Stats/Generated/Data/Armor.txt"],
            "shields": ["Stats/Generated/Data/Shield.txt", "Public/**/Stats/Generated/Data/Shield.txt"],
            "weapons": ["Stats/Generated/Data/Weapon.txt", "Public/**/Stats/Generated/Data/Weapon.txt"],

            # Skills - Now using a broad pattern to catch everything, filtering will happen in Context
            "skills": ["Public/**/Stats/Generated/Data/Skill*.txt"],

            # Other resources
            "item_prog_names": ["Public/**/Stats/Generated/Data/ItemProgressionNames.txt"],
            "item_prog_visuals": ["Public/**/Stats/Generated/Data/ItemProgressionVisuals.txt"],
            "item_prog_lsj": ["**/Localization/ItemProgression.lsj"],
            "localization_xml": ["Localization/English/english.xml"],
            "merged_lsj": ["Public/**/RootTemplates/_merged.lsj"],
            "root_templates_lsj": ["Public/**/RootTemplates/*.lsj"],
            "level_characters": ["Mods/**/Levels/**/Characters/_merged.lsj", "Mods/**/Globals/**/Characters/_merged.lsj", "Mods/**/Globals/**/Characters/**.lsj", "Mods/**/Levels/**/Characters/**.lsj"],
            "level_items": ["Mods/**/Levels/**/Items/*.lsj", "Mods/**/Globals/**/Items/*.lsj"],
            "recipes": ["Mods/**/Story/Journal/recipes_prototypes.lsj"],
            "item_combo_properties": ["Public/**/Stats/Generated/ItemComboProperties.txt"],
            "item_combos": ["Public/**/Stats/Generated/ItemCombos.txt"],
            "object_categories_item_combos": ["Public/**/Stats/Generated/ObjectCategoriesItemComboPreviewData.txt"],
        }
    }

def get_module_name_from_path(filepath: str) -> str:
    """
    Extracts the module name from a file path.
    Assumes standard structure: .../Public/<ModuleName>/... or .../Mods/<ModuleName>/...
    """
    parts = filepath.replace('\\', '/').split('/')

    try:
        if "Public" in parts:
            idx = parts.index("Public")
            if idx + 1 < len(parts):
                return parts[idx + 1]

        if "Mods" in parts:
            idx = parts.index("Mods")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except ValueError:
        pass

    return "Base" # Default fall back
