import os
import re
import csv
import io
import argparse
from copy import deepcopy

from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_stats_txt
from dos2_tools.core.localization import load_localization_data, get_localized_text
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.formatters import sanitize_filename

EXTERNAL_TABLES = ["ST_AllPotions", "ST_Ingredients", "ST_RareIngredient", "ST_Trader_WeaponNormal", "ST_Trader_ArmorNormal", "ST_Trader_ClothArmor"]
MAX_SIMULATION_LEVEL = 16 

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
                    if child_id in EXTERNAL_TABLES:
                        pool.add_child(LootNode(item['name'], "Link", rel))
                    elif child_id in visited:
                        pool.add_child(LootNode(item['name'], "Table_Cycle", rel))
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

    def flatten_wrappers(self, node):
        if not node or not node.children: return node
        new_children = []
        for child in node.children:
            if child.type == "Pool":
                child.children = [self.flatten_wrappers(gc) for gc in child.children]
                new_children.append(child)
            else:
                new_children.append(self.flatten_wrappers(child))
        
        node.children = new_children
        if node.type == "Table" and len(node.children) == 1:
            pool = node.children[0]
            if pool.chance >= 0.99 and pool.min_qty == 1 and pool.max_qty == 1:
                if len(pool.children) == 1 and pool.children[0].type == "Table":
                    return pool.children[0]
        return node

