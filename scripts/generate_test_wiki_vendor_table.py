import json
import re
import csv
import io
import os

from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats

EXTERNAL_TABLES = [
    "ST_AllPotions",
    "ST_Ingredients",
    "ST_RareIngredient",
]

class StatsManager:
    def __init__(self, all_stats):
        self.stats = all_stats
        self.category_map = {}
        self.build_category_map()

    def build_category_map(self):
        for stat_name, data in self.stats.items():
            cat = data.get("ObjectCategory")
            if cat:
                if cat not in self.category_map:
                    self.category_map[cat] = []
                self.category_map[cat].append({
                    'id': stat_name,
                    'min_level': int(data.get("MinLevel", 0)),
                    'priority': int(data.get("Priority", 1)),
                    'type': data.get("type", "Unknown")
                })

    def get_items_for_category(self, category_name, current_level):
        if category_name not in self.category_map: return None
        candidates = self.category_map[category_name]
        valid_items = []
        for item in candidates:
            if item['min_level'] > current_level: continue
            valid_items.append(item)
        return valid_items

    def is_valid_item_id(self, item_name):
        if item_name in self.stats: return True
        if item_name.startswith("I_") and item_name[2:] in self.stats: return True
        return False
    
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
        reader = csv.reader(f, delimiter=',', quotechar='"')
        try: return next(reader)
        except StopIteration: return []

    def load_data(self, data_str):
        current_table_id = None
        current_drop_count_rule = "1,1"
        current_start_level = None; current_end_level = None
        lines = data_str.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//'): continue

            if line.startswith('new treasuretable'):
                match = re.search(r'new treasuretable "([^"]+)"', line)
                if match:
                    current_table_id = match.group(1)
                    self.tables[current_table_id] = []
                    current_drop_count_rule = "1,1"
                    current_start_level = None; current_end_level = None

            elif line.startswith('new subtable'):
                match = re.search(r'new subtable "([^"]+)"', line)
                if match:
                    current_drop_count_rule = match.group(1)
                    current_start_level = None; current_end_level = None
                    self.tables[current_table_id].append({
                        'type': 'group_header',
                        'drop_count': current_drop_count_rule
                    })

            elif line.startswith('StartLevel'):
                match = re.search(r'StartLevel "([^"]+)"', line)
                if match: current_start_level = int(match.group(1))
            elif line.startswith('EndLevel'):
                match = re.search(r'EndLevel "([^"]+)"', line)
                if match: current_end_level = int(match.group(1))

            elif line.startswith('object category'):
                if current_table_id:
                    clean_line = line.replace('object category ', '')
                    parts = self.parse_csv_line(clean_line)
                    if not parts: continue
                    self.tables[current_table_id].append({
                        'type': 'item',
                        'name': parts[0],
                        'frequency': int(parts[1]) if len(parts) > 1 else 1,
                        'start_level': current_start_level,
                        'end_level': current_end_level
                    })

    def parse_qty_rule(self, drop_rule):
        if drop_rule.startswith('-'):
            val = abs(int(drop_rule))
            return val, val, 1.0
        pairs = drop_rule.split(';')
        min_qty = float('inf'); max_qty = 0; total_weight = 0; success_weight = 0
        for pair in pairs:
            if ',' not in pair: continue
            try:
                c, w = map(int, pair.split(','))
                total_weight += w
                if c > 0:
                    success_weight += w
                    if c < min_qty: min_qty = c
                    if c > max_qty: max_qty = c
            except ValueError: continue
        if total_weight == 0: return 0, 0, 0.0
        if min_qty == float('inf'): min_qty = 0
        return min_qty, max_qty, (success_weight / total_weight)

    def get_real_table_id(self, table_id):
        if table_id in self.tables: return table_id
        if table_id.startswith("T_"):
            stripped = table_id[2:]
            if stripped in self.tables: return stripped
        return None

    def get_groups_for_table(self, table_id, level):
        real_id = self.get_real_table_id(table_id)
        if not real_id: return None
        raw_rows = self.tables[real_id]
        groups = []
        current_group = {'rule': "1,1", 'items': []}

        for row in raw_rows:
            if row['type'] == 'group_header':
                if current_group['items']: groups.append(current_group)
                current_group = {'rule': row['drop_count'], 'items': []}
            elif row['type'] == 'item':
                s = row['start_level']; e = row['end_level']
                if s and level < s: continue
                if e and level > e: continue
                current_group['items'].append(row)
        if current_group['items']: groups.append(current_group)
        return groups

    def build_loot_tree(self, table_id, level, visited=None):
        if visited is None: visited = set()
        
        real_id = self.get_real_table_id(table_id)
        if not real_id: return None

        root_node = LootNode(real_id, "Table")
        
        groups = self.get_groups_for_table(real_id, level)
        if not groups: return None

        for group in groups:
            min_q, max_q, chance = self.parse_qty_rule(group['rule'])
            if chance <= 0: continue

            pool_node = LootNode("Subtable", "Pool", chance, min_q, max_q)
            
            total_freq = sum(i['frequency'] for i in group['items'])
            if total_freq == 0: continue

            for item in group['items']:
                name = item['name']
                freq = item['frequency']
                rel_weight = freq / total_freq
                
                child_table_id = self.get_real_table_id(name)
                
                if child_table_id:
                    if child_table_id in EXTERNAL_TABLES:
                        link_node = LootNode(name, "Link", rel_weight)
                        pool_node.add_child(link_node)

                    elif child_table_id in visited:
                        child_node = LootNode(name, "Table_Cycle", rel_weight)
                        pool_node.add_child(child_node)
                    else:
                        new_visited = visited.copy()
                        new_visited.add(child_table_id)
                        child_tree = self.build_loot_tree(child_table_id, level, new_visited)
                        
                        if child_tree:
                            child_tree.chance = rel_weight 
                            pool_node.add_child(child_tree)
                
                else:
                    node_type = "Item" if self.stats_mgr.is_valid_item_id(name) else "Category"
                    child_node = LootNode(name, node_type, rel_weight)
                    
                    if node_type == "Category":
                        cat_items = self.stats_mgr.get_items_for_category(name, level)
                        if cat_items:
                            cat_total_prio = sum(c['priority'] for c in cat_items)
                            if cat_total_prio > 0:
                                for c in cat_items:
                                    child_node.items.append({
                                        'name': c['id'],
                                        'rel_chance': c['priority'] / cat_total_prio
                                    })
                    
                    pool_node.add_child(child_node)

            root_node.add_child(pool_node)

        return root_node

    def flatten_wrappers(self, node):
        if not node or not node.children: return node

        new_children = []
        for child in node.children:
            if child.type == "Pool":
                optimized_pool_children = []
                for grand_child in child.children:
                    optimized_grand_child = self.flatten_wrappers(grand_child)
                    optimized_pool_children.append(optimized_grand_child)
                child.children = optimized_pool_children
                new_children.append(child)
            else:
                new_children.append(self.flatten_wrappers(child))
        
        node.children = new_children

        if node.type == "Table" and len(node.children) == 1:
            pool = node.children[0]
            if pool.chance >= 0.99 and pool.min_qty == 1 and pool.max_qty == 1:
                if len(pool.children) == 1 and pool.children[0].type == "Table":
                    child_table = pool.children[0]
                    return child_table
        return node

