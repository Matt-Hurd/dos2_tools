import re
import json
import xml.etree.ElementTree as ET
from collections import OrderedDict
from typing import Dict, List, Any, Optional, Tuple

from dos2_tools.core.models import StatEntry, CraftingCombo, RootTemplate

def parse_item_combos(filepath: str) -> Dict[str, CraftingCombo]:
    regex_combo = re.compile(r'new ItemCombination "(.+?)"')
    regex_result = re.compile(r'new ItemCombinationResult "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    all_combos = {}
    current_combo_id = None
    current_result_id = None # This will now store the ITEM ID found in data
    current_data = {}

    # We might have multiple results in one block in theory, but usually it's Result 1.
    # The original script prioritized Result 1.

    parsing_results = False

    # Temporary storage for the current block being parsed
    current_combo_obj = None

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                match_combo = regex_combo.match(line)
                if match_combo:
                    # If we were parsing a combo previously and it has a result, save it?
                    # The original script structure was:
                    # Combo ID -> { Data: {}, Results: { "Result 1": "ItemID" } }
                    # Then `generate_crafting_wikitext` used `results.get("Result 1")` as the result ID.

                    current_combo_id = match_combo.group(1)
                    current_combo_obj = CraftingCombo(combo_id=current_combo_id, result_id="")
                    all_combos[current_combo_id] = current_combo_obj

                    parsing_results = False
                    continue

                match_result = regex_result.match(line)
                if match_result:
                    parsing_results = True
                    # The group(1) here is just the result block name, often not the item ID.
                    # We ignore it and wait for "Result 1" data property.
                    continue

                match_data = regex_data.match(line)
                if match_data and current_combo_obj:
                    key = match_data.group(1)
                    val = match_data.group(2)

                    if parsing_results:
                        if key == "Result 1":
                            current_combo_obj.result_id = val
                    else:
                        current_combo_obj.ingredients[key] = val
                    continue

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_combos

def parse_object_category_previews(filepath: str) -> Dict[str, Dict[str, str]]:
    regex_preview = re.compile(r'new CraftingPreviewData "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    previews = {}
    current_category = None

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                match_preview = regex_preview.match(line)
                if match_preview:
                    current_category = match_preview.group(1)
                    previews[current_category] = {}
                    continue

                match_data = regex_data.match(line)
                if match_data and current_category:
                    key = match_data.group(1)
                    val = match_data.group(2)
                    previews[current_category][key] = val
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return previews

def parse_item_combo_properties(filepath: str) -> Dict[str, Any]:
    regex_property = re.compile(r'new ItemComboProperty "(.+?)"')
    regex_entry = re.compile(r'new ItemComboPropertyEntry')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    all_properties = {}
    current_prop_id = None

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                match_property = regex_property.match(line)
                if match_property:
                    current_prop_id = match_property.group(1)
                    all_properties[current_prop_id] = {
                        "entries": [],
                        "data": {}
                    }
                    continue

                match_entry = regex_entry.match(line)
                if match_entry and current_prop_id:
                    all_properties[current_prop_id]["entries"].append({})
                    continue

                match_data = regex_data.match(line)
                if match_data and current_prop_id:
                    key = match_data.group(1)
                    val = match_data.group(2)

                    entries = all_properties[current_prop_id]["entries"]
                    if entries:
                        entries[-1][key] = val
                    else:
                        all_properties[current_prop_id]["data"][key] = val
                    continue

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    return all_properties

def parse_stats_txt(filepath: str) -> Dict[str, StatEntry]:
    regex_entry = re.compile(r'new entry "(.+?)"')
    regex_using = re.compile(r'using "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')
    regex_type = re.compile(r'type "(.+?)"')

    all_entries = {}
    current_entry = None

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                match_entry = regex_entry.match(line)
                if match_entry:
                    entry_id = match_entry.group(1)
                    current_entry = StatEntry(name=entry_id)
                    all_entries[entry_id] = current_entry
                    continue

                if not current_entry: continue

                match_using = regex_using.match(line)
                if match_using:
                    current_entry.using = match_using.group(1)
                    continue

                match_data = regex_data.match(line)
                if match_data:
                    key = match_data.group(1)
                    val = match_data.group(2)
                    current_entry.data[key] = val
                    continue

                match_type = regex_type.match(line)
                if match_type:
                    current_entry.type = match_type.group(1)
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_entries

def parse_lsj(filepath: str) -> Optional[Dict]:
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

def parse_xml_localization(filepath: str) -> Dict[str, str]:
    handle_map = {}
    if not filepath: return handle_map

    try:
        context = ET.iterparse(filepath, events=('end',))
        for event, elem in context:
            if elem.tag == 'content':
                uid = elem.get('contentuid')
                text = elem.text or ""
                if uid:
                    handle_map[uid] = text
                elem.clear()
    except ET.ParseError:
        pass
    return handle_map

def _resolve_value_from_dict_or_str(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        return data.get("value")
    return data if isinstance(data, str) else None

def _extract_action_data(node_data: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    book_id = None
    direct_recipes = []

    actions = node_data.get("OnUsePeaceActions")
    if not actions:
        return None, []

    if isinstance(actions, list):
        for action_block in actions:
            action_list = action_block.get("Action", [])
            if not isinstance(action_list, list):
                action_list = [action_list]

            for act in action_list:
                a_type = act.get("ActionType", {})
                type_val = -1
                if isinstance(a_type, dict):
                    type_val = a_type.get("value")

                attributes = act.get("Attributes", [])
                if not isinstance(attributes, list):
                    attributes = [attributes]

                for attr in attributes:
                    if type_val == 11: # Read Book
                        book_node = attr.get("BookId")
                        if isinstance(book_node, dict):
                            book_id = book_node.get("value")
                    elif type_val == 30: # Learn Recipe
                        recipe_node = attr.get("RecipeID")
                        if isinstance(recipe_node, dict):
                            val = recipe_node.get("value")
                            if val:
                                splits = val.split(';')
                                direct_recipes.extend([x.strip() for x in splits if x.strip()])

    return book_id, direct_recipes

def parse_lsj_templates(filepath: str) -> Dict[str, RootTemplate]:
    """
    Parses a templates .lsj file and returns a dict mapping UUID -> RootTemplate
    """
    data = parse_lsj(filepath)
    if not data: return {}

    templates = {}

    game_objects = data.get("save", {}).get("regions", {}).get("Templates", {}).get("GameObjects", [])

    if not game_objects:
        root_nodes = data.get("region", {}).get("node", {}).get("children", {}).get("node", [])
        if isinstance(root_nodes, dict): root_nodes = [root_nodes]
        for n in root_nodes:
            if n.get('id') == 'GameObjects':
                game_objects = n.get("children", {}).get("node", [])
                break

    if isinstance(game_objects, dict): game_objects = [game_objects]

    for go in game_objects:
        map_key = _resolve_value_from_dict_or_str(go.get("MapKey"))
        if not map_key: continue

        stats_id = _resolve_value_from_dict_or_str(go.get("Stats"))
        template_name = _resolve_value_from_dict_or_str(go.get("TemplateName"))

        display_name_node = go.get("DisplayName")
        display_name_handle = None
        if isinstance(display_name_node, dict):
            display_name_handle = display_name_node.get("handle")

        description_node = go.get("Description")
        desc_handle = None
        if isinstance(description_node, dict):
            desc_handle = description_node.get("handle")

        icon = _resolve_value_from_dict_or_str(go.get("Icon"))

        obj_type = _resolve_value_from_dict_or_str(go.get("Type"))
        tags = []
        tags_node = go.get("Tags")
        if tags_node:
            if isinstance(tags_node, str):
                tags.append(tags_node)

        book_id, recipes = _extract_action_data(go)

        rt = RootTemplate(
            uuid=map_key,
            name=template_name or "Unknown",
            stats_id=stats_id,
            type=obj_type,
            display_name_handle=display_name_handle,
            description_handle=desc_handle,
            icon=icon,
            tags=tags,
            book_id=book_id,
            taught_recipes=recipes,
            raw_data=go
        )
        templates[map_key] = rt

    return templates
