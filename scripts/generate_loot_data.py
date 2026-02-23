"""
Generate loot data for DOS2 wiki Lua modules and shared loot table pages.

Thin CLI using GameData(). Ported from generate_loot_data.py.
Outputs:
  - Module_LootData.lua: Lua table with all treasure table data
  - loot_wikitext/: Wiki stub pages for shared tables

The LootGraph is script-specific (shared-table detection logic),
so it lives here rather than in the wiki/ modules.

Usage:
    python3 -m dos2_tools.scripts.generate_loot_data
    python3 -m dos2_tools.scripts.generate_loot_data --out-lua loot.lua --out-wiki loot_pages
"""

import os
import argparse
from collections import defaultdict

from dos2_tools.core.game_data import GameData


FORCE_SHARED_PREFIXES = [
    "ST_Gen", "ST_Trader", "Reward_", "T_Reward", "ST_Humanoid"
]
IGNORE_TABLES = ["Empty", "Generic"]

EQUIPMENT_CATEGORIES = {
    "Amulet", "Axe", "Belt", "Bow", "ClothBoots", "ClothGloves",
    "ClothHelmet", "ClothLowerBody", "ClothUpperBody", "Club",
    "Crossbow", "Dagger", "HeavyBoots", "HeavyGloves", "HeavyHelmet",
    "HeavyLowerBody", "HeavyUpperBody", "LightBoots", "LightGloves",
    "LightHelmet", "LightLowerBody", "LightUpperBody", "MageBoots",
    "MageGloves", "MageHelmet", "MageLowerBody", "MageUpperBody",
    "REFERENCE_HeavyBoots", "REFERENCE_HeavyGloves", "REFERENCE_HeavyHelmet",
    "REFERENCE_HeavyLowerBody", "REFERENCE_HeavyUpperBody",
    "REFERENCE_LightBoots", "REFERENCE_LightGloves", "REFERENCE_LightHelmet",
    "REFERENCE_LightLowerBody", "REFERENCE_LightUpperBody",
    "REFERENCE_MageBoots", "REFERENCE_MageGloves", "REFERENCE_MageHelmet",
    "REFERENCE_MageLowerBody", "REFERENCE_MageUpperBody",
    "Ring", "Spear", "StaffAir", "StaffFire", "StaffPoison", "StaffWater",
    "Sword", "Shield", "TwoHandedAxe", "TwoHandedMace", "TwoHandedSword",
    "WandAir", "WandFire", "WandPoison", "WandWater",
}


class LootGraph:
    """Builds a graph of table-to-table references to identify shared tables."""

    def __init__(self, tables_dict):
        self.tables = tables_dict
        self.edges = defaultdict(list)
        self.reverse_edges = defaultdict(list)
        self._build()

    def _clean_id(self, name):
        if name.startswith("T_"):
            return name[2:]
        return name

    def _resolve_real_id(self, name):
        if name in self.tables:
            return name
        if name.startswith("T_") and name[2:] in self.tables:
            return name[2:]
        return None

    def _build(self):
        """Walk pools->items to find table-to-table references."""
        for table_id, table_data in self.tables.items():
            for pool in table_data.get("pools", []):
                for item in pool.get("items", []):
                    child_name = item.get("name", "")
                    real_child = self._resolve_real_id(child_name)
                    if real_child:
                        self.edges[table_id].append(real_child)
                        self.reverse_edges[real_child].append(table_id)

    def get_shared_tables(self):
        """Return set of table IDs that are referenced by multiple parents."""
        shared = set()
        for t_id in self.tables:
            if "Skillbook" in t_id:
                continue
            parents = set(self.reverse_edges.get(t_id, []))
            if len(parents) > 1:
                shared.add(t_id)
                continue
            for prefix in FORCE_SHARED_PREFIXES:
                clean = self._clean_id(t_id)
                if t_id.startswith(prefix) or clean.startswith(prefix):
                    shared.add(t_id)
                    break
        return shared


def get_category_info(cat_name, stats_mgr):
    """Return ('Equipment'|'Collection', items_list) for a category."""
    if cat_name in EQUIPMENT_CATEGORIES:
        return "Equipment", []
    items = stats_mgr.get_category_info(cat_name)
    if not items:
        return None, []
    sorted_items = sorted(items, key=lambda x: (x["min_level"], x["id"]))
    return "Collection", sorted_items


def clean_lua_string(name):
    return name.replace("'", "\\'")


