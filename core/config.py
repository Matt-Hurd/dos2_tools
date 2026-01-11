import os

LOAD_ORDER = [
    "Icons", "Minimaps", "Shared", "Origins", "English", 
    "Patch1", "Patch1_Gold", "Patch1_Hotfix1", "Patch1_Hotfix2", "Patch1_Hotfix4", "Patch1_TDE",
    "Patch2", "Patch3", "Patch4", "Patch4-1", "Patch5", "Patch6", "Patch7", "Patch7_Hotfix",
    "Patch8", "Patch9", "Patch10",
]

UUID_BLACKLIST = {
    "hac19df12gb0c8g43c6ga46fg23d85a679b68",
}

def get_config():
    base_path = "extracted"
    return {
        "base_path": base_path,
        "load_order_dirs": [os.path.join(base_path, d) for d in LOAD_ORDER],
        "cache_file": "cache_resolved_load_order.txt",
        "patterns": {
            "stats": ["Stats/Generated/Data/*.txt", "Public/**/Stats/Generated/Data/*.txt"],
            "objects": ["Stats/Generated/Data/Object.txt", "Public/**/Stats/Generated/Data/Object.txt"],
            "potions": ["Stats/Generated/Data/Potion.txt", "Public/**/Stats/Generated/Data/Potion.txt"],
            "armors": ["Stats/Generated/Data/Armor.txt", "Public/**/Stats/Generated/Data/Armor.txt"],
            "shields": ["Stats/Generated/Data/Shield.txt", "Public/**/Stats/Generated/Data/Shield.txt"],
            "weapons": ["Stats/Generated/Data/Weapon.txt", "Public/**/Stats/Generated/Data/Weapon.txt"],
            "item_prog_names": ["Public/**/Stats/Generated/Data/ItemProgressionNames.txt"],
            "item_prog_visuals": ["Public/**/Stats/Generated/Data/ItemProgressionVisuals.txt"],
            "item_prog_lsj": ["**/Localization/ItemProgression.lsj"],
            "localization_xml": ["Localization/English/english.xml"],
            "merged_lsj": ["Public/**/RootTemplates/_merged.lsj"],
            "root_templates_lsj": ["Public/**/RootTemplates/*.lsj"],
            "skills": [
                "Public/DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4/Stats/Generated/Data/Skill*.txt",
                "Public/Engine/Stats/Generated/Data/Skill*.txt",
                "Public/Game/Stats/Generated/Data/Skill*.txt",
                "Public/Shared/Stats/Generated/Data/Skill*.txt",
                "Public/ArmorSets/Stats/Generated/Data/Skill*.txt"
            ],
            "level_characters": ["Mods/**/Levels/**/Characters/_merged.lsj", "Mods/**/Globals/**/Characters/_merged.lsj", "Mods/**/Globals/**/Characters/**.lsj", "Mods/**/Levels/**/Characters/**.lsj"],
            "level_items": ["Mods/**/Levels/**/Items/*.lsj", "Mods/**/Globals/**/Items/*.lsj"],
            "recipes": ["Mods/**/Story/Journal/recipes_prototypes.lsj"],
            "item_combo_properties": ["Public/DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4/Stats/Generated/ItemComboProperties.txt", "Public/Shared/Stats/Generated/ItemComboProperties.txt", "Public/ArmorSets/Stats/Generated/ItemComboProperties.txt", "Public/ArmorSets/Stats/Generated/ItemComboProperties.txt"],
            "item_combos": ["Public/DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4/Stats/Generated/ItemCombos.txt", "Public/Shared/Stats/Generated/ItemCombos.txt", "Public/ArmorSets/Stats/Generated/ItemCombos.txt"],
            "object_categories_item_combos": ["Public/**/Stats/Generated/ObjectCategoriesItemComboPreviewData.txt"],
        }
    }