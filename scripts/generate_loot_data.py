import os
import re
import csv
import io
import json
from collections import defaultdict

from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import load_localization_data, get_localized_text

FORCE_SHARED_PREFIXES = ["ST_Gen", "ST_Trader", "Reward_", "T_Reward", "ST_Humanoid"]
IGNORE_TABLES = ["Empty", "Generic"]

class StatsManager:
    def __init__(self, all_stats):
        self.stats = all_stats
        self.category_map = defaultdict(list)
        self.build_category_map()

    def build_category_map(self):
        for stat_name, data in self.stats.items():
            cat = data.get("ObjectCategory")
            if cat:
                self.category_map[cat].append({
                    'id': stat_name,
                    'min_level': int(data.get("MinLevel", 0)),
                })

    def get_item_min_level(self, item_name):
        lookup = item_name[2:] if item_name.startswith("I_") else item_name
        if lookup in self.stats:
            return int(self.stats[lookup].get("MinLevel", 0))
        return 0

    def get_category_info(self, cat_name):
        items = self.category_map.get(cat_name)
        if not items: return None, None
        
        is_equipment = cat_name in [
            "Amulet", "Axe", "Belt", "Bow", "ClothBoots", "ClothGloves", 
            "ClothHelmet", "ClothLowerBody", "ClothUpperBody", "Club", 
            "Crossbow", "Dagger", "HeavyBoots", "HeavyGloves", "HeavyHelmet", 
            "HeavyLowerBody", "HeavyUpperBody", "LightBoots", "LightGloves", 
            "LightHelmet", "LightLowerBody", "LightUpperBody", "MageBoots", 
            "MageGloves", "MageHelmet", "MageLowerBody", "MageUpperBody", 
            "REFERENCE_HeavyBoots", "REFERENCE_HeavyGloves", "REFERENCE_HeavyHelmet", 
            "REFERENCE_HeavyLowerBody", "REFERENCE_HeavyUpperBody", "REFERENCE_LightBoots", 
            "REFERENCE_LightGloves", "REFERENCE_LightHelmet", "REFERENCE_LightLowerBody", 
            "REFERENCE_LightUpperBody", "REFERENCE_MageBoots", "REFERENCE_MageGloves", 
            "REFERENCE_MageHelmet", "REFERENCE_MageLowerBody", "REFERENCE_MageUpperBody", 
            "Ring", "Spear", "StaffAir", "StaffFire", "StaffPoison", "StaffWater", 
            "Sword", "Shield", "TwoHandedAxe", "TwoHandedMace", "TwoHandedSword", 
            "WandAir", "WandFire", "WandPoison", "WandWater",
        ]
        
        if is_equipment:
            return "Equipment", []
        
        sorted_items = sorted(items, key=lambda x: (x['min_level'], x['id']))
        return "Collection", sorted_items

