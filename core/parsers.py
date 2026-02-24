"""
Parsers for DOS2 game data file formats.

Handles parsing of:
  - Stats .txt files (Armor, Weapon, Object, Potion, Skill, etc.)
  - LSJ (JSON) files (root templates, level data, localization)
  - XML localization files (english.xml)
  - Item combo files (crafting recipes)
  - Item progression files (names and visuals)
  - Object category preview data
"""

import re
import json
import xml.etree.ElementTree as ET
from collections import OrderedDict

from dos2_tools.core.config import GIFTBAG_MAP
from dos2_tools.core.data_models import LSJNode, GameObject


# ─── File-Path Helpers ───────────────────────────────────────────────────────

def get_region_name(file_path):
    """
    Derive the game region name from a level or globals file path.

    Looks for the component after "Levels" or "Globals" in the path.
    Returns "Unknown" if neither sentinel is found.

    Used by scripts that scan level files and need to tag objects with
    their region (e.g. FJ_FortJoy_Main, RC_Main).
    """
    parts = file_path.replace("\\", "/").split("/")
    if "Levels" in parts:
        return parts[parts.index("Levels") + 1]
    if "Globals" in parts:
        return parts[parts.index("Globals") + 1]
    return "Unknown"


# ─── Stats (.txt) Parsing ───────────────────────────────────────────────────

def parse_stats_txt(filepath):
    """
    Parse a DOS2 stats text file (Armor.txt, Weapon.txt, Object.txt, etc.).

    Returns a dict of entry_id -> {_id, _type, _using, _data: OrderedDict}.
    Inheritance (_using) is NOT resolved here — see stats_engine.resolve_all_stats().
    """
    regex_entry = re.compile(r'new entry "(.+?)"')
    regex_using = re.compile(r'using "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')
    regex_type = re.compile(r'type "(.+?)"')

    all_entries = {}
    current_entry = None

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                match = regex_entry.match(line)
                if match:
                    entry_id = match.group(1)
                    current_entry = {"_id": entry_id, "_data": OrderedDict()}
                    all_entries[entry_id] = current_entry
                    continue

                if not current_entry:
                    continue

                match = regex_using.match(line)
                if match:
                    current_entry["_using"] = match.group(1)
                    continue

                match = regex_data.match(line)
                if match:
                    current_entry["_data"][match.group(1)] = match.group(2)
                    continue

                match = regex_type.match(line)
                if match:
                    current_entry["_type"] = match.group(1)
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_entries


# ─── LSJ (JSON) Parsing ────────────────────────────────────────────────────

