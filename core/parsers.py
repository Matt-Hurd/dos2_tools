import re
import json
import xml.etree.ElementTree as ET
from collections import OrderedDict

def parse_item_combos(filepath):
    regex_combo = re.compile(r'new ItemCombination "(.+?)"')
    regex_result = re.compile(r'new ItemCombinationResult "(.+?)"')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')

    all_combos = OrderedDict()
    current_combo = None
    parsing_results = False

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                match_combo = regex_combo.match(line)
                if match_combo:
                    combo_id = match_combo.group(1)
                    current_combo = {
                        "ID": combo_id, 
                        "Data": OrderedDict(), 
                        "Results": OrderedDict()
                    }
                    all_combos[combo_id] = current_combo
                    parsing_results = False
                    continue

                match_result = regex_result.match(line)
                if match_result:
                    if current_combo:
                        parsing_results = True
                        current_combo["ResultID"] = match_result.group(1)
                    continue

                match_data = regex_data.match(line)
                if match_data and current_combo:
                    key = match_data.group(1)
                    val = match_data.group(2)
                    
                    if parsing_results:
                        current_combo["Results"][key] = val
                    else:
                        current_combo["Data"][key] = val
                    continue

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_combos

def parse_item_combo_properties(filepath):
    regex_property = re.compile(r'new ItemComboProperty "(.+?)"')
    regex_entry = re.compile(r'new ItemComboPropertyEntry')
    regex_data = re.compile(r'data "(.+?)" "(.*?)"')
    all_properties = {}
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                match_property = regex_property.match(line)
                if match_property:
                    property_id = match_property.group(1)
                    all_properties[property_id] = []
                    continue
                
                match_entry = regex_entry.match(line)
                if match_entry:
                    current_entry = {}
                    all_properties[property_id].append(current_entry)
                    continue
                    
                match_data = regex_data.match(line)
                if match_data and all_properties[property_id]:
                    key = match_data.group(1)
                    val = match_data.group(2)
                    all_properties[property_id][-1][key] = val
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    return all_properties

def parse_stats_txt(filepath):
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
                    current_entry = {"_id": entry_id, "_data": OrderedDict()}
                    all_entries[entry_id] = current_entry
                    continue
                    
                if not current_entry: continue
                    
                match_using = regex_using.match(line)
                if match_using:
                    current_entry["_using"] = match_using.group(1)
                    continue
                    
                match_data = regex_data.match(line)
                if match_data:
                    key = match_data.group(1)
                    val = match_data.group(2)
                    current_entry["_data"][key] = val
                    continue

                match_type = regex_type.match(line)
                if match_type:
                    current_entry["_type"] = match_type.group(1)
                    continue
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")

    return all_entries

def parse_lsj(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

def parse_xml_localization(filepath):
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

def parse_item_progression_names(filepath):
    name_groups = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            current_group = None
            for line in f:
                line = line.strip()
                match_group = re.search(r'new namegroup "(.*?)"', line)
                if match_group:
                    current_group = match_group.group(1)
                    name_groups[current_group] = {}
                    continue
                
                if current_group and line.startswith('add name'):
                    match_name = re.search(r'add name "(.*?)","(.*?)"', line)
                    if match_name:
                        name_groups[current_group]['name'] = match_name.group(1)
                        name_groups[current_group]['description'] = match_name.group(2)
    except FileNotFoundError:
        pass
    return name_groups

def parse_item_progression_visuals(filepath):
    item_groups = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            current_group = None
            for line in f:
                line = line.strip()
                match_group = re.search(r'new itemgroup "(.*?)"', line)
                if match_group:
                    current_group = match_group.group(1)
                    item_groups[current_group] = {}
                    continue
                
                if current_group and line.startswith('add rootgroup'):
                    match_root = re.search(r'add rootgroup "(.*?)","(.*?)"', line)
                    if match_root:
                        item_groups[current_group]['rootgroup'] = match_root.group(1)
    except FileNotFoundError:
        pass
    return item_groups

def _find_skill_id_deep(data):
    if isinstance(data, dict):
        if "SkillID" in data:
            val_obj = data["SkillID"]
            if isinstance(val_obj, dict):
                return val_obj.get("value")
            return val_obj 
        
        if data.get("id") == "SkillID" and "value" in data:
            return data["value"]

        for v in data.values():
            found = _find_skill_id_deep(v)
            if found: return found

    elif isinstance(data, list):
        for item in data:
            found = _find_skill_id_deep(item)
            if found: return found
            
    return None

def parse_lsj_templates(filepath):
    data = parse_lsj(filepath)
    if not data: return {}, {}
    
    by_stats = {}
    by_map_key = {}

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
        map_key = go.get("MapKey", {}).get("value")
        stats_id = go.get("Stats", {}).get("value")
        skill_list = go.get("SkillList", [])
        template_name = go.get("TemplateName", {}).get("value")
        
        description = go.get("Description")
        display_name = go.get("DisplayName")
        trade_treasures = go.get("TradeTreasures")
        tts = []
        if trade_treasures:
            for tt in trade_treasures:
                ttem = tt.get("TreasureItem")
                if ttem:
                    tts.append(ttem.get("value"))

        treasures = go.get("Treasures")
        ts = []
        if treasures:
            for t in treasures:
                tem = t.get("TreasureItem")
                if tem:
                    ts.append(tem.get("value"))

        icon = go.get("Icon", {}).get("value")

        if "attribute" in go:
            attrs = go["attribute"]
            if isinstance(attrs, dict): attrs = [attrs]
            for a in attrs:
                aid = a.get("id")
                if not map_key and aid == "MapKey": map_key = a.get("value")
                if not stats_id and aid == "Stats": stats_id = a.get("value")
                if not description and aid == "Description": description = a
                if not display_name and aid == "DisplayName": display_name = a
                if not icon and aid == "Icon": icon = a.get("value")

        if not map_key and not stats_id:
            continue

        final_obj = {}
        if map_key:
            final_obj["MapKey"] = map_key
        if stats_id:
            final_obj["Stats"] = stats_id
        if description:
            final_obj["Description"] = description
        if display_name:
            final_obj["DisplayName"] = display_name
        if icon:
            final_obj["Icon"] = icon
        if tts:
            final_obj["TradeTreasures"] = tts
        if ts:
            final_obj["Treasures"] = ts
        if skill_list:
            final_obj["SkillList"] = skill_list
        if template_name:
            final_obj["TemplateName"] = template_name
        if go.get("LevelOverride"):
            final_obj["LevelOverride"] = go.get("LevelOverride")
        if go.get("Transform"):
            final_obj["Transform"] = go.get("Transform")
        if go.get("Tags"):
            final_obj["Tags"] = go.get("Tags")
        if go.get("DefaultState"):
            final_obj["DefaultState"] = go.get("DefaultState").get("value")
        if go.get("Type"):
            final_obj["Type"] = go.get("Type").get("value")
        if go.get("ItemList"):
            final_obj["ItemList"] = go.get("ItemList")
        if go.get("OnUsePeaceActions"):
            final_obj["OnUsePeaceActions"] = go.get("OnUsePeaceActions")
        if go.get("InventoryList"):
            final_obj["InventoryList"] = go.get("InventoryList")

        peace_actions = go.get("OnUsePeaceActions")
        if peace_actions:
            skill_id = _find_skill_id_deep(peace_actions)
            if skill_id:
                final_obj["SkillID"] = skill_id

        if stats_id: by_stats[stats_id] = final_obj
        if map_key: by_map_key[map_key] = final_obj

    return by_stats, by_map_key