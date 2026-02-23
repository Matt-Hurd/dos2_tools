"""
Loot engine for DOS2 treasure tables.

Consolidates the StatsManager, LootNode, and TreasureParser classes
that were previously duplicated across 5+ scripts into a single
canonical implementation.

The loot engine handles:
  - Parsing treasure table CSV data
  - Building loot trees from table definitions
  - Category resolution (which items belong to which categories)
  - Probability flattening for item source analysis
  - Tree optimization (wrapper flattening)
"""

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field


# ─── Data Structures ────────────────────────────────────────────────────────

@dataclass
class LootNode:
    """
    A node in the loot table hierarchy.

    Represents either a Table (container), Pool (random selection),
    Category (item group), or Item (leaf).
    """
    name: str
    type: str  # "Table", "Category", "Item", "Pool"
    chance: float = 1.0
    min_qty: int = 1
    max_qty: int = 1
    children: list = field(default_factory=list)
    items: list = field(default_factory=list)

    def add_child(self, node):
        self.children.append(node)


# ─── Stats Manager ──────────────────────────────────────────────────────────

class StatsManager:
    """
    Manages resolved stats and provides item category lookups.

    This is the canonical version, consolidating features from all
    the previously divergent copies:
      - Category mapping (ObjectCategory -> list of items)
      - Item minimum level queries
      - Item validity checks
      - Category info (items with level ranges)
    """

    def __init__(self, all_stats):
        self.stats = all_stats
        self.category_map = defaultdict(list)
        self._build_category_map()

    def _build_category_map(self):
        """Build a map of ObjectCategory -> list of item entries."""
        for entry_id, data in self.stats.items():
            categories = data.get("ObjectCategory", "")
            if not categories:
                continue
            for cat in categories.split(";"):
                cat = cat.strip()
                if cat:
                    self.category_map[cat].append({
                        "id": entry_id,
                        "data": data,
                    })

    def get_items_for_category(self, category_name, current_level=None):
        """
        Get all items in a category, optionally filtered by level.

        Args:
            category_name: The ObjectCategory to look up
            current_level: If provided, only return items at or below this level

        Returns:
            list[dict]: Items in the category
        """
        items = self.category_map.get(category_name, [])
        if current_level is not None:
            return [
                item for item in items
                if self.get_item_min_level(item["id"]) <= current_level
            ]
        return items

    def get_category_info(self, category_name):
        """
        Get detailed info about items in a category.

        Returns a list of dicts with id, min_level, and data for each item.
        """
        items = self.category_map.get(category_name, [])
        result = []
        for item in items:
            result.append({
                "id": item["id"],
                "min_level": self.get_item_min_level(item["id"]),
                "data": item["data"],
            })
        return result

    def is_valid_item_id(self, item_name):
        """Check if an item ID exists in the stats database."""
        return item_name in self.stats

    def get_item_min_level(self, item_name):
        """
        Get the minimum level for an item.

        Returns 0 if the item has no MinLevel or doesn't exist.
        """
        # Strip I_ prefix: stats are keyed without it (e.g. I_LOOT_Essence_Life_A → LOOT_Essence_Life_A)
        lookup = item_name[2:] if item_name.startswith("I_") else item_name
        if lookup not in self.stats:
            return 0
        try:
            return int(self.stats[lookup].get("MinLevel", "0") or "0")
        except (ValueError, TypeError):
            return 0


# ─── Treasure Table Parser ──────────────────────────────────────────────────

