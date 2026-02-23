"""
Tests for core/loot.py — TreasureParser and StatsManager.

Covered:
  - parse_qty_rule: all rule variants
  - get_real_table_id: T_ prefix, _N suffix, combinations
  - load_data + build_loot_tree: full tree construction
  - StartLevel / EndLevel filtering
  - Cycle detection
  - flatten_probabilities: probability math
  - StatsManager: category map, level filtering, I_ prefix stripping
"""

import pytest
from dos2_tools.core.loot import TreasureParser, StatsManager, LootNode

# Re-use inline strings from conftest (duplicate here for clarity if run standalone)
TINY_TREASURE_TXT = """\
new treasuretable "TinyTable"
new subtable "1,1"
object category "ClothUpperBody",5
new "SubTable_A",3

new treasuretable "SubTable_A"
new subtable "1,3;0,3"
new "I_SomeItem",1
"""

CYCLE_TXT = """\
new treasuretable "CycleA"
new subtable "1,1"
new "CycleB",1

new treasuretable "CycleB"
new subtable "1,1"
new "CycleA",1
"""

LEVEL_TXT = """\
new treasuretable "LevelTable"
new subtable "1,1"
StartLevel "5"
new "HighItem",1
EndLevel "10"
new "MidItem",1
new "I_AlwaysItem",1
"""

T_PREFIX_TXT = """\
new treasuretable "SourceOrb"
new subtable "1,1"
new "I_SourceOrb",1
"""


# ─── parse_qty_rule ──────────────────────────────────────────────────────────

class TestParseQtyRule:
    def setup_method(self):
        self.parser = TreasureParser()

    def test_guaranteed_single(self):
        assert self.parser.parse_qty_rule("1,1") == (1, 1, 1.0)

    def test_negative_guaranteed(self):
        min_q, max_q, chance = self.parser.parse_qty_rule("-1")
        assert min_q == 1
        assert max_q == 1
        assert chance == 1.0

    def test_negative_two(self):
        min_q, max_q, chance = self.parser.parse_qty_rule("-2")
        assert min_q == 2
        assert max_q == 2
        assert chance == 1.0

    def test_fifty_fifty(self):
        min_q, max_q, chance = self.parser.parse_qty_rule("1,3;0,3")
        assert min_q == 1
        assert max_q == 1
        assert abs(chance - 0.5) < 1e-9

    def test_eighty_percent(self):
        min_q, max_q, chance = self.parser.parse_qty_rule("1,8;0,2")
        assert abs(chance - 0.8) < 1e-9

    def test_always_two(self):
        min_q, max_q, chance = self.parser.parse_qty_rule("2,1")
        assert min_q == 2
        assert max_q == 2
        assert chance == 1.0

    def test_plain_integer(self):
        min_q, max_q, chance = self.parser.parse_qty_rule("3")
        assert min_q == 3
        assert max_q == 3
        assert chance == 1.0

    def test_empty_string_defaults(self):
        assert self.parser.parse_qty_rule("") == (1, 1, 1.0)

    def test_none_defaults(self):
        assert self.parser.parse_qty_rule(None) == (1, 1, 1.0)

    def test_zero_chance_pool(self):
        # "0,1" means always drop 0 items = zero chance of getting anything
        min_q, max_q, chance = self.parser.parse_qty_rule("0,1")
        assert chance == 0.0

    def test_multi_qty_range(self):
        # E.g. "1,3;2,3;3,4" — min=1, max=3
        min_q, max_q, chance = self.parser.parse_qty_rule("1,3;2,3;3,4")
        assert min_q == 1
        assert max_q == 3
        assert chance == 1.0  # All entries have count > 0


# ─── get_real_table_id ───────────────────────────────────────────────────────