def generate_table_page(table_id):
    return (
        f"{{{{InfoboxLootTable|name={table_id}}}}}\n"
        f"The '''{table_id}''' is a shared loot table.\n\n"
        f"== Contents ==\n"
        f"{{{{NPC Loot|table_id={table_id}|mode=full}}}}\n\n"
        f"[[Category:Loot Tables]]"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate loot data Lua module and shared table wiki pages"
    )
    parser.add_argument(
        "--out-lua", default="Module_LootData.lua",
        help="Output path for Lua module"
    )
    parser.add_argument(
        "--out-wiki", default="loot_wikitext",
        help="Output directory for shared table wiki pages"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    os.makedirs(args.out_wiki, exist_ok=True)
    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization
    stats_mgr = game.stats_manager

    tables = game.loot_engine.tables
    graph = LootGraph(tables)
    shared_tables = graph.get_shared_tables()
    print(f"Identified {len(shared_tables)} shared tables.")

    # Build Lua module
    lines = ["return {"]

    for t_id, table_data in tables.items():
        pools = table_data.get("pools", [])

        if not pools or t_id in IGNORE_TABLES:
            continue

        # Check that at least one pool has items worth outputting
        has_items = any(pool.get("items") for pool in pools)
        if not has_items:
            continue

        safe_tid = clean_lua_string(t_id)
        if safe_tid.startswith("T_"):
            safe_tid = safe_tid[2:]

        is_shared_str = "true" if t_id in shared_tables else "false"
        lines.append(f"['{safe_tid}'] = {{ IsShared={is_shared_str}, Groups={{")

        for pool in pools:
            pool_items = pool.get("items", [])
            if not pool_items:
                continue

            # Parse pool selection rule for Chance/Min/Max
            rule = pool.get("rule", "1,1")
            from dos2_tools.core.loot import TreasureParser
            tp = TreasureParser.__new__(TreasureParser)
            tp.tables = {}
            min_q, max_q, chance = tp.parse_qty_rule(rule)
            if chance <= 0:
                continue

            # Compute relative item weights from frequency
            total_freq = sum(grp.get("frequency", 1) for grp in pool_items)
            if total_freq <= 0:
                continue

            lines.append(f"  {{ Chance={chance:.4f}, Min={min_q}, Max={max_q}, Items={{")

            for grp in pool_items:
                freq = grp.get("frequency", 1)
                rel_chance = freq / total_freq if total_freq > 0 else 1.0

                name = grp.get("name", "")
                internal_name = name

                # Use pool item's level range from the treasure table (matches old script)
                start_lvl = grp.get("start_level") or 0
                end_lvl = grp.get("end_level")
                stat_min = stats_mgr.get_item_min_level(internal_name)
                actual_min = max(stat_min, start_lvl)
                # Old script: s_lvl is nil when <= 1, e_lvl is nil when absent/falsy
                s_lvl = str(actual_min) if actual_min > 1 else "nil"
                e_lvl = str(end_lvl) if end_lvl else "nil"

                extra_data_list = []
                cat_type, cat_items = get_category_info(internal_name, stats_mgr)

                display_name = internal_name
                if internal_name.startswith("I_"):
                    clean_item_id = internal_name[2:]
                    loc_text = loc.get_text(clean_item_id)
                    if not loc_text:
                        # Try template DisplayName for unique items (e.g. I_FTJ_OutsideMagister_Crossbow)
                        loc_text = game.resolve_display_name(stats_id=clean_item_id)
                    display_name = loc_text if loc_text else clean_item_id
                    extra_data_list.append("IsItem=true")
                elif internal_name.startswith("T_"):
                    display_name = internal_name[2:]

                safe_display_name = clean_lua_string(display_name)

                if cat_type == "Equipment":
                    extra_data_list.append("IsEquip=true")
                elif cat_type == "Collection" and cat_items:
                    tips = []
                    for ci in cat_items:
                        c_id = ci["id"]
                        c_lookup = c_id[2:] if c_id.startswith("I_") else c_id
                        c_name = loc.get_text(c_lookup) or c_lookup
                        c_name = clean_lua_string(c_name)
                        lvl_str = f" ({ci['min_level']})" if ci.get("min_level", 0) > 1 else ""
                        tips.append(f"{c_name}{lvl_str}")
                    tooltip_str = ", ".join(tips)
                    extra_data_list.append(f"Tooltip='{tooltip_str}'")

                extra_data_str = ", " + ", ".join(extra_data_list) if extra_data_list else ""
                lines.append(
                    f"    {{ '{safe_display_name}', {rel_chance:.4f}, {s_lvl}, {e_lvl}{extra_data_str} }},"
                )

            lines.append("  }, },")
        lines.append("} },")

    lines.append("}")

    with open(args.out_lua, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated {args.out_lua}")

    # Wiki stub pages for shared tables
    for t_id in shared_tables:
        safe_name = t_id.replace(" ", "_")
        path = os.path.join(args.out_wiki, f"{safe_name}.wikitext")
        with open(path, "w", encoding="utf-8") as f:
            f.write(generate_table_page(t_id))

    print(f"Generated {len(shared_tables)} wiki stubs in {args.out_wiki}/")
    print("done")


if __name__ == "__main__":
    main()