class WikiExporter:
    def __init__(self):
        self.c_bg_header_guaranteed = "#1e3a1e" 
        self.c_bg_header_chance = "#3a2a1e"     
        self.c_accent_green = "#2c7a2c" 
        self.c_accent_gold = "#a87b00"
        self.c_text_muted = "#555"

    def is_junk(self, name):
        keywords = ["Junk", "Generic", "Scraps", "Clutter"]
        return any(k in name for k in keywords)

    def extract_and_prune_guaranteed(self, node, multiplier=1):
        extracted_items = []
        for pool in list(node.children):
            if pool.type != "Pool": continue 

            # Only extract if it is 100% chance AND has exactly 1 child.
            # If it has > 1 child, it's a weighted choice (Random), so we can't extract it as a fixed item.
            if pool.chance >= 0.99:
                if len(pool.children) > 1:
                    continue

                current_qty = pool.min_qty * multiplier
                
                pool_children_copy = list(pool.children)
                
                for child in pool_children_copy:
                    if child.type in ["Item", "Category", "Link"]:
                        extracted_items.append({
                            'node': child,
                            'qty': current_qty
                        })
                        pool.children.remove(child)

                    elif child.type in ["Table", "Table_Cycle"]:
                        # Recurse
                        sub_items = self.extract_and_prune_guaranteed(child, current_qty)
                        
                        if sub_items:
                            extracted_items.extend(sub_items)
                            if not child.children:
                                pool.children.remove(child)
                        else:
                            # If sub_items is empty, it means the table contained random pools.
                            # We failed to extract. Leave it here.
                            pass

                if not pool.children:
                    node.children.remove(pool)

        return extracted_items

    def render_tree(self, node):
        if not node: return ""
        
        html = f"<div style='width:100%; max-width: 800px; font-family: sans-serif;'>"
        html += f"<h3>Loot Table: {node.name}</h3>"
        
        if not node.children:
            html += "<p>No loot defined.</p></div>"
            return html

        guaranteed_items = self.extract_and_prune_guaranteed(node, multiplier=1)

        if guaranteed_items:
            html += self.render_guaranteed_flat_table(guaranteed_items)

        for pool in node.children:
            html += self.render_pool_table(pool)
            
        html += "</div>"
        return html

    def render_guaranteed_flat_table(self, items):
        html = f"""
        <table class="wikitable" style="width: 100%; margin-bottom: 15px;">
            <tr style="background-color: {self.c_bg_header_guaranteed}; color: #fff;">
                <th colspan="3" style="text-align: left; padding: 5px 10px;">
                    Guaranteed Stock <span style="font-weight:normal; font-size:0.9em; opacity:0.8;">(Always Available)</span>
                </th>
            </tr>
            <tr>
                <th style="width: 60%;">Item / Group</th>
                <th style="width: 20%; text-align: center;">Quantity</th>
                <th style="width: 20%; text-align: center;">Chance</th>
            </tr>
        """
        
        for entry in items:
            node = entry['node']
            qty = entry['qty']
            html += "<tr>"
            html += f"<td style='padding: 4px 8px;'>{self.render_row_content_flat(node)}</td>"
            html += f"<td style='padding: 4px 8px; text-align: center; color: {self.c_accent_green}; font-weight: bold;'>{qty}</td>"
            html += f"<td style='padding: 4px 8px; text-align: center; color: {self.c_text_muted};'>100%</td>"
            html += "</tr>"

        html += "</table>"
        return html

    def render_pool_table(self, pool):
        qty_str = f"{pool.min_qty}" if pool.min_qty == pool.max_qty else f"{pool.min_qty}-{pool.max_qty}"
        
        is_guaranteed_pool = pool.chance >= 0.99
        
        # LOGIC FIX:
        # If the pool is guaranteed (100%) AND selects a single item type (len children == 1),
        # we treat the pool's quantity as the item's quantity.
        # In this case, we simplify the header to just "Stock" or "Conditional" and let the row show the number.
        push_qty = False
        if is_guaranteed_pool and len(pool.children) == 1:
            push_qty = True

        if is_guaranteed_pool:
            title_text = "Stock" if push_qty else f"Stock (Selects {qty_str})"
            chance_text = "Always Available"
            header_bg = self.c_bg_header_guaranteed
        else:
            title_text = f"Rare/Conditional (Selects {qty_str})"
            chance_text = f"{pool.chance:.1%} Chance"
            header_bg = self.c_bg_header_chance

        html = f"""
        <table class="wikitable" style="width: 100%; margin-bottom: 10px;">
            <tr style="background-color: {header_bg}; color: #fff;">
                <th colspan="3" style="padding: 5px 10px; text-align: left;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span>{title_text}</span>
                        <span style="font-size: 0.85em; background: rgba(0,0,0,0.3); padding: 1px 5px; border-radius: 3px;">{chance_text}</span>
                    </div>
                </th>
            </tr>
            <tr style="font-size: 0.9em; background-color: #f9f9f9;">
                <th style="text-align: left; padding: 4px 8px;">Item / Group</th>
                <th style="width: 20%; text-align: center; padding: 4px 8px;">Quantity</th>
                <th style="width: 20%; text-align: center; padding: 4px 8px;">Chance</th>
            </tr>
        """
        
        sorted_children = sorted(pool.children, key=lambda x: x.chance, reverse=True)
        for child in sorted_children:
            # Pass the pool's min_qty if we determined we should push it down
            q_override = pool.min_qty if push_qty else None
            html += self.render_recursive_rows(child, qty_override=q_override)
            
        html += "</table>"
        return html

    def render_recursive_rows(self, node, qty_override=None):
        # Calculate Quantity
        # 1. Start with node's own qty
        qty_val = node.min_qty 
        # 2. If node is a simple Item/Link/Category, it defaults to 1 usually
        if node.type in ["Item", "Category", "Link"]:
             qty_val = 1
        # 3. Apply override if provided (from parent pool)
        if qty_override is not None:
            qty_val = qty_override

        # Format string
        qty_display = f"{qty_val}" 
        # Handle ranges only if override wasn't applied (simple case)
        if qty_override is None and node.min_qty != node.max_qty:
            qty_display = f"{node.min_qty}-{node.max_qty}"

        pct_label = f"{node.chance:.1%}"
        if node.chance > 0.99: pct_label = "100%"
        
        primary_content = ""
        clean_name = node.name.replace("ST_", "").replace("_", " ")

        if node.type == "Link":
            primary_content = f"""&#128279; <a href="#" style="font-weight:bold; text-decoration:none;">[[{node.name}]]</a>"""
        elif node.type == "Item":
            primary_content = f"""<span style="color: #666; font-size: 0.8em;">&bull;</span> {node.name}"""
        elif node.type == "Category":
            item_count = len(node.items)
            clean_name = node.name.replace("Category", "").strip()
            primary_content = f"""<span style="color: {self.c_accent_gold}; font-weight:bold;">[CAT]</span> {clean_name} <span style="font-size:0.9em; color:#666;">({item_count} items)</span>"""
        elif node.type in ["Table", "Table_Cycle"]:
             primary_content = f"""<span style="font-weight:bold;">{clean_name}</span>"""

        html = "<tr>"
        html += f"<td style='padding: 4px 8px;'>{primary_content}</td>"
        html += f"<td style='padding: 4px 8px; text-align: center;'>{qty_display}</td>"
        html += f"<td style='padding: 4px 8px; text-align: center; color: {self.c_text_muted};'>{pct_label}</td>"
        html += "</tr>"

        if node.type == "Category":
            expand_content = "<ul style='margin: 5px 0 5px 20px; padding: 0; list-style-type: none; font-size: 0.9em; color: #555;'>"
            for item in node.items:
                 expand_content += f"<li>&bull; {item['name']} <span style='opacity:0.7'>({item['rel_chance']:.1%})</span></li>"
            expand_content += "</ul>"
            html += self.render_expansion_row("Show Items", expand_content)

        elif node.type in ["Table", "Table_Cycle"] and node.children:
            # When expanding a table, we create a new inner table.
            # We assume inside this table, standard rules apply (pools determine qty).
            inner_table = """<table class="wikitable" style="width: 100%; border-collapse: collapse; margin: 5px 0;">"""
            inner_table += """<tr style="background:#eee; font-size:0.85em;"><th style="text-align:left;">Item / Group</th><th style="width:20%;">Qty</th><th style="width:20%;">Chance</th></tr>"""
            
            for pool in node.children:
                # Check for push-down logic inside nested tables too
                is_guaranteed = pool.chance >= 0.99
                push_q = (is_guaranteed and len(pool.children) == 1)
                
                sorted_kids = sorted(pool.children, key=lambda x: x.chance, reverse=True)
                for kid in sorted_kids:
                    q_over = pool.min_qty if push_q else None
                    inner_table += self.render_recursive_rows(kid, qty_override=q_over)
            
            inner_table += "</table>"
            html += self.render_expansion_row("Show Contents", inner_table)

        return html

    def render_expansion_row(self, toggle_label, content):
        return f"""
        <tr>
            <td colspan="3" style="padding: 0; border: none;">
                <div class="mw-collapsible mw-collapsed" style="width: 100%;">
                    <div class="mw-collapsible-toggle" style="padding: 4px 8px; background-color: #fafafa; border-bottom: 1px solid #ddd; cursor: pointer; text-align: center; font-size: 0.85em; color: #444;">
                        &#9660; {toggle_label}
                    </div>
                    <div class="mw-collapsible-content" style="padding: 5px 10px;">
                        {content}
                    </div>
                </div>
            </td>
        </tr>
        """

    def render_row_content_flat(self, node):
        if node.type == "Link":
            return f"""&#128279; <a href="#" style="font-weight:bold; text-decoration:none;">[[{node.name}]]</a>"""
        if node.type == "Item":
            return f"""<span style="color: #666; font-size: 0.8em;">&bull;</span> {node.name}"""
        if node.type == "Category":
            item_count = len(node.items)
            clean_name = node.name.replace("Category", "").strip()
            return f"""<span style="color: {self.c_accent_gold}; font-weight:bold;">[CAT]</span> {clean_name} ({item_count} items)"""
        return node.name

def main():
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_stats = {}
    for f in stats_files: raw_stats.update(parse_stats_txt(f))
    final_stats = resolve_all_stats(raw_stats)
    stats_mgr = StatsManager(final_stats)
    
    parser = TreasureParser(stats_mgr)
    tt_files = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt_files:
        with open(f, 'r', encoding='utf-8', errors='replace') as file_obj:
            parser.load_data(file_obj.read())

    target = "RC_DW_Trader_EquipmentRangerWarrior"
    
    root = parser.build_loot_tree(target, level=13)
    
    optimized_root = parser.flatten_wrappers(root)
    
    exporter = WikiExporter()
    html_output = exporter.render_tree(optimized_root)
    
    print(html_output)

if __name__ == "__main__":
    main()