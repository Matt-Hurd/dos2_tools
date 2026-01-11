import os
import json
import re
import csv
import io
import argparse
from copy import deepcopy
from collections import defaultdict

from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_stats_txt
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.formatters import sanitize_filename

MAX_SIMULATION_LEVEL = 20

class StatsManager:
    def __init__(self, all_stats):
        self.stats = all_stats
        self.category_map = {}
        self.build_category_map()

    def build_category_map(self):
        for stat_name, data in self.stats.items():
            cat = data.get("ObjectCategory")
            if cat:
                if cat not in self.category_map: self.category_map[cat] = []
                self.category_map[cat].append({
                    'id': stat_name,
                    'min_level': int(data.get("MinLevel", 0)),
                    'priority': int(data.get("Priority", 1)),
                })

    def get_items_for_category(self, category_name, current_level):
        if category_name not in self.category_map: return None
        return [i for i in self.category_map[category_name] if i['min_level'] <= current_level]

    def is_valid_item_id(self, item_name):
        return item_name in self.stats or (item_name.startswith("I_") and item_name[2:] in self.stats)
    
    def get_item_min_level(self, item_name):
        lookup = item_name[2:] if item_name.startswith("I_") else item_name
        if lookup in self.stats:
            return int(self.stats[lookup].get("MinLevel", 0))
        return 0

class LootNode:
    def __init__(self, name, node_type, chance=1.0, min_qty=1, max_qty=1):
        self.name = name
        self.type = node_type 
        self.chance = chance
        self.min_qty = min_qty
        self.max_qty = max_qty
        self.children = []
        self.items = []

    def add_child(self, node):
        self.children.append(node)

