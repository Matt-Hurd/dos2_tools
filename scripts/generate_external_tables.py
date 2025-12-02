import os
import re
import csv
import io
import argparse
from copy import deepcopy

from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_lsj_templates, parse_stats_txt
from dos2_tools.core.localization import load_localization_data
from dos2_tools.core.stats_engine import resolve_all_stats

EXTERNAL_TABLES = ["ST_AllPotions", "ST_Ingredients", "ST_RareIngredient", "ST_Trader_WeaponNormal", "ST_Trader_ArmorNormal", "ST_Trader_ClothArmor"]
MAX_SIMULATION_LEVEL = 16 

# --- HELPERS ---

class GlobalIDGenerator:
    def __init__(self):
        self.count = 0
    
    def get_next(self):
        self.count += 1
        return f"group_{self.count}"

# --- DATA CLASSES ---

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

# --- PARSER ---

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

# --- EXPORTER (FLATTENED) ---

class DropTableExporter:
    def __init__(self, global_id_gen):
        self.id_gen = global_id_gen
        self.seen_identifiers = set() 

    def get_uid(self):
        return self.id_gen.get_next()

    def clean_label(self, text):
        text = text.replace("ST_", "").replace("I_", "")
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        return text.replace("_", " ").strip()

    def get_qty_display(self, node, override=None):
        min_q = node.min_qty if override is None else override
        max_q = node.max_qty if override is None else override
        if node.type in ["Item", "Link", "Category"] and override is None:
            min_q = 1; max_q = 1
        return f"{min_q}" if min_q == max_q else f"{min_q}-{max_q}"

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

    def get_table_rows(self, node):
        if not node: return ""
        node_copy = deepcopy(node)
        
        output_lines = []

        # 1. Guaranteed Items (Recursive guarantee extraction)
        guaranteed_items = self.extract_guaranteed(node_copy)
        for entry in guaranteed_items:
            # These are simple items found recursively
            row_text = self.render_simple_item_row(entry['node'], qty_override=entry['qty'], force_rarity="Always")
            if row_text: output_lines.append(row_text)

        # 2. Process Remaining Pools
        for pool in node_copy.children:
            # CHECK: If the Pool is 100% chance, we FLATTEN it.
            # (Unless it selects >1, which implies multiple items, but we'll flatten that too as multiple rolls)
            if pool.chance >= 0.99:
                # Flatten: Render the pool's children as top-level rows
                for child in sorted(pool.children, key=lambda x: x.chance, reverse=True):
                    row = self.render_promoted_child_row(child, pool_min_qty=pool.min_qty)
                    if row: output_lines.append(row)
            else:
                # Not 100% -> Keep it as a wrapper Group so user sees the chance
                pool_text = self.render_pool_as_group(pool)
                if pool_text: output_lines.append(pool_text)
            
        return "\n".join(output_lines)

    def render_simple_item_row(self, node, qty_override=None, force_rarity=None):
        """Renders a standard Item row (no expansion)."""
        name = self._get_display_name(node)
        if not name: return None
        
        qty = self.get_qty_display(node, qty_override)
        rarity = force_rarity if force_rarity else f"{node.chance:.1%}"
        if node.chance > 0.99: rarity = "100%"
        
        return f"{{{{TradeRowItem|name={name}|quantity={qty}|rarity={rarity}}}}}"

    def render_promoted_child_row(self, node, pool_min_qty=1):
        """
        Renders a node that was inside a pool but is now being promoted to Top Level.
        If it's an Item -> TradeRowItem.
        If it's a Category/Group -> TradeRowGroup (Expandable).
        """
        name = self._get_display_name(node)
        if not name: return None
        
        qty = self.get_qty_display(node, pool_min_qty)
        rarity = f"{node.chance:.1%}"
        if node.chance > 0.99: rarity = "100%"

        is_complex = (node.type in ["Category", "Table", "Table_Cycle"])

        if is_complex:
            # It's a Category (e.g. "Healing Potion"). 
            # Since it's now top level, we want it to be an Expandable Group Row.
            return self.render_standalone_group(node, name, qty, rarity)
        else:
            # It's a simple item.
            return f"{{{{TradeRowItem|name={name}|quantity={qty}|rarity={rarity}}}}}"

    def render_pool_as_group(self, pool):
        """Renders a Pool that needs to stay a group (because chance < 100%)."""
        pool_uid = self.get_uid()
        child_rows = []
        
        for child in sorted(pool.children, key=lambda x: x.chance, reverse=True):
            # These are strictly children, so they are always TradeRowChild
            c_text = self.render_group_child(child, parent_uid=pool_uid)
            if c_text: child_rows.append(c_text)
        
        if not child_rows: return None

        qty = self.get_qty_display(pool)
        chance = f"{pool.chance:.1%}"
        
        out = []
        out.append(f"{{{{TradeRowGroup|id={pool_uid}|name=Selection Pool (Selects {qty})|quantity={qty}|rarity={chance}}}}}")
        out.extend(child_rows)
        return "\n".join(out)

    def render_standalone_group(self, node, name, qty, rarity):
        """
        Renders a Category/Table as a Top-Level TradeRowGroup.
        This iterates the Category's internal items to create TradeRowChild rows.
        """
        uid = self.get_uid()
        children_lines = []
        
        # 1. Category Items
        if node.type == "Category" and node.items:
             for i in node.items:
                 if i['name'] not in self.seen_identifiers:
                     self.seen_identifiers.add(i['name'])
                     c_name = f"[[{i['name']}]]"
                     c_rar = f"{i['rel']:.1%}"
                     children_lines.append(f"{{{{TradeRowChild|id={uid}|name={c_name}|quantity=1|rarity={c_rar}}}}}")
        
        # 2. Table/Cycle Children (Nested sub-tables)
        elif node.type in ["Table", "Table_Cycle"] and node.children:
             # This is a complex nesting scenario. 
             # For simplicity in this structure, we treat immediate children as row children.
             for pool in node.children:
                p_push = (pool.chance >= 0.99 and len(pool.children)==1)
                for kid in sorted(pool.children, key=lambda x:x.chance, reverse=True):
                    c_text = self.render_group_child(kid, parent_uid=uid, qty_override=pool.min_qty if p_push else None)
                    if c_text: children_lines.append(c_text)

        if not children_lines: return None # Don't render empty groups
        
        out = []
        out.append(f"{{{{TradeRowGroup|id={uid}|name={name}|quantity={qty}|rarity={rarity}}}}}")
        out.extend(children_lines)
        return "\n".join(out)

    def render_group_child(self, node, parent_uid, qty_override=None):
        """Renders a standard child row (indent). Handles complex children by nesting."""
        name = self._get_display_name(node)
        if not name: return None

        qty = self.get_qty_display(node, qty_override)
        rarity = f"{node.chance:.1%}"
        
        # If the child itself is complex (e.g. a table inside a pool), 
        # we can't do Group-inside-Group easily. We use the text-block expansion (NestedContainer).
        is_complex = (node.type in ["Category", "Table", "Table_Cycle"])
        
        if is_complex:
            nested_block = self.render_nested_text_block(node)
            if not nested_block: return None
            return f"{{{{TradeRowChild|id={parent_uid}|name={nested_block}|quantity={qty}|rarity={rarity}}}}}"
        else:
            return f"{{{{TradeRowChild|id={parent_uid}|name={name}|quantity={qty}|rarity={rarity}}}}}"

    def _get_display_name(self, node):
        if node.type in ["Item", "Link"]:
            if node.name in self.seen_identifiers: return None
            self.seen_identifiers.add(node.name)
            
        clean = self.clean_label(node.name)
        if node.type == "Link": clean = f"[[{node.name}]]"
        
        if node.type == "Category":
             clean = f"<span style='color:#a87b00; font-weight:bold;'>[CAT]</span> {clean}"
        elif node.type in ["Table", "Table_Cycle"]:
             clean = f"'''{clean}'''"
             
        return clean

    def render_nested_text_block(self, node):
        """
        Used when a complex item is DEEP inside a structure and cannot be its own RowGroup.
        Returns {{TradeNestedContainer}} string.
        """
        lines = []
        if node.type == "Category" and node.items:
             for i in node.items:
                 if i['name'] not in self.seen_identifiers:
                     self.seen_identifiers.add(i['name'])
                     lines.append(f"{{{{TradeNestedLine|name=[[{i['name']}]]|quantity=1|rarity={i['rel']:.1%}}}}}")
        elif node.type in ["Table", "Table_Cycle"] and node.children:
            for pool in node.children:
                p_push = (pool.chance >= 0.99 and len(pool.children)==1)
                for kid in sorted(pool.children, key=lambda x:x.chance, reverse=True):
                    if kid.name in self.seen_identifiers: continue
                    self.seen_identifiers.add(kid.name)
                    k_name = self.clean_label(kid.name)
                    if kid.type == "Link": k_name = f"[[{kid.name}]]"
                    if kid.type in ["Table", "Category"]: k_name = f"'''{k_name}''' (Group)"
                    k_qty = self.get_qty_display(kid, pool.min_qty if p_push else None)
                    k_chance = f"{kid.chance:.1%}"
                    lines.append(f"{{{{TradeNestedLine|name={k_name}|quantity={k_qty}|rarity={k_chance}}}}}")

        if not lines: return None
        return f"{{{{TradeNestedContainer|name={self.clean_label(node.name)}|content={''.join(lines)}}}}}"