class TestGetRealTableId:
    def setup_method(self):
        self.parser = TreasureParser()
        self.parser.load_data(T_PREFIX_TXT)
        # Also add a table named ST_Foo for suffix test
        self.parser.tables["ST_Foo"] = {"pools": [], "can_merge": True,
                                        "min_level": 0, "max_level": 0}

    def test_direct_match(self):
        assert self.parser.get_real_table_id("SourceOrb") == "SourceOrb"

    def test_t_prefix_stripped(self):
        assert self.parser.get_real_table_id("T_SourceOrb") == "SourceOrb"

    def test_level_suffix_stripped(self):
        # "ST_Foo_3" → "ST_Foo"
        assert self.parser.get_real_table_id("ST_Foo_3") == "ST_Foo"

    def test_t_prefix_and_level_suffix(self):
        # T_SourceOrb_5 → strip _5 → T_SourceOrb → strip T_ → SourceOrb
        assert self.parser.get_real_table_id("T_SourceOrb_5") == "SourceOrb"

    def test_not_found_returns_none(self):
        assert self.parser.get_real_table_id("NonExistentTable") is None


# ─── load_data + build_loot_tree ─────────────────────────────────────────────

class TestBuildLootTree:
    def test_empty_parser_returns_empty_tree(self):
        p = TreasureParser()
        p.load_data("")
        tree = p.build_loot_tree("NoTable")
        assert tree.type == "Table"
        assert tree.children == []

    def test_loads_table_names(self):
        p = TreasureParser()
        p.load_data(TINY_TREASURE_TXT)
        assert "TinyTable" in p.tables
        assert "SubTable_A" in p.tables

    def test_pool_count_correct(self):
        p = TreasureParser()
        p.load_data(TINY_TREASURE_TXT)
        # TinyTable has 1 subtable
        assert len(p.tables["TinyTable"]["pools"]) == 1
        # SubTable_A has 1 subtable
        assert len(p.tables["SubTable_A"]["pools"]) == 1

    def test_tree_has_pool_child(self, tiny_parser):
        tree = tiny_parser.build_loot_tree("TinyTable")
        assert tree.type == "Table"
        assert len(tree.children) == 1
        pool = tree.children[0]
        assert pool.type == "Pool"

    def test_pool_has_category_and_subtable_children(self, tiny_parser):
        tree = tiny_parser.build_loot_tree("TinyTable")
        pool = tree.children[0]
        # Two items: Category "ClothUpperBody" and sub-table "SubTable_A"
        assert len(pool.children) == 2
        types = {c.type for c in pool.children}
        assert "Category" in types
        assert "Table" in types

    def test_subtable_reference_is_recursive(self, tiny_parser):
        tree = tiny_parser.build_loot_tree("TinyTable")
        pool = tree.children[0]
        # Find the sub-table child
        sub = next(c for c in pool.children if c.type == "Table")
        # SubTable_A has a pool with a 50% chance
        assert len(sub.children) > 0

    def test_sub_table_pool_chance(self, tiny_parser):
        tree = tiny_parser.build_loot_tree("TinyTable")
        pool = tree.children[0]
        sub = next(c for c in pool.children if c.type == "Table")
        sub_pool = sub.children[0]
        assert sub_pool.type == "Pool"
        assert abs(sub_pool.chance - 0.5) < 1e-9

    def test_cycle_detection(self):
        p = TreasureParser()
        p.load_data(CYCLE_TXT)
        # Should not raise / recurse infinitely
        tree = p.build_loot_tree("CycleA")
        assert tree is not None
        # The cycle node must appear as Table_Cycle somewhere
        def has_cycle_node(node, depth=0):
            if node.type == "Table_Cycle":
                return True
            if depth > 10:
                return False
            return any(has_cycle_node(c, depth + 1) for c in node.children)
        assert has_cycle_node(tree)

    def test_startlevel_filtering(self):
        p = TreasureParser()
        p.load_data(LEVEL_TXT)
        # At level 3: HighItem requires StartLevel 5, should be filtered out
        tree = p.build_loot_tree("LevelTable", level=3)
        pool = tree.children[0] if tree.children else None
        if pool:
            names = [c.name for c in pool.children]
            assert "HighItem" not in names

    def test_startlevel_included_at_correct_level(self):
        p = TreasureParser()
        p.load_data(LEVEL_TXT)
        # At level 10: HighItem's StartLevel 5 is satisfied
        tree = p.build_loot_tree("LevelTable", level=10)
        pool = tree.children[0] if tree.children else None
        if pool:
            names = [c.name for c in pool.children]
            assert "HighItem" in names

    def test_i_prefix_item_cleaned(self, tiny_parser):
        """Items referenced as new "I_SomeItem" should strip the I_ prefix."""
        tree = tiny_parser.build_loot_tree("SubTable_A")
        pool = tree.children[0]
        names = [c.name for c in pool.children]
        assert "SomeItem" in names