def parse_lsj(filepath):
    """Parse a .lsj JSON file. Returns the parsed dict or None on error."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def parse_lsj_templates(filepath):
    """
    Parse an LSJ file containing RootTemplates/GameObjects.

    Handles both the "save.regions.Templates.GameObjects" format and
    the "region.node.children.node" format.

    Returns:
        tuple[dict, dict]: (by_stats_id, by_map_key) — two indexes into
        the same underlying GameObject instances.
    """
    data = parse_lsj(filepath)
    if not data:
        return {}, {}

    by_stats = {}
    by_map_key = {}

    root = LSJNode(data)

    # Try format 1: save.regions.Templates.GameObjects
    game_objects = (
        root.get_node("save")
        .get_node("regions")
        .get_node("Templates")
        .get_raw("GameObjects", [])
    )

    # Try format 2: region.node.children.node
    if not game_objects:
        for n in root.get_node("region").get_node("node").get_node("children").get_list("node"):
            if n.get_value("id") == "GameObjects":
                game_objects = n.get_node("children").get_raw("node", [])
                break

    if isinstance(game_objects, dict):
        game_objects = [game_objects]
    if not isinstance(game_objects, list):
        game_objects = []

    for go_raw in game_objects:
        go = LSJNode(go_raw)
        obj = _extract_game_object(go)
        if not obj:
            continue

        if obj.stats_id:
            by_stats[obj.stats_id] = obj
        if obj.map_key:
            by_map_key[obj.map_key] = obj

    return by_stats, by_map_key


def _extract_game_object(go):
    """
    Extract relevant fields from a raw GameObjects node into a GameObject.

    Handles both direct-property and attribute-list LSJ formats.
    Returns None if the node lacks both MapKey and Stats.
    """
    map_key = go.get_value("MapKey")
    stats_id = go.get_value("Stats")
    template_name = go.get_value("TemplateName")
    icon = go.get_value("Icon")
    description = go.get_raw("Description")
    display_name = go.get_raw("DisplayName")
    name = go.get_value("Name")

    # Attribute-list fallback (older LSJ format)
    for attr in go.get_list("attribute"):
        aid = attr.get_value("id")
        if not map_key and aid == "MapKey":
            map_key = attr.get_value("value")
        if not stats_id and aid == "Stats":
            stats_id = attr.get_value("value")
        if not description and aid == "Description":
            description = attr.raw
        if not display_name and aid == "DisplayName":
            display_name = attr.raw
        if not icon and aid == "Icon":
            icon = attr.get_value("value")

    if not map_key and not stats_id:
        return None

    obj = GameObject(
        map_key=map_key,
        stats_id=stats_id,
        template_name=template_name,
        icon=icon,
        name=name,
        display_name=display_name,
        description=description,
    )

    # Scalar fields
    raw_type = go.get_raw("Type")
    if raw_type is not None:
        obj.type = go.get_value("Type")
    raw_default_state = go.get_raw("DefaultState")
    if raw_default_state is not None:
        obj.default_state = go.get_value("DefaultState")

    # Passthrough raw fields for downstream LSJNode-based helpers
    for lsj_key, attr_name in (
        ("SkillList", "skill_list"),
        ("LevelOverride", "level_override"),
        ("Transform", "transform"),
        ("Tags", "tags"),
        ("ItemList", "item_list"),
        ("OnUsePeaceActions", "on_use_peace_actions"),
        ("InventoryList", "inventory_list"),
    ):
        val = go.get_raw(lsj_key)
        if val is not None:
            setattr(obj, attr_name, val)

    # Trade treasures — unwrap into plain list[str]
    for tt in go.get_list("TradeTreasures"):
        val = tt.get_value("TreasureItem")
        if val:
            obj.trade_treasures.append(val)

    # Treasures — unwrap into plain list[str]
    for t in go.get_list("Treasures"):
        val = t.get_value("TreasureItem")
        if val:
            obj.treasures.append(val)

    # Extract SkillID from OnUsePeaceActions
    if go.has("OnUsePeaceActions"):
        skill_id = go.deep_find_value("SkillID")
        if skill_id:
            obj.skill_id = skill_id

    return obj


# ─── XML Localization ───────────────────────────────────────────────────────

def parse_xml_localization(filepath):
    """
    Parse an english.xml localization file.

    Returns a dict of content_uid -> localized_text.
    """
    handle_map = {}
    if not filepath:
        return handle_map

    try:
        context = ET.iterparse(filepath, events=("end",))
        for event, elem in context:
            if elem.tag == "content":
                uid = elem.get("contentuid")
                text = elem.text or ""
                if uid:
                    handle_map[uid] = text
                elem.clear()
    except ET.ParseError:
        pass
    return handle_map


# ─── Item Combos (Crafting) ─────────────────────────────────────────────────

def parse_item_combos(filepath):
    """
    Parse an ItemCombos.txt file (crafting recipes).

    Returns an OrderedDict of combo_id -> combo data, including
    gift bag attribution based on the file path.
    """
    regex_combo = re.compile(r'new ItemCombination "(.+?)"')
    regex_result = re.compile(r'new ItemCombinationResult "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    # Detect gift bag from file path
    giftbag_name = None
    for gb_key, gb_label in GIFTBAG_MAP.items():
        if gb_key in filepath:
            giftbag_name = gb_label
            break

    all_combos = OrderedDict()
    current_combo = None
    parsing_results = False

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                match = regex_combo.match(line)
                if match:
                    combo_id = match.group(1)
                    current_combo = {
                        "ID": combo_id,
                        "Data": OrderedDict(),
                        "Results": OrderedDict(),
                        "Giftbag": giftbag_name,
                    }
                    all_combos[combo_id] = current_combo
                    parsing_results = False
                    continue

                match = regex_result.match(line)
                if match:
                    if current_combo:
                        parsing_results = True
                        current_combo["ResultID"] = match.group(1)
                    continue

                match = regex_data.match(line)
                if match and current_combo:
                    key, val = match.group(1), match.group(2)
                    if parsing_results:
                        current_combo["Results"][key] = val
                    else:
                        current_combo["Data"][key] = val
                    continue

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_combos


def parse_object_category_previews(filepath):
    """Parse ObjectCategoriesItemComboPreviewData.txt."""
    regex_preview = re.compile(r'new CraftingPreviewData "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    previews = {}
    current_category = None

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                match = regex_preview.match(line)
                if match:
                    current_category = match.group(1)
                    previews[current_category] = {}
                    continue

                match = regex_data.match(line)
                if match and current_category:
                    previews[current_category][match.group(1)] = match.group(2)
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return previews


def parse_item_combo_properties(filepath):
    """Parse ItemComboProperties.txt."""
    regex_property = re.compile(r'new ItemComboProperty "(.+?)"')
    regex_entry = re.compile(r"new ItemComboPropertyEntry")
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    all_properties = {}
    current_prop_id = None

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                match = regex_property.match(line)
                if match:
                    current_prop_id = match.group(1)
                    all_properties[current_prop_id] = {
                        "entries": [],
                        "data": {},
                    }
                    continue

                match = regex_entry.match(line)
                if match and current_prop_id:
                    all_properties[current_prop_id]["entries"].append({})
                    continue

                match = regex_data.match(line)
                if match and current_prop_id:
                    key, val = match.group(1), match.group(2)
                    entries = all_properties[current_prop_id]["entries"]
                    if entries:
                        entries[-1][key] = val
                    else:
                        all_properties[current_prop_id]["data"][key] = val
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_properties


# ─── Item Progression ───────────────────────────────────────────────────────

def parse_item_progression_names(filepath):
    """Parse ItemProgressionNames.txt (name groups for items)."""
    name_groups = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            current_group = None
            for line in f:
                line = line.strip()
                match = re.search(r'new namegroup "(.*?)"', line)
                if match:
                    current_group = match.group(1)
                    name_groups[current_group] = {}
                    continue

                if current_group and line.startswith("add name"):
                    match = re.search(r'add name "(.*?)","(.*?)"', line)
                    if match:
                        name_groups[current_group]["name"] = match.group(1)
                        name_groups[current_group]["description"] = match.group(2)
    except FileNotFoundError:
        pass
    return name_groups


def parse_item_progression_visuals(filepath):
    """Parse ItemProgressionVisuals.txt (visual root groups for items)."""
    item_groups = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            current_group = None
            for line in f:
                line = line.strip()
                match = re.search(r'new itemgroup "(.*?)"', line)
                if match:
                    current_group = match.group(1)
                    item_groups[current_group] = {}
                    continue

                if current_group and line.startswith("add rootgroup"):
                    match = re.search(r'add rootgroup "(.*?)","(.*?)"', line)
                    if match:
                        item_groups[current_group]["rootgroup"] = match.group(1)
    except FileNotFoundError:
        pass
    return item_groups


# ─── Treasure Tables ────────────────────────────────────────────────────────

def parse_treasure_table(filepath):
    """
    Parse a TreasureTable.txt file.

    Returns the raw text content for processing by the loot engine,
    since treasure tables use a CSV-like format that requires
    stateful multi-line parsing best handled by TreasureParser.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""