class OSRSWikiExporter:
    def __init__(self, loc_map, uuid_map):
        self.uid_counter = 0
        self.seen_identifiers = set() 
        self.has_rendered_gold = False 
        self.loc_map = loc_map
        self.uuid_map = uuid_map

    def get_uid(self):
        self.uid_counter += 1
        return f"group_{self.uid_counter}"

    def clean_label(self, text):
        text = text.replace("ST_", "").replace("I_", "")
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        return text.replace("_", " ").strip()

    def resolve_name_link(self, raw_name):
        clean_internal = raw_name
        if clean_internal.startswith("I_"):
            clean_internal = clean_internal[2:]

        loc_text = get_localized_text(clean_internal, self.uuid_map, self.loc_map)

        if loc_text:
            safe_name = sanitize_filename(loc_text)
            return f"[[{safe_name}]]"

        return self.clean_label(raw_name)

    def get_qty_display(self, node, override=None):
        min_q = node.min_qty if override is None else override
        max_q = node.max_qty if override is None else override
        if node.type in ["Item", "Link", "Category"] and override is None:
            min_q = 1; max_q = 1
        return f"{min_q}" if min_q == max_q else f"{min_q}-{max_q}"

    def extract_trader_gold(self, node, multiplier=1):
        found_gold = None
        for pool in list(node.children):
            if pool.type != "Pool": continue
            for child in list(pool.children):
                if child.type in ["Table", "Table_Cycle"]:
                     res = self.extract_trader_gold(child, pool.min_qty * multiplier)
                     if res: found_gold = res
            for child in list(pool.children):
                clean = self.clean_label(child.name)
                is_gold = (clean == "Trader Gold") or (clean == "Gold")
                if is_gold:
                    qty_str = self.get_qty_display(child, pool.min_qty * multiplier)
                    found_gold = qty_str
                    pool.children.remove(child)
            if not pool.children: node.children.remove(pool)
        return found_gold

    def extract_guaranteed(self, node, multiplier=1):
        extracted = []
        for pool in list(node.children):
            if pool.type != "Pool": continue
            if pool.chance >= 0.99 and len(pool.children) == 1:
                child = pool.children[0]
                q = pool.min_qty * multiplier
                
                if child.type == "Table":
                     sub = self.extract_guaranteed(child, q)
                     extracted.extend(sub)
                     if not child.children: node.children.remove(pool)
                elif child.type in ["Item", "Link"]:
                    extracted.append({'node': child, 'qty': q})
                    node.children.remove(pool)
        return extracted

    def render_level_block(self, node, level):
        if not node: return None
        node_copy = deepcopy(node)
        
        raw_gold_qty = self.extract_trader_gold(node_copy)
        display_gold_qty = None
        if raw_gold_qty and not self.has_rendered_gold:
            display_gold_qty = raw_gold_qty
            self.has_rendered_gold = True

        guaranteed_rows = []
        guaranteed_items = self.extract_guaranteed(node_copy)
        for entry in guaranteed_items:
            row_text = self.render_row(entry['node'], qty_override=entry['qty'], force_rarity="Always")
            if row_text: guaranteed_rows.append(row_text)

        pool_rows = []
        for pool in node_copy.children:
            pool_text = self.render_pool(pool)
            if pool_text: pool_rows.append(pool_text)

        if not guaranteed_rows and not pool_rows and not display_gold_qty: return None

        output = []
        header_text = f"Stock (Level {level})" if level == 1 else f"New at Level {level}"
        output.append(f"=={header_text}==")
        
        if display_gold_qty:
            output.append(f"{{{{TradeTraderGold|quantity={display_gold_qty}}}}}")
            output.append("")
        
        if guaranteed_rows:
            output.append("{{TradeTableHead}}")
            output.extend(guaranteed_rows)
            output.append("{{TradeTableBottom}}")
            output.append("")

        if pool_rows:
            if guaranteed_rows or display_gold_qty: output.append(f"==={header_text} (Random)===")
            else: output.append(f"==={header_text} (Random)===")
            output.extend(pool_rows)

        return "\n".join(output)

    def render_pool(self, pool):
        new_children = []
        is_g = pool.chance >= 0.99
        push_qty = (is_g and len(pool.children) == 1)
        
        for child in sorted(pool.children, key=lambda x: x.chance, reverse=True):
            q_over = pool.min_qty if push_qty else None
            row_text = self.render_row(child, qty_override=q_over)
            if row_text: new_children.append(row_text)
                
        if not new_children: return None

        qty = self.get_qty_display(pool)
        chance = f"{pool.chance:.1%}" if pool.chance < 0.99 else "Always Available"
        
        out = []
        out.append(f"{{{{TradePoolHead|name=Selection Pool (Selects {qty})|chance={chance}}}}}")
        out.extend(new_children)
        out.append("{{TradeTableBottom}}")
        return "\n".join(out)

    def render_deep_container(self, node):
        lines = []
        
        if node.type == "Category" and node.items:
             for i in node.items:
                 if i['name'] not in self.seen_identifiers:
                     self.seen_identifiers.add(i['name'])
                     display_name = self.resolve_name_link(i['name'])
                     lines.append(f"{{{{TradeNestedLine|name={display_name}|quantity=1|rarity={i['rel']:.1%}}}}}")
                 
        elif node.type in ["Table", "Table_Cycle"] and node.children:
            for pool in node.children:
                p_is_g = pool.chance >= 0.99
                p_push = (p_is_g and len(pool.children)==1)
                for kid in sorted(pool.children, key=lambda x:x.chance, reverse=True):
                    
                    if kid.name in self.seen_identifiers: continue
                    self.seen_identifiers.add(kid.name)
                    
                    k_name = self.clean_label(kid.name)

                    if kid.type == "Item":
                        k_name = self.resolve_name_link(kid.name)
                    elif kid.type == "Link":
                        k_name = f"[[{kid.name}]]"
                    elif kid.type in ["Table", "Category"]:
                         k_name = f"'''{k_name}''' (Group)"
                    
                    k_qty = self.get_qty_display(kid, pool.min_qty if p_push else None)
                    k_chance = f"{kid.chance:.1%}"
                    lines.append(f"{{{{TradeNestedLine|name={k_name}|quantity={k_qty}|rarity={k_chance}}}}}")

        if not lines: return ""

        content_block = "".join(lines)
        return f"{{{{TradeNestedContainer|name={self.clean_label(node.name)}|content={content_block}}}}}"

    def render_row(self, node, qty_override=None, force_rarity=None):
        if node.type in ["Item", "Link"]:
            if node.name in self.seen_identifiers: return None
            self.seen_identifiers.add(node.name)

        name = self.clean_label(node.name)

        if node.type == "Item":
            name = self.resolve_name_link(node.name)
        elif node.type == "Link":
            name = f"[[{node.name}]]"

        qty = self.get_qty_display(node, qty_override)
        rarity = force_rarity if force_rarity else f"{node.chance:.1%}"
        if node.chance > 0.99: rarity = "100%"
        
        children_to_render = []
        
        if node.type == "Category" and node.items:
            for i in node.items:
                if i['name'] not in self.seen_identifiers:
                    self.seen_identifiers.add(i['name'])
                    display_name = self.resolve_name_link(i['name'])
                    children_to_render.append({
                        'name': display_name, 
                        'qty': '1', 
                        'rar': f"{i['rel']:.1%}"
                    })
            name = f"<span style='color:#a87b00; font-weight:bold;'>[CAT]</span> {name}"

        elif node.type in ["Table", "Table_Cycle"] and node.children:
            for pool in node.children:
                p_is_g = pool.chance >= 0.99
                p_push = (p_is_g and len(pool.children)==1)
                
                for kid in sorted(pool.children, key=lambda x:x.chance, reverse=True):
                    
                    if kid.type in ["Table", "Table_Cycle", "Category"]:
                         deep_tmpl = self.render_deep_container(kid)
                         if deep_tmpl:
                             children_to_render.append({'name': deep_tmpl, 'qty': '1', 'rar': f"{kid.chance:.1%}"})
                    else:
                        if kid.name not in self.seen_identifiers:
                            self.seen_identifiers.add(kid.name)
                            k_name = self.clean_label(kid.name)

                            if kid.type == "Item":
                                k_name = self.resolve_name_link(kid.name)
                            elif kid.type == "Link":
                                k_name = f"[[{kid.name}]]"

                            k_qty = self.get_qty_display(kid, pool.min_qty if p_push else None)
                            children_to_render.append({'name': k_name, 'qty': k_qty, 'rar': f"{kid.chance:.1%}"})
            
            name = f"'''{name}'''"

        if (node.type in ["Category", "Table", "Table_Cycle"]) and not children_to_render:
            return None

        if not children_to_render:
            return f"{{{{TradeRowItem|name={name}|quantity={qty}|rarity={rarity}}}}}"
        else:
            uid = self.get_uid()
            out = []
            out.append(f"{{{{TradeRowGroup|id={uid}|name={name}|quantity={qty}|rarity={rarity}}}}}")
            for c in children_to_render:
                out.append(f"{{{{TradeRowChild|id={uid}|name={c['name']}|quantity={c['qty']}|rarity={c['rar']}}}}}")
            return "\n".join(out)