# ─── StatsManager ─────────────────────────────────────────────────────────────

class TestStatsManager:
    def test_builds_category_map(self, tiny_resolved_stats):
        sm = StatsManager(tiny_resolved_stats)
        assert "ClothUpperBody" in sm.category_map
        assert "LeatherUpperBody" in sm.category_map

    def test_multi_category_item_in_both_buckets(self, tiny_resolved_stats):
        sm = StatsManager(tiny_resolved_stats)
        cloth = [i["id"] for i in sm.category_map["ClothUpperBody"]]
        leather = [i["id"] for i in sm.category_map["LeatherUpperBody"]]
        assert "ARM_MultiCat" in cloth
        assert "ARM_MultiCat" in leather

    def test_get_items_for_category_no_level_filter(self, tiny_stats_manager):
        items = tiny_stats_manager.get_items_for_category("ClothUpperBody")
        ids = [i["id"] for i in items]
        assert "ARM_Child" in ids
        assert "ARM_MultiCat" in ids

    def test_get_items_for_category_level_filter_excludes(self, tiny_stats_manager):
        # ARM_Child has MinLevel 3; at level 2 it should be excluded
        items = tiny_stats_manager.get_items_for_category("ClothUpperBody", current_level=2)
        ids = [i["id"] for i in items]
        assert "ARM_Child" not in ids

    def test_get_items_for_category_level_filter_includes(self, tiny_stats_manager):
        # ARM_Child has MinLevel 3; at level 5 it should be included
        items = tiny_stats_manager.get_items_for_category("ClothUpperBody", current_level=5)
        ids = [i["id"] for i in items]
        assert "ARM_Child" in ids

    def test_is_valid_item_id_present(self, tiny_stats_manager):
        assert tiny_stats_manager.is_valid_item_id("ARM_Child")

    def test_is_valid_item_id_absent(self, tiny_stats_manager):
        assert not tiny_stats_manager.is_valid_item_id("NonExistent")

    def test_get_item_min_level_direct(self, tiny_stats_manager):
        assert tiny_stats_manager.get_item_min_level("ARM_Child") == 3

    def test_get_item_min_level_i_prefix_stripped(self, tiny_stats_manager):
        # "I_ARM_Child" → looks up "ARM_Child"
        assert tiny_stats_manager.get_item_min_level("I_ARM_Child") == 3

    def test_get_item_min_level_missing(self, tiny_stats_manager):
        assert tiny_stats_manager.get_item_min_level("NonExistent") == 0

    def test_get_category_info(self, tiny_stats_manager):
        info = tiny_stats_manager.get_category_info("ClothUpperBody")
        assert isinstance(info, list)
        assert all("id" in entry and "min_level" in entry for entry in info)

    def test_category_items_have_data(self, tiny_stats_manager):
        items = tiny_stats_manager.get_items_for_category("ClothUpperBody")
        assert all("data" in i for i in items)


# ─── flatten_probabilities ───────────────────────────────────────────────────