class TreasureParser:
    def __init__(self):
        self.tables = {}

    def parse_csv_line(self, line):
        f = io.StringIO(line)
        try: return next(csv.reader(f, delimiter=',', quotechar='"'))
        except StopIteration: return []

    def parse_qty_rule(self, drop_rule):
        if drop_rule.startswith('-'):
            val = abs(int(drop_rule))
            return val, val, 1.0
        pairs = drop_rule.split(';')
        min_q = 999; max_q = 0; total_w = 0; success_w = 0
        for p in pairs:
            if ',' not in p: continue
            try:
                c, w = map(int, p.split(','))
                total_w += w
                if c > 0:
                    success_w += w
                    min_q = min(min_q, c)
                    max_q = max(max_q, c)
            except: continue
        if total_w == 0: return 0,0,0
        if min_q == 999: min_q = 0
        return min_q, max_q, success_w/total_w

    def load_data(self, data_str):
        current_table = None
        current_s = None 
        current_e = None
        
        for line in data_str.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'): continue
            
            if line.startswith('new treasuretable'):
                match = re.search(r'new treasuretable "([^"]+)"', line)
                if match:
                    current_table = match.group(1)
                    self.tables[current_table] = []
                    current_s = None
                    current_e = None
            elif line.startswith('new subtable') and current_table:
                match = re.search(r'new subtable "([^"]+)"', line)
                if match:
                    self.tables[current_table].append({'type': 'group', 'rule': match.group(1), 'items': []})
                    current_s = None
                    current_e = None
            elif line.startswith('StartLevel'):
                m = re.search(r'StartLevel "([^"]+)"', line)
                if m: current_s = int(m.group(1))
            elif line.startswith('EndLevel'):
                m = re.search(r'EndLevel "([^"]+)"', line)
                if m: current_e = int(m.group(1))
            elif line.startswith('object category') and current_table:
                parts = self.parse_csv_line(line.replace('object category ', ''))
                if parts and self.tables[current_table]:
                    self.tables[current_table][-1]['items'].append({
                        'name': parts[0],
                        'freq': int(parts[1]) if len(parts) > 1 else 1,
                        's': current_s, 'e': current_e
                    })
                    
class LootGraph:
    def __init__(self):
        self.edges = defaultdict(list)
        self.reverse_edges = defaultdict(list)
        self.tables = {} 
        self.normalized_ids = {} 

    def add_table(self, table_id, raw_groups):
        self.tables[table_id] = raw_groups
        clean = self.clean_id(table_id)
        self.normalized_ids[clean] = table_id
        for group in raw_groups:
            for item in group['items']:
                self.edges[table_id].append(item['name'])

    def clean_id(self, name):
        if name.startswith("T_"): return name[2:]
        return name

    def resolve_real_id(self, name):
        if name in self.tables: return name
        if name.startswith("T_") and name[2:] in self.tables: return name[2:]
        clean = self.clean_id(name)
        if clean in self.normalized_ids: return self.normalized_ids[clean]
        return None

    def build_graph(self):
        final_edges = defaultdict(list)
        for parent, children in self.edges.items():
            for child_ref in children:
                real_child_id = self.resolve_real_id(child_ref)
                if real_child_id:
                    final_edges[parent].append(real_child_id)
                    self.reverse_edges[real_child_id].append(parent)
        self.edges = final_edges

    def get_shared_tables(self):
        shared = set()
        for t_id in self.tables:
            # Add denylist
            if "Skillbook" in t_id:
                continue
            parents = self.reverse_edges.get(t_id, [])
            unique_parents = set(parents)
            if len(unique_parents) > 1:
                shared.add(t_id)
                continue
            for p in FORCE_SHARED_PREFIXES:
                if t_id.startswith(p) or (t_id.startswith("T_") and t_id[2:].startswith(p)):
                    shared.add(t_id)
                    break
        return shared

def clean_lua_string(name):
    return name.replace("'", "\\'")

def generate_table_page(table_id):
    return f"""{{{{InfoboxLootTable|name={table_id}}}}}
The '''{table_id}''' is a shared loot table.

== Contents ==
{{{{NPC Loot|table_id={table_id}|mode=full}}}}

[[Category:Loot Tables]]"""

