"""
Integration tests for core/game_data.py — GameData central loader.

All tests are @pytest.mark.integration because they load the actual
extracted game files (using caches where available).

We use the session-scoped `real_game_data` fixture from conftest.py
so data is loaded only once for the entire test session.
"""

import pytest


@pytest.mark.integration
class TestGameDataStats:
    def test_stats_loads(self, real_game_data):
        assert real_game_data.stats is not None
        assert len(real_game_data.stats) > 100

    def test_base_armor_entry_exists(self, real_game_data):
        assert "_Armors" in real_game_data.stats

    def test_base_armor_slot_inherited(self, real_game_data):
        assert real_game_data.stats["_Armors"].get("Slot") == "Breast"

    def test_child_armor_inherits_slot(self, real_game_data):
        civilian = real_game_data.stats.get("ARM_Civilian_UpperBody")
        assert civilian is not None
        assert civilian.get("Slot") == "Breast"

    def test_stats_returns_same_object_on_second_call(self, real_game_data):
        """Verify lazy caching: second access returns the same dict, not a copy."""
        assert real_game_data.stats is real_game_data.stats


@pytest.mark.integration
class TestGameDataLootEngine:
    def test_loot_engine_loads(self, real_game_data):
        engine = real_game_data.loot_engine
        assert engine is not None

    def test_loot_engine_has_tables(self, real_game_data):
        assert len(real_game_data.loot_engine.tables) >= 10

    def test_known_table_present(self, real_game_data):
        assert "ST_SourceSkillBook" in real_game_data.loot_engine.tables

    def test_gen_resurrect_scroll_present(self, real_game_data):
        assert "Gen_ResurrectScroll" in real_game_data.loot_engine.tables

    def test_build_loot_tree_source_skillbook(self, real_game_data):
        tree = real_game_data.loot_engine.build_loot_tree("ST_SourceSkillBook")
        assert tree.type == "Table"
        assert len(tree.children) >= 1

    def test_build_loot_tree_returns_pools(self, real_game_data):
        tree = real_game_data.loot_engine.build_loot_tree("ST_SourceSkillBook")
        pool_children = [c for c in tree.children if c.type == "Pool"]
        assert len(pool_children) >= 1

    def test_resurrect_scroll_pool_guaranteed(self, real_game_data):
        tree = real_game_data.loot_engine.build_loot_tree("Gen_ResurrectScroll")
        assert len(tree.children) >= 1
        pool = tree.children[0]
        assert pool.chance == 1.0

    def test_loot_engine_same_object_on_second_call(self, real_game_data):
        """Verify lazy caching."""
        assert real_game_data.loot_engine is real_game_data.loot_engine


@pytest.mark.integration
class TestGameDataStatsManager:
    def test_stats_manager_loads(self, real_game_data):
        sm = real_game_data.stats_manager
        assert sm is not None

    def test_cloth_upper_body_category_has_items(self, real_game_data):
        items = real_game_data.stats_manager.get_items_for_category("ClothUpperBody")
        assert len(items) > 0

    def test_category_items_have_id_and_data(self, real_game_data):
        items = real_game_data.stats_manager.get_items_for_category("ClothUpperBody")
        for item in items[:5]:
            assert "id" in item
            assert "data" in item

    def test_is_valid_item_id_known_item(self, real_game_data):
        # _BaseArmor or _Armors exists in stats
        assert real_game_data.stats_manager.is_valid_item_id("_Armors")

    def test_is_valid_item_id_unknown(self, real_game_data):
        assert not real_game_data.stats_manager.is_valid_item_id("TotallyFakeItem_XYZ")


@pytest.mark.integration
class TestGameDataFileIndex:
    def test_file_index_loads(self, real_game_data):
        index = real_game_data.file_index
        assert len(index) > 10000

    def test_get_files_pattern_armor(self, real_game_data):
        entries = real_game_data.get_files("armors")
        assert len(entries) >= 1

    def test_get_file_paths_returns_strings(self, real_game_data):
        paths = real_game_data.get_file_paths("treasure_tables")
        assert all(isinstance(p, str) for p in paths)
        assert len(paths) >= 1

    def test_get_files_returns_file_entries(self, real_game_data):
        from dos2_tools.core.data_models import FileEntry
        entries = real_game_data.get_files("armors")
        assert all(isinstance(e, FileEntry) for e in entries)


@pytest.mark.integration
class TestGameDataItemCombos:
    def test_item_combos_load(self, real_game_data):
        combos = real_game_data.item_combos
        assert len(combos) > 0

    def test_combo_properties_load(self, real_game_data):
        props = real_game_data.combo_properties
        assert len(props) > 0

    def test_item_combos_same_object(self, real_game_data):
        """Verify lazy caching."""
        assert real_game_data.item_combos is real_game_data.item_combos


@pytest.mark.integration
class TestGameDataLocalization:
    def test_localization_loads(self, real_game_data):
        loc = real_game_data.localization
        assert loc is not None

    def test_localization_has_handles(self, real_game_data):
        loc = real_game_data.localization
        assert len(loc.handle_map) > 1000

    def test_localization_same_object(self, real_game_data):
        assert real_game_data.localization is real_game_data.localization