class TreasureParser:
    def __init__(self, stats_manager):
        self.tables = {}
        self.stats_mgr = stats_manager
        self.visited_cache = {}

    def parse_csv_line(self, line):
        f = io.StringIO(line)
        try: return next(csv.reader(f, delimiter=',', quotechar='"'))
        except StopIteration: return []

    def load_data(self, data_str):
        current_table = None
        current_s = None; current_e = None
        
        for line in data_str.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'): continue
            
            if line.startswith('new treasuretable'):
                match = re.search(r'new treasuretable "([^"]+)"', line)
                if match:
                    current_table = match.group(1)
                    self.tables[current_table] = []
                    current_s = None; current_e = None
            elif line.startswith('new subtable') and current_table:
                match = re.search(r'new subtable "([^"]+)"', line)
                if match:
                    self.tables[current_table].append({'type': 'group', 'rule': match.group(1), 'items': []})
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

    def get_real_table_id(self, table_id):
        if table_id in self.tables: return table_id
        if table_id.startswith("T_") and table_id[2:] in self.tables: return table_id[2:]
        return None

    def build_loot_tree(self, table_id, level, visited=None):
        if visited is None: visited = set()
        real_id = self.get_real_table_id(table_id)
        if not real_id: return None
        
        root = LootNode(real_id, "Table")
        if real_id not in self.tables: return root
        
        for group in self.tables[real_id]:
            min_q, max_q, chance = self.parse_qty_rule(group['rule'])
            if chance <= 0: continue
            
            pool = LootNode("Subtable", "Pool", chance, min_q, max_q)
            valid_items = []
            
            for item in group['items']:
                if item['s'] and level < item['s']: continue
                if item['e'] and level > item['e']: continue

                if self.stats_mgr.is_valid_item_id(item['name']):
                    item_min_lvl = self.stats_mgr.get_item_min_level(item['name'])
                    if level < item_min_lvl:
                        continue

                valid_items.append(item)
                
            total_freq = sum(i['freq'] for i in valid_items)
            if total_freq == 0: continue
            
            for item in valid_items:
                rel = item['freq'] / total_freq
                child_id = self.get_real_table_id(item['name'])
                
                if child_id:
                    if child_id in visited:
                        continue 
                    else:
                        new_v = visited.copy(); new_v.add(child_id)
                        child_tree = self.build_loot_tree(child_id, level, new_v)
                        if child_tree:
                            child_tree.chance = rel
                            pool.add_child(child_tree)
                else:
                    ntype = "Item" if self.stats_mgr.is_valid_item_id(item['name']) else "Category"
                    node = LootNode(item['name'], ntype, rel)
                    
                    if ntype == "Category":
                        cat_items = self.stats_mgr.get_items_for_category(item['name'], level)
                        if cat_items:
                            tot_p = sum(c['priority'] for c in cat_items)
                            if tot_p > 0:
                                for c in cat_items:
                                    node.items.append({'name': c['id'], 'rel': c['priority']/tot_p})
                    
                    pool.add_child(node)
            root.add_child(pool)
        return root

    def flatten_probabilities(self, node, current_prob=1.0, current_min=1, current_max=1):
        """
        Traverses the tree to map Items to {prob, min_qty, max_qty}.
        """
        results = {}
        
        effective_prob = current_prob * node.chance
        
        # Calculate quantity for children
        next_min = current_min
        next_max = current_max

        # If this node is a Pool (Subtable), it defines how many selections are made.
        # e.g. "1,3" means we select 1 to 3 times from the child list.
        # This acts as a multiplier for the resulting item count.
        if node.type == "Pool":
            next_min = current_min * node.min_qty
            next_max = current_max * node.max_qty
        
        if node.type == "Item":
            if node.name not in results: 
                results[node.name] = {'prob': 0.0, 'min': 99999, 'max': 0}
            
            # For a leaf item, the 'current' accumulation is the result
            results[node.name]['prob'] = effective_prob
            results[node.name]['min'] = next_min
            results[node.name]['max'] = next_max

        elif node.type == "Category":
            for item in node.items:
                i_name = item['name']
                i_prob = effective_prob * item['rel']
                if i_name not in results: 
                    results[i_name] = {'prob': 0.0, 'min': 99999, 'max': 0}
                
                results[i_name]['prob'] = i_prob
                results[i_name]['min'] = next_min
                results[i_name]['max'] = next_max
        
        for child in node.children:
            child_res = self.flatten_probabilities(child, effective_prob, next_min, next_max)
            for k, v in child_res.items():
                if k not in results: 
                    results[k] = {'prob': 0.0, 'min': 99999, 'max': 0}
                
                results[k]['prob'] += v['prob']
                # If an item appears in multiple branches, we widen the range to cover all possibilities
                results[k]['min'] = min(results[k]['min'], v['min'])
                results[k]['max'] = max(results[k]['max'], v['max'])
                
        return results

def get_resolved_name(val, handle, loc_map, uuid_map):
    if handle and handle in loc_map: return loc_map[handle]
    if val:
        loc_text = get_localized_text(val, uuid_map, loc_map)
        return loc_text if loc_text else val
    return "Unknown"

