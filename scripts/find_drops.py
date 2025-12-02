import json
import re
import csv
import io
import os

# --- MOCK IMPORTS ---
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.parsers import parse_stats_txt
from dos2_tools.core.stats_engine import resolve_all_stats
# --------------------

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
    """Represents a node in the loot hierarchy."""
    def __init__(self, name, node_type, chance=1.0, min_qty=1, max_qty=1):
        self.name = name
        self.type = node_type # "Table", "Category", "Item", "Pool"
        self.chance = chance
        self.min_qty = min_qty
        self.max_qty = max_qty
        self.children = [] # List of LootNodes or ItemDicts
        self.items = [] # If leaf, contains resolved items

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

    # =========================================================================
    # HIERARCHICAL ANALYSIS
    # =========================================================================

    def build_loot_tree(self, table_id, level, visited=None):
        if visited is None: visited = set()
        
        real_id = self.get_real_table_id(table_id)
        if not real_id: return None # Should not happen if called correctly

        # Root Node for this Table
        root_node = LootNode(real_id, "Table")
        
        # Get Pools (Subtables)
        groups = self.get_groups_for_table(real_id, level)
        if not groups: return None

        for group in groups:
            min_q, max_q, chance = self.parse_qty_rule(group['rule'])
            if chance <= 0: continue

            # Create a "Pool Node" to represent this specific subtable logic
            pool_node = LootNode("Subtable", "Pool", chance, min_q, max_q)
            
            # Calculate total frequency for relative weights
            total_freq = sum(i['frequency'] for i in group['items'])
            if total_freq == 0: continue

            for item in group['items']:
                name = item['name']
                freq = item['frequency']
                rel_weight = freq / total_freq
                
                # RECURSION CHECK
                child_table_id = self.get_real_table_id(name)
                
                if child_table_id:
                    # Case A: Nested Table
                    if child_table_id in visited:
                        # Cycle! Treat as leaf.
                        child_node = LootNode(name, "Table_Cycle", rel_weight)
                        pool_node.add_child(child_node)
                    else:
                        # Recurse
                        new_visited = visited.copy()
                        new_visited.add(child_table_id)
                        child_tree = self.build_loot_tree(child_table_id, level, new_visited)
                        
                        if child_tree:
                            # Attach the entire child tree with updated weight
                            child_tree.chance = rel_weight # Relative chance within this pool
                            pool_node.add_child(child_tree)
                
                else:
                    # Case B: Item or Category
                    node_type = "Item" if self.stats_mgr.is_valid_item_id(name) else "Category"
                    child_node = LootNode(name, node_type, rel_weight)
                    
                    # If Category, expand items immediately into the node
                    if node_type == "Category":
                        cat_items = self.stats_mgr.get_items_for_category(name, level)
                        if cat_items:
                            # Normalize internal weights
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
        """
        Optimizes the tree.
        If a Table Node has exactly 1 Pool, and that Pool selects exactly 1 item,
        and that item is a Table Node -> Merge them.
        """
        if not node or not node.children: return node

        # Process children first (bottom-up)
        new_children = []
        for child in node.children:
            # Child is usually a Pool
            if child.type == "Pool":
                # Optimize inside the pool
                optimized_pool_children = []
                for grand_child in child.children:
                    optimized_grand_child = self.flatten_wrappers(grand_child)
                    optimized_pool_children.append(optimized_grand_child)
                child.children = optimized_pool_children
                new_children.append(child)
            else:
                # Table inside a table (rare structure in my node logic, but possible)
                new_children.append(self.flatten_wrappers(child))
        
        node.children = new_children

        # Logic: If I am a Table, and I have 1 Pool, and that Pool has 1 Child (Table),
        # And the logic is "Select 1", then I am a wrapper.
        if node.type == "Table" and len(node.children) == 1:
            pool = node.children[0]
            # Check if pool is purely a wrapper (100% chance, 1 qty)
            # AND it has only 1 child which is a Table
            if pool.chance >= 0.99 and pool.min_qty == 1 and pool.max_qty == 1:
                if len(pool.children) == 1 and pool.children[0].type == "Table":
                    # Promote the child table to replace me
                    # We preserve the name for trace, but effectively return the child
                    child_table = pool.children[0]
                    # Propagate chance (1.0 * 1.0 = 1.0)
                    return child_table

        return node

    def print_tree(self, node, indent=0, parent_chance=1.0):
        if not node: return
        
        prefix = "  " * indent
        
        # Display Logic
        if node.type == "Table":
            # Just print name, recursion handles contents
            # Unless it's the root, we usually print this via the Parent Pool calling us
            if indent == 0:
                print(f"=== {node.name} ===")
            else:
                # Nested table
                eff_chance = parent_chance
                print(f"{prefix}[TABLE] {node.name} (Chance: {eff_chance:.1%})")

            for pool in node.children:
                self.print_tree(pool, indent + 1)

        elif node.type == "Pool":
            qty_str = f"{node.min_qty}" if node.min_qty == node.max_qty else f"{node.min_qty}-{node.max_qty}"
            print(f"\n{prefix}Pool: Selects {qty_str} (Chance: {node.chance:.0%})")
            
            # Sort children by chance
            sorted_children = sorted(node.children, key=lambda x: x.chance, reverse=True)
            for child in sorted_children:
                self.print_tree(child, indent + 1, child.chance)

        elif node.type == "Category":
            print(f"{prefix}- [CAT] {node.name} (Weight: {parent_chance:.1%})")
            # Print top 3 items as preview? or all?
            # Let's print summary
            if node.items:
                print(f"{prefix}  Contains {len(node.items)} items (e.g. {node.items[0]['name']})")

        elif node.type == "Item":
            print(f"{prefix}- {node.name} (Weight: {parent_chance:.1%})")

# --- EXECUTION ---
def main():
    conf = get_config()
    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    
    print("Loading Stats...")
    stats_files = get_files_by_pattern(all_files, conf['patterns']['stats'])
    raw_stats = {}
    for f in stats_files: raw_stats.update(parse_stats_txt(f))
    final_stats = resolve_all_stats(raw_stats)
    stats_mgr = StatsManager(final_stats)
    
    print("Loading Treasure Tables...")
    parser = TreasureParser(stats_mgr)
    tt_files = [f for f in all_files if "TreasureTable.txt" in f]
    for f in tt_files:
        with open(f, 'r', encoding='utf-8', errors='replace') as file_obj:
            parser.load_data(file_obj.read())

    target = "RC_DW_Trader_EquipmentRangerWarrior"
    
    # 1. Build Raw Tree
    root = parser.build_loot_tree(target, level=13)
    
    # 2. Optimize Wrappers (LizardPrisoner -> GenericPrisoner)
    optimized_root = parser.flatten_wrappers(root)
    
    # 3. Print
    parser.print_tree(optimized_root)

if __name__ == "__main__":
    main()