# --- MAIN ---

def generate_header(table_id, clean_name):
    return f"""The '''{clean_name}''', also known as '''{table_id}''' is a leveled [[Treasure Table]].

=== Drop Table ===
''{{{{Transcludeable}}}}''
<onlyinclude>"""

def generate_footer():
    return """</onlyinclude>

[[Category:Drop tables]]
[[Category:Leveled drop tables]]
[[Category:Subtables]]"""

def main():
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Data...")
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_s = {}
    for f in stats_files: raw_s.update(parse_stats_txt(f))
    final_s = resolve_all_stats(raw_s)
    stats_mgr = StatsManager(final_s)
    
    tp = TreasureParser(stats_mgr)
    tt = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt:
        with open(f,'r',encoding='utf-8',errors='replace') as fo: tp.load_data(fo.read())
        
    for table_id in EXTERNAL_TABLES:
        print(f"Processing {table_id}...")
        
        id_gen = GlobalIDGenerator()
        
        logic_snapshots = []
        for lvl in range(1, MAX_SIMULATION_LEVEL + 1):
            root = tp.build_loot_tree(table_id, lvl)
            opt_root = tp.flatten_wrappers(root)
            logic_snapshots.append({'lvl': lvl, 'tree': opt_root})

        # Logic comparison for range collapsing
        dummy_gen = GlobalIDGenerator()
        collapsed_ranges = []
        last_dump = None
        s_lvl = 1
        
        for entry in logic_snapshots:
            d_exp = DropTableExporter(GlobalIDGenerator())
            dump = d_exp.get_table_rows(entry['tree'])
            
            if entry['lvl'] == 1:
                last_dump = dump
                continue
            
            if dump != last_dump:
                collapsed_ranges.append({'s': s_lvl, 'e': entry['lvl'] - 1, 'tree': logic_snapshots[s_lvl-1]['tree']})
                s_lvl = entry['lvl']
                last_dump = dump
        
        collapsed_ranges.append({'s': s_lvl, 'e': MAX_SIMULATION_LEVEL, 'tree': logic_snapshots[s_lvl-1]['tree']})

        final_wikitext = []
        clean_name = DropTableExporter(id_gen).clean_label(table_id)
        
        final_wikitext.append(generate_header(table_id, clean_name))
        
        for r in collapsed_ranges:
            exporter = DropTableExporter(id_gen)
            rows = exporter.get_table_rows(r['tree'])
            
            if not rows: continue

            label = f"Level {r['s']} - {r['e']}" if r['s'] != r['e'] else f"Level {r['s']}"
            if r['e'] == MAX_SIMULATION_LEVEL:
                label = f"Level {r['s']}+"
            
            final_wikitext.append(f"=== {label} ===")
            final_wikitext.append("{{TradeTableHead}}")
            final_wikitext.append(rows)
            final_wikitext.append("{{TradeTableBottom}}")
            final_wikitext.append("")
            
        final_wikitext.append(generate_footer())
        
        out_str = "\n".join(final_wikitext)
        fname = f"treasure_table_wikitext/{clean_name.replace(' ','_')}_DropTable.wikitext"
        os.makedirs(os.path.dirname(fname), exist_ok=True)
        with open(fname,'w',encoding='utf-8') as f: f.write(out_str)
        print(f"Created {fname}")

if __name__ == "__main__":
    main()