def find_npc_trade_id(npc_name, all_files, conf, loc_map, uuid_map):
    char_files = get_files_by_pattern(all_files, conf['patterns']['level_characters'])
    found = []
    print(f"Scanning level files for {npc_name}...")
    for f in char_files:
        if 'Test' in f: continue
        _, objects = parse_lsj_templates(f)
        for _, data in objects.items():
            d_node = data.get("DisplayName")
            final = "Unknown"
            if d_node:
                v = d_node.get("value")
                h = d_node.get("handle")
                if h: final = loc_map.get(h, v)
                elif v: final = v
            if final and npc_name.lower() in final.lower():
                found.extend(data.get("TradeTreasures", []))
    return list(set(found))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("npc_name")
    args = parser.parse_args()
    
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Data...")
    loc = load_localization_data(all_files, conf)
    
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_s = {}
    for f in stats_files: raw_s.update(parse_stats_txt(f))
    final_s = resolve_all_stats(raw_s)
    stats_mgr = StatsManager(final_s)
    
    tp = TreasureParser(stats_mgr)
    tt = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt:
        with open(f,'r',encoding='utf-8',errors='replace') as fo: tp.load_data(fo.read())
        
    ids = find_npc_trade_id(args.npc_name, all_files, conf, loc['handles'], loc['uuids'])
    valid_ids = sorted(list(set([x for x in ids if x])))

    if not valid_ids:
        print("No trade ID found.")
        return
    
    print(f"Generating merged table for {valid_ids}...")
    exporter = OSRSWikiExporter(loc['handles'], loc['uuids'])
    final_wikitext = []

    for lvl in range(1, MAX_SIMULATION_LEVEL + 1):
        master_node = LootNode("Master_Merged", "Table")

        for trade_id in valid_ids:
            root = tp.build_loot_tree(trade_id, lvl)
            if root:
                opt_root = tp.flatten_wrappers(root)
                master_node.children.extend(opt_root.children)

        block = exporter.render_level_block(master_node, lvl)
        if block:
            final_wikitext.append(block)
            print(f" > Generated Level {lvl} (Merged)")

    full_text = "\n\n".join(final_wikitext)
    fname = f"{args.npc_name.replace(' ','_')}_Trade.wikitext"
    with open(fname,'w',encoding='utf-8') as f: f.write(full_text)
    print(f"Done: {fname}")

if __name__ == "__main__":
    main()