class TreasureParser:
    """
    Parser and tree builder for DOS2 treasure tables.

    The treasure table format is:
      new treasuretable "TableName"   -- defines a table
      new subtable "RULE"             -- pool header, RULE is a qty/chance rule
                                         like "1,1" (always 1), "1,3;0,3" (50%)
      object category "CatName", FREQ  -- category pool entry
      new "ItemOrTableName", FREQ      -- item or sub-table pool entry
      StartLevel "N"                   -- subsequent entries only valid from lvl N
      EndLevel "N"                     -- subsequent entries only valid up to lvl N

    This is the canonical version, consolidating features from all copies:
      - CSV parsing with proper quote handling
      - Quantity/chance rule parsing (classic ;-separated probability format)
      - Table aliasing (handling T_ prefix)
      - Tree building with cycle detection
      - Wrapper flattening (tree optimization)
      - Probability flattening (for source analysis)
    """

    def __init__(self, stats_manager=None):
        self.tables = {}
        self.stats_mgr = stats_manager

    def load_data(self, data_str):
        """
        Parse treasure table text data and populate self.tables.

        Table format (per-table):
            new treasuretable "Name"
            new subtable "RULE"          <- pool header; RULE is qty/chance rule
            object category "Cat", FREQ  <- category entry in current pool
            new "NameOrTable", FREQ      <- item or sub-table entry in current pool
            StartLevel "N"               <- next entries valid from level N
            EndLevel "N"                 <- next entries valid up to level N
        """
        current_table = None
        current_pool_idx = None  # index into self.tables[t]['pools']
        current_start_level = None
        current_end_level = None

        for raw_line in data_str.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            # ── New table declaration ────────────────────────────────────────
            if line.startswith('new treasuretable "'):
                match = re.match(r'new treasuretable "(.+?)"', line)
                if match:
                    table_id = match.group(1)
                    current_table = table_id
                    current_pool_idx = None
                    current_start_level = None
                    current_end_level = None
                    if table_id not in self.tables:
                        self.tables[table_id] = {
                            "pools": [],    # list of {rule, items}
                            "can_merge": True,
                            "min_level": 0,
                            "max_level": 0,
                        }
                continue

            if not current_table:
                continue

            # ── Level range markers ──────────────────────────────────────────
            if line.startswith("StartLevel"):
                m = re.search(r'StartLevel\s+"([^"]+)"', line)
                if m:
                    try:
                        current_start_level = int(m.group(1))
                    except ValueError:
                        pass
                continue

            if line.startswith("EndLevel"):
                m = re.search(r'EndLevel\s+"([^"]+)"', line)
                if m:
                    try:
                        current_end_level = int(m.group(1))
                    except ValueError:
                        pass
                continue

            # ── Pool header ──────────────────────────────────────────────────
            if line.startswith("new subtable"):
                # The argument is the pool quantity/chance rule, NOT a name
                rest = line[len("new subtable"):].strip().strip('"')
                pool = {
                    "rule": rest,
                    "items": [],
                }
                self.tables[current_table]["pools"].append(pool)
                current_pool_idx = len(self.tables[current_table]["pools"]) - 1
                # Reset level range — it's scoped to the subtable block above the items,
                # and should not bleed from one pool into the next.
                current_start_level = None
                current_end_level = None
                continue

            # ── Ensure we have an implicit pool if entries arrive before any subtable ─
            if current_pool_idx is None:
                pool = {"rule": "1,1", "items": []}
                self.tables[current_table]["pools"].append(pool)
                current_pool_idx = 0

            pool = self.tables[current_table]["pools"][current_pool_idx]

            # ── Category entry ───────────────────────────────────────────────
            if line.startswith("object category"):
                parts = self._parse_csv_line(line[len("object category"):].strip())
                if parts:
                    name = parts[0].strip('"')
                    freq = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                    pool["items"].append({
                        "type": "Category",
                        "name": name,
                        "frequency": freq,
                        "start_level": current_start_level,
                        "end_level": current_end_level,
                    })
                continue

            # ── Item or sub-table entry ──────────────────────────────────────
            if line.startswith("new "):
                parts = self._parse_csv_line(line[4:].strip())
                if parts:
                    name = parts[0].strip('"')
                    freq = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                    pool["items"].append({
                        "type": "Item",   # will be resolved in build_loot_tree
                        "name": name,
                        "frequency": freq,
                        "start_level": current_start_level,
                        "end_level": current_end_level,
                    })
                continue

    def _parse_csv_line(self, line):
        """Parse a CSV-like line, handling quoted fields."""
        try:
            reader = csv.reader(io.StringIO(line))
            for row in reader:
                return [field.strip() for field in row if field.strip()]
        except csv.Error:
            return line.split(",")

    def parse_qty_rule(self, drop_rule):
        """
        Parse a pool selection rule string.

        The treasure table format uses semicolon-separated count,weight pairs:
          "1,1"       -> always select 1 item (weight 1)
          "-1"        -> always select 1 item (negative = guaranteed)
          "1,3;0,3"   -> 50% chance: select 1 (weight 3) or 0 (weight 3)
          "1,8;0,2"   -> 80% chance of selecting 1 item

        Returns (min_qty, max_qty, chance) tuple.
        """
        if not drop_rule:
            return 1, 1, 1.0

        drop_rule = str(drop_rule).strip()

        # Negative number: guaranteed, e.g. "-1"
        if drop_rule.startswith('-'):
            try:
                val = abs(int(drop_rule))
                return val, val, 1.0
            except ValueError:
                pass

        # Semicolon-separated probability pairs: "COUNT,WEIGHT;COUNT,WEIGHT;..."
        if ';' in drop_rule or ',' in drop_rule:
            pairs = drop_rule.split(';')
            min_q = 9999
            max_q = 0
            total_w = 0
            success_w = 0
            parsed = False
            for pair in pairs:
                pair = pair.strip()
                if ',' not in pair:
                    continue
                parts = pair.split(',', 1)
                try:
                    c = int(parts[0].strip())
                    w = int(parts[1].strip())
                    total_w += w
                    if c > 0:
                        success_w += w
                        min_q = min(min_q, c)
                        max_q = max(max_q, c)
                    parsed = True
                except (ValueError, IndexError):
                    continue
            if parsed and total_w > 0:
                if min_q == 9999:
                    min_q = 0
                chance = success_w / total_w
                return min_q, max_q, chance

        # Plain integer: always select that many
        try:
            val = int(drop_rule)
            return val, val, 1.0
        except ValueError:
            return 1, 1, 1.0

    def get_real_table_id(self, table_id):
        """
        Resolve a table ID, handling T_ prefix and _N suffixes.

        Table references in item entries use formats like:
          "T_SourceOrb"  -> resolves to "SourceOrb" in tables dict
          "ST_Foo_3"     -> resolves to "ST_Foo" (level-specific suffix)
        """
        if table_id in self.tables:
            return table_id
        # Strip T_ prefix (common in item references)
        if table_id.startswith("T_") and table_id[2:] in self.tables:
            return table_id[2:]
        # Strip trailing _N suffix (level-specific alias)
        base = re.sub(r"_\d+$", "", table_id)
        if base in self.tables:
            return base
        if base.startswith("T_") and base[2:] in self.tables:
            return base[2:]
        return None  # Not found (means it's an item, not a table)

    def build_loot_tree(self, table_id, level=1, visited=None):
        """
        Build a LootNode tree for a treasure table.

        Each table has one or more pools (from `new subtable` lines).
        Each pool selects N items from its child list with a given chance.
        Items in a pool can be:
          - Category entries  -> resolved to their items if stats_mgr is set
          - Item entries      -> may be items or sub-table references

        Args:
            table_id: The treasure table to build
            level: Player level (affects StartLevel/EndLevel filtering and
                   category item filtering)
            visited: Set of visited real table IDs for cycle detection

        Returns:
            LootNode: Root node of the loot tree
        """
        if visited is None:
            visited = set()

        real_id = self.get_real_table_id(table_id)
        if real_id is None or real_id in visited:
            return LootNode(table_id, "Table")

        if real_id not in self.tables:
            return LootNode(table_id, "Table")

        visited.add(real_id)
        table_data = self.tables[real_id]
        root = LootNode(real_id, "Table")

        for pool_data in table_data.get("pools", []):
            rule = pool_data.get("rule", "1,1")
            min_qty, max_qty, chance = self.parse_qty_rule(rule)

            if chance <= 0:
                continue  # This pool never fires

            # Create a pool node representing this subtable selection
            pool_node = LootNode("Pool", "Pool", chance=chance,
                                 min_qty=min_qty, max_qty=max_qty)

            items = pool_data.get("items", [])

            # Filter by StartLevel / EndLevel
            valid_items = []
            for item in items:
                sl = item.get("start_level")
                el = item.get("end_level")
                if sl is not None and level < sl:
                    continue
                if el is not None and level > el:
                    continue
                valid_items.append(item)

            # Compute total frequency for relative weights
            total_freq = sum(i.get("frequency", 1) for i in valid_items)
            if total_freq == 0:
                continue

            for item in valid_items:
                name = item["name"]
                freq = item.get("frequency", 1)
                rel_chance = freq / total_freq
                entry_type = item["type"]  # "Category" or "Item"

                if entry_type == "Category":
                    # I_ prefix = direct item reference, not an ObjectCategory name
                    if name.startswith("I_"):
                        clean_name = name[2:]
                        node_is_valid = (
                            self.stats_mgr is None
                            or self.stats_mgr.is_valid_item_id(clean_name)
                            or self.stats_mgr.is_valid_item_id(name)
                        )
                        item_node = LootNode(
                            clean_name, "Item" if node_is_valid else "InvalidItem",
                            chance=rel_chance
                        )
                        pool_node.add_child(item_node)
                    else:
                        # Actual ObjectCategory lookup
                        cat_node = LootNode(name, "Category", chance=rel_chance)
                        if self.stats_mgr:
                            cat_items = self.stats_mgr.get_items_for_category(name, level)
                            for ci in cat_items:
                                item_node = LootNode(ci["id"], "Item")
                                cat_node.items.append(item_node)
                        pool_node.add_child(cat_node)

                else:
                    # Check if it's a reference to another table
                    child_real_id = self.get_real_table_id(name)
                    if child_real_id and child_real_id != real_id:
                        if child_real_id in visited:
                            # Cycle: render as a leaf Table_Cycle
                            cycle_node = LootNode(name, "Table_Cycle",
                                                  chance=rel_chance)
                            pool_node.add_child(cycle_node)
                        else:
                            child_tree = self.build_loot_tree(
                                name, level, visited.copy()
                            )
                            child_tree.chance = rel_chance
                            pool_node.add_child(child_tree)
                    else:
                        # It's a leaf item (possibly with I_ prefix)
                        clean_name = name
                        if name.startswith("I_"):
                            clean_name = name[2:]
                        node_is_valid = (
                            self.stats_mgr is None
                            or self.stats_mgr.is_valid_item_id(clean_name)
                            or self.stats_mgr.is_valid_item_id(name)
                        )
                        item_node = LootNode(
                            clean_name, "Item" if node_is_valid else "InvalidItem",
                            chance=rel_chance
                        )
                        pool_node.add_child(item_node)

            if pool_node.children:
                root.add_child(pool_node)

        return root

    def flatten_wrappers(self, node):
        """
        Optimize the loot tree by flattening unnecessary wrapper nodes.

        If a Table node has exactly one child Pool/Table with one child,
        merge them to reduce tree depth.
        """
        # Recursively flatten children first
        for child in node.children:
            self.flatten_wrappers(child)

        # If this is a Table with exactly 1 child that is also a Table
        if (node.type == "Table" and len(node.children) == 1
                and node.children[0].type == "Table"
                and len(node.children[0].children) > 0):
            inner = node.children[0]
            # Absorb the inner table's children
            node.children = inner.children
            # Propagate chance if meaningful
            if inner.chance < 1.0:
                for child in node.children:
                    child.chance *= inner.chance

    def flatten_probabilities(self, node, current_prob=1.0, current_min=1, current_max=1):
        """
        Flatten the tree into a dict of item_name -> probability info.

        Used for "where does this item come from?" analysis.

        Args:
            node: Root LootNode to start from
            current_prob: Cumulative probability to this point
            current_min: Cumulative min quantity
            current_max: Cumulative max quantity

        Returns:
            dict[str, dict]: item_name -> {prob, min_qty, max_qty}
        """
        result = {}

        effective_prob = current_prob * node.chance
        eff_min = current_min * node.min_qty
        eff_max = current_max * node.max_qty

        if node.type == "Item" and node.name:
            if node.name in result:
                # Merge probabilities
                existing = result[node.name]
                existing["prob"] = 1 - (1 - existing["prob"]) * (1 - effective_prob)
                existing["min_qty"] = min(existing["min_qty"], eff_min)
                existing["max_qty"] = max(existing["max_qty"], eff_max)
            else:
                result[node.name] = {
                    "prob": effective_prob,
                    "min_qty": eff_min,
                    "max_qty": eff_max,
                }

        # Category items
        if node.items:
            per_item_prob = effective_prob / max(len(node.items), 1)
            for item_node in node.items:
                if item_node.name in result:
                    existing = result[item_node.name]
                    existing["prob"] = 1 - (1 - existing["prob"]) * (1 - per_item_prob)
                else:
                    result[item_node.name] = {
                        "prob": per_item_prob,
                        "min_qty": eff_min,
                        "max_qty": eff_max,
                    }

        # Recurse into children
        for child in node.children:
            child_items = self.flatten_probabilities(child, effective_prob, eff_min, eff_max)
            for item_name, item_info in child_items.items():
                if item_name in result:
                    existing = result[item_name]
                    existing["prob"] = 1 - (1 - existing["prob"]) * (1 - item_info["prob"])
                    existing["min_qty"] = min(existing["min_qty"], item_info["min_qty"])
                    existing["max_qty"] = max(existing["max_qty"], item_info["max_qty"])
                else:
                    result[item_name] = item_info

        return result

    def print_tree(self, node, indent=0, parent_chance=1.0):
        """Debug utility: print a loot tree to console."""
        effective = parent_chance * node.chance
        prefix = "  " * indent
        qty_str = (
            f" x{node.min_qty}-{node.max_qty}"
            if node.min_qty != node.max_qty
            else (f" x{node.min_qty}" if node.min_qty > 1 else "")
        )

        print(f"{prefix}[{node.type}] {node.name} "
              f"({effective:.1%} chance){qty_str}")

        for item in node.items:
            print(f"{prefix}  └─ {item.name}")

        for child in node.children:
            self.print_tree(child, indent + 1, effective)