class TestFlattenProbabilities:
    def _single_item_tree(self):
        """A Table → Pool(1.0) → Item tree."""
        root = LootNode("Root", "Table")
        pool = LootNode("Pool", "Pool", chance=1.0, min_qty=1, max_qty=1)
        item = LootNode("Sword", "Item", chance=1.0)
        pool.add_child(item)
        root.add_child(pool)
        return root

    def _two_equal_items_tree(self):
        """A Table → Pool(1.0) → [Item(0.5), Item(0.5)] tree."""
        root = LootNode("Root", "Table")
        pool = LootNode("Pool", "Pool", chance=1.0)
        pool.add_child(LootNode("Sword", "Item", chance=0.5))
        pool.add_child(LootNode("Bow", "Item", chance=0.5))
        root.add_child(pool)
        return root

    def _pool_with_chance_tree(self, pool_chance):
        """Table → Pool(pool_chance) → Item(1.0)."""
        root = LootNode("Root", "Table")
        pool = LootNode("Pool", "Pool", chance=pool_chance)
        pool.add_child(LootNode("Ring", "Item", chance=1.0))
        root.add_child(pool)
        return root

    def test_single_item_probability_one(self):
        p = TreasureParser()
        result = p.flatten_probabilities(self._single_item_tree())
        assert "Sword" in result
        assert abs(result["Sword"]["prob"] - 1.0) < 1e-9

    def test_two_equal_items_each_half(self):
        p = TreasureParser()
        result = p.flatten_probabilities(self._two_equal_items_tree())
        assert abs(result["Sword"]["prob"] - 0.5) < 1e-9
        assert abs(result["Bow"]["prob"] - 0.5) < 1e-9

    def test_pool_chance_reduces_item_prob(self):
        p = TreasureParser()
        result = p.flatten_probabilities(self._pool_with_chance_tree(0.8))
        assert abs(result["Ring"]["prob"] - 0.8) < 1e-9

    def test_qty_propagated(self):
        root = LootNode("Root", "Table")
        pool = LootNode("Pool", "Pool", chance=1.0, min_qty=2, max_qty=3)
        pool.add_child(LootNode("Gold", "Item", chance=1.0))
        root.add_child(pool)
        p = TreasureParser()
        result = p.flatten_probabilities(root)
        assert result["Gold"]["min_qty"] == 2
        assert result["Gold"]["max_qty"] == 3


# ─── Integration: real TreasureTable.txt ─────────────────────────────────────

@pytest.mark.integration
class TestRealTreasureTable:
    def test_loads_without_error(self, real_treasure_table_txt):
        from dos2_tools.core.parsers import parse_treasure_table
        data = parse_treasure_table(real_treasure_table_txt)
        assert data and len(data) > 0

    def test_known_tables_present(self, real_treasure_table_txt):
        from dos2_tools.core.parsers import parse_treasure_table
        p = TreasureParser()
        p.load_data(parse_treasure_table(real_treasure_table_txt))
        assert "ST_SourceSkillBook" in p.tables
        assert "Gen_ResurrectScroll" in p.tables

    def test_source_skillbook_tree(self, real_treasure_table_txt):
        from dos2_tools.core.parsers import parse_treasure_table
        p = TreasureParser()
        p.load_data(parse_treasure_table(real_treasure_table_txt))
        tree = p.build_loot_tree("ST_SourceSkillBook")
        assert tree.type == "Table"
        # Should have at least one pool
        assert len(tree.children) >= 1

    def test_resurrect_scroll_pool_is_guaranteed(self, real_treasure_table_txt):
        """Gen_ResurrectScroll uses rule '-1' = always 1 item."""
        from dos2_tools.core.parsers import parse_treasure_table
        p = TreasureParser()
        p.load_data(parse_treasure_table(real_treasure_table_txt))
        tree = p.build_loot_tree("Gen_ResurrectScroll")
        assert len(tree.children) >= 1
        pool = tree.children[0]
        assert pool.chance == 1.0