def main():
    print("Initializing Item Source Mapper (with Quantity)...")
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    loc_data = load_localization_data(all_files, conf)
    loc_map = loc_data['handles']
    uuid_map = loc_data['uuids']
    
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_s = {}
    for f in stats_files: raw_s.update(parse_stats_txt(f))
    final_s = resolve_all_stats(raw_s)
    stats_mgr = StatsManager(final_s)
    
    tp = TreasureParser(stats_mgr)
    tt = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt:
        with open(f,'r',encoding='utf-8',errors='replace') as fo: tp.load_data(fo.read())

    print("Loading NPCs...")
    char_files = get_files_by_pattern(all_files, conf['patterns']['level_characters'])
    npc_map = {} 

    template_files = get_files_by_pattern(all_files, conf['patterns']['root_templates_lsj'])
    template_files.extend(get_files_by_pattern(all_files, ["Public/**/RootTemplates/_merged.lsj"]))
    root_templates = {}
    for f in template_files:
        _, by_map_key = parse_lsj_templates(f)
        root_templates.update(by_map_key)

    for f_path in char_files:
        if 'Test' in f_path or 'Develop' in f_path: continue
        _, level_objects = parse_lsj_templates(f_path)
        
        for obj_uuid, level_data in level_objects.items():
            template_uuid = level_data.get("TemplateName")
            final_data = {}
            if template_uuid and template_uuid in root_templates:
                final_data = deepcopy(root_templates[template_uuid])
            final_data.update(level_data)

            d_node = final_data.get("DisplayName")
            if not d_node: continue
            
            npc_name = get_resolved_name(d_node.get("value"), d_node.get("handle"), loc_map, uuid_map)
            if not npc_name or npc_name == "Unknown": continue

            drops = final_data.get("Treasures", [])
            if not isinstance(drops, list): drops = [drops] if drops else []
            
            trades = final_data.get("TradeTreasures", [])
            if not isinstance(trades, list): trades = [trades] if trades else []

            drops = [d for d in drops if d and d != "Empty"]
            trades = [t for t in trades if t and t != "Empty"]

            if not drops and not trades: continue

            if npc_name not in npc_map:
                npc_map[npc_name] = {'drops': set(), 'trades': set()}
            
            npc_map[npc_name]['drops'].update(drops)
            npc_map[npc_name]['trades'].update(trades)

    print(f"Found {len(npc_map)} NPCs with loot tables.")

    table_cache = {}

    def analyze_table(t_id):
        if t_id in table_cache: return table_cache[t_id]
        
        aggregated_data = {}
        
        levels_to_check = range(1, MAX_SIMULATION_LEVEL + 1, 2)
        
        for lvl in levels_to_check:
            tree = tp.build_loot_tree(t_id, lvl)
            if not tree: continue
            
            # This returns { item_id: { 'prob': float, 'min': int, 'max': int } }
            results = tp.flatten_probabilities(tree)
            
            for item, data in results.items():
                if item not in aggregated_data: 
                    aggregated_data[item] = {'prob': 0.0, 'min': 9999, 'max': 0}
                
                # Maximize probability found across levels (e.g., if at level 10 it's 100%, record that)
                aggregated_data[item]['prob'] = max(aggregated_data[item]['prob'], data['prob'])
                
                # Widen quantity range
                aggregated_data[item]['min'] = min(aggregated_data[item]['min'], data['min'])
                aggregated_data[item]['max'] = max(aggregated_data[item]['max'], data['max'])
        
        table_cache[t_id] = aggregated_data
        return aggregated_data

    item_source_map = {}

    total_npcs = len(npc_map)
    curr = 0
    
    for npc_name, tables in npc_map.items():
        curr += 1
        if curr % 100 == 0: print(f"Processing NPC {curr}/{total_npcs}...")
        
        # Helper to process drops/trades
        def process_source_type(table_list, source_key):
            for t_id in table_list:
                items_data = analyze_table(t_id)
                
                for item_id, stats in items_data.items():
                    resolved_item_name = get_resolved_name(item_id, None, loc_map, uuid_map)
                    
                    if resolved_item_name not in item_source_map:
                        item_source_map[resolved_item_name] = {'drops': [], 'sells': []}
                    
                    target_list = item_source_map[resolved_item_name][source_key]
                    exists = next((x for x in target_list if x['npc'] == npc_name), None)
                    
                    if not exists:
                        target_list.append({
                            'npc': npc_name,
                            'chance': float(f"{stats['prob']:.4f}"),
                            'min': stats['min'],
                            'max': stats['max']
                        })
                    else:
                        # If we hit the same NPC via a different table (rare), merge stats
                        exists['chance'] = max(exists['chance'], stats['prob'])
                        exists['min'] = min(exists['min'], stats['min'])
                        exists['max'] = max(exists['max'], stats['max'])

        process_source_type(tables['drops'], 'drops')
        process_source_type(tables['trades'], 'sells')

    # Sort results
    for item in item_source_map:
        item_source_map[item]['drops'].sort(key=lambda x: x['chance'], reverse=True)
        item_source_map[item]['sells'].sort(key=lambda x: x['chance'], reverse=True)

    out_file = "item_sources.json"
    print(f"Exporting to {out_file}...")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(item_source_map, f, indent=2, ensure_ascii=False)
    print("Done.")

if __name__ == "__main__":
    main()