def main():
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Localization...")
    loc_data = load_localization_data(all_files, conf)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']

    print("Parsing Stats...")
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_s = {}
    for f in stats_files: raw_s.update(parse_stats_txt(f))
    final_s = resolve_all_stats(raw_s)
    stats_mgr = StatsManager(final_s)

    print("Parsing Treasure Tables...")
    parser = TreasureParser()
    tt = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt:
        with open(f,'r',encoding='utf-8',errors='replace') as fo: parser.load_data(fo.read())

    graph = LootGraph()
    for tid, groups in parser.tables.items():
        graph.add_table(tid, groups)
    graph.build_graph()
    
    shared_tables = graph.get_shared_tables()
    print(f"Identified {len(shared_tables)} shared tables.")

    lines = []
    lines.append("return {")
    
    for t_id, groups in parser.tables.items():
        if not groups or t_id in IGNORE_TABLES: continue
        
        safe_tid = clean_lua_string(t_id)
        if safe_tid.startswith("T_"): safe_tid = safe_tid[2:]

        is_shared_str = "true" if t_id in shared_tables else "false"
        lines.append(f"['{safe_tid}'] = {{ IsShared={is_shared_str}, Groups={{")
        
        for grp in groups:
            min_q, max_q, chance = parser.parse_qty_rule(grp['rule'])
            if chance <= 0: continue
            
            lines.append(f"  {{ Chance={chance:.4f}, Min={min_q}, Max={max_q}, Items={{")
            
            total_freq = sum(i['freq'] for i in grp['items'])
            if total_freq > 0:
                for item in grp['items']:
                    rel_chance = item['freq'] / total_freq
                    internal_name = item['name']
                    
                    stat_min = stats_mgr.get_item_min_level(internal_name)
                    table_min = item['s'] if item['s'] is not None else 0
                    
                    actual_min = max(stat_min, table_min)
                    
                    s_lvl = str(actual_min) if actual_min > 1 else "nil"
                    e_lvl = item['e'] if item['e'] else "nil"
                    
                    extra_data_list = []
                    cat_type, cat_items = stats_mgr.get_category_info(internal_name)
                    
                    display_name = internal_name
                    
                    if internal_name.startswith("I_"):
                        clean_item_id = internal_name[2:]
                        
                        loc_text = get_localized_text(clean_item_id, uuid_map, loc_map)
                        
                        if not loc_text:
                            with open("unique_items.json", 'r', encoding='utf-8') as f:
                                items_data = json.load(f)
                                item_entry = items_data.get(clean_item_id)
                                if item_entry:
                                    loc_text = item_entry.get("display_name")
                        
                        display_name = loc_text if loc_text else clean_item_id
                        extra_data_list.append("IsItem=true")
                    elif internal_name.startswith("T_"):
                        display_name = internal_name[2:]
                    else:
                        display_name = internal_name

                    safe_display_name = clean_lua_string(display_name)

                    if cat_type == "Equipment":
                        extra_data_list.append("IsEquip=true")
                    elif cat_type == "Collection" and cat_items:
                        tips = []
                        for ci in cat_items:
                            c_id = ci['id']
                            c_lookup = c_id
                            if c_id.startswith("I_"): c_lookup = c_id[2:]
                            
                            c_loc = get_localized_text(c_lookup, uuid_map, loc_map)
                            c_name = c_loc if c_loc else c_lookup
                            
                            c_name = clean_lua_string(c_name)
                            
                            lvl_str = f" ({ci['min_level']})" if ci['min_level'] > 1 else ""
                            tips.append(f"{c_name}{lvl_str}")
                        
                        tooltip_str = ", ".join(tips)
                        extra_data_list.append(f"Tooltip='{tooltip_str}'")
                    
                    extra_data_str = ", " + ", ".join(extra_data_list) if extra_data_list else ""

                    lines.append(f"    {{ '{safe_display_name}', {rel_chance:.4f}, {s_lvl}, {e_lvl}{extra_data_str} }},")
            
            lines.append("  }, },")
        lines.append("} },")
        
    lines.append("}")
    
    with open("Module_LootData.lua", "w", encoding='utf-8') as f:
        f.write("\n".join(lines))
    print("Generated Module_LootData.lua")

    out_dir = "loot_wikitext"
    if not os.path.exists(out_dir): os.makedirs(out_dir)
    for t_id in shared_tables:
        safe_name = t_id.replace(" ", "_")
        with open(os.path.join(out_dir, f"{safe_name}.wikitext"), 'w') as f:
            f.write(generate_table_page(t_id))

if __name__ == "__main__":
    main()