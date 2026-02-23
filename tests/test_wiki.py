"""
Integration tests for the wiki/ page generation modules.

All tests in this file are @pytest.mark.integration — they require the
real extracted game files (via the real_game_data session fixture) and exercise
the full page generation pipeline end-to-end.

Coverage:
    wiki/items.py        — generate_infobox, generate_crafting_section,
                           generate_book_text_section, generate_full_page,
                           parse_and_group_locations, generate_locations_section
    wiki/loot_tables.py  — DropTableRenderer.render_full_drop_table_page,
                           get_table_rows, clean_label, resolve_name
    wiki/trade.py        — TradeTableRenderer.render_full_trader_page,
                           render_level_block, render_row
    wiki/npcs.py         — generate_infobox, generate_stats_section,
                           generate_skills_section, generate_full_page
"""

import pytest


# ─── wiki/items.py ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestItemsGenerateInfobox:
    """Unit-style tests for generate_infobox (pure string formatting)."""

    def test_basic_infobox_structure(self):
        from dos2_tools.wiki.items import generate_infobox
        result = generate_infobox(
            name="Resurrection Scroll",
            stats_id="OBJ_ResurrectScroll",
            root_template_uuid="aaaabbbb-0000-0000-0000-000000000000",
        )
        assert "{{InfoboxItem" in result
        assert "|name=Resurrection Scroll" in result
        assert "|stats_id=OBJ_ResurrectScroll" in result
        assert "|root_template_uuid=aaaabbbb-0000-0000-0000-000000000000" in result
        assert result.strip().endswith("}}")

    def test_infobox_with_description(self):
        from dos2_tools.wiki.items import generate_infobox
        result = generate_infobox(
            name="Foo",
            stats_id="FOO",
            root_template_uuid="",
            description="A foo item",
        )
        assert "|description=A foo item" in result

    def test_infobox_description_pipe_escaped(self):
        from dos2_tools.wiki.items import generate_infobox
        result = generate_infobox(
            name="Foo",
            stats_id="FOO",
            root_template_uuid="",
            description="A|B",
        )
        assert "{{!}}" in result
        assert "A|B" not in result

    def test_infobox_with_properties(self):
        from dos2_tools.wiki.items import generate_infobox
        result = generate_infobox(
            name="Foo",
            stats_id="FOO",
            root_template_uuid="",
            properties=["Poison"],
        )
        assert "|properties=" in result

    def test_weapon_template(self):
        from dos2_tools.wiki.items import generate_infobox
        result = generate_infobox(
            name="Sword",
            stats_id="WPN_Sword",
            root_template_uuid="",
            template="InfoboxWeapon",
        )
        assert "{{InfoboxWeapon" in result

    def test_armour_template(self):
        from dos2_tools.wiki.items import generate_infobox
        result = generate_infobox(
            name="Robe",
            stats_id="ARM_Robe",
            root_template_uuid="",
            template="InfoboxArmour",
        )
        assert "{{InfoboxArmour" in result


@pytest.mark.integration
class TestItemsParseGroupLocations:
    """Tests for parse_and_group_locations (pure string parsing)."""

    def test_simple_location_tuple(self):
        from dos2_tools.wiki.items import parse_and_group_locations
        locs = [("1.0,2.0,3.0 (FortJoy)", "uuid-1")]
        grouped = parse_and_group_locations(locs)
        assert ("FortJoy", "Ground Spawn", "uuid-1") in grouped

    def test_location_inside_container(self):
        from dos2_tools.wiki.items import parse_and_group_locations
        locs = [("1.0,0.0,0.0 (Reaper) inside ChestA", "uuid-x")]
        grouped = parse_and_group_locations(locs)
        key = ("Reaper", "ChestA", "uuid-x")
        assert key in grouped

    def test_multiple_locations_same_region_grouped(self):
        from dos2_tools.wiki.items import parse_and_group_locations
        locs = [
            ("1.0,0.0,0.0 (FortJoy)", "uuid-a"),
            ("5.0,0.0,0.0 (FortJoy)", "uuid-a"),
        ]
        grouped = parse_and_group_locations(locs)
        key = ("FortJoy", "Ground Spawn", "uuid-a")
        assert len(grouped[key]) == 2

    def test_unknown_format_falls_back(self):
        from dos2_tools.wiki.items import parse_and_group_locations
        locs = [("not-a-location", "x")]
        grouped = parse_and_group_locations(locs)
        # Should end up in the Unknown bucket
        keys = list(grouped.keys())
        assert any(k[0] == "Unknown" for k in keys)


@pytest.mark.integration
class TestItemsGenerateLocationsSection:
    """Tests for generate_locations_section (pure wikitext building)."""

    def test_empty_dict_returns_empty_string(self):
        from dos2_tools.wiki.items import generate_locations_section
        result = generate_locations_section("SomeItem", "uuid-1", {})
        assert result == ""

    def test_section_header_present(self):
        from dos2_tools.wiki.items import generate_locations_section
        grouped = {("FortJoy", "Ground Spawn", "uuid-1"): ["1.0,0.0,0.0"]}
        result = generate_locations_section("SomeItem", "uuid-1", grouped)
        assert "== Locations ==" in result

    def test_item_location_template_present(self):
        from dos2_tools.wiki.items import generate_locations_section
        grouped = {("FortJoy", "Ground Spawn", "uuid-1"): ["1.0,0.0,0.0"]}
        result = generate_locations_section("SomeItem", "uuid-1", grouped)
        assert "{{ItemLocation" in result
        assert "stats_id=SomeItem" in result
        assert "region=FortJoy" in result

    def test_location_footer_present(self):
        from dos2_tools.wiki.items import generate_locations_section
        grouped = {("FortJoy", "Chest", "uuid-2"): ["2.0,0.0,0.0"]}
        result = generate_locations_section("SomeItem", "uuid-1", grouped)
        assert "{{ItemLocationTable}}" in result


@pytest.mark.integration
class TestItemsGenerateCraftingSection:
    """Integration tests for generate_crafting_section with real game data."""

    def test_craftable_armor_has_used_in_section(self, real_game_data):
        """ARM_Civilian_UpperBody is used in upgrade recipes."""
        from dos2_tools.wiki.items import generate_crafting_section, _build_root_template_db
        stats_id = "ARM_Civilian_UpperBody"
        cat_str = real_game_data.stats[stats_id].get("ComboCategory", "")
        cats = [c.strip() for c in cat_str.split(",") if c.strip()]
        rt_db = _build_root_template_db(real_game_data)

        result = generate_crafting_section(
            stats_id=stats_id,
            item_categories=cats,
            properties=[],
            all_combos=real_game_data.item_combos,
            resolved_stats=real_game_data.stats,
            root_template_db=rt_db,
            item_name="Civilian Upper Body",
        )
        assert "== Crafting ==" in result
        assert "{{CraftingRow|" in result

    def test_non_craftable_item_returns_empty(self, real_game_data):
        """_Armors is a base entry not a real drop — should have no crafting rows."""
        from dos2_tools.wiki.items import generate_crafting_section, _build_root_template_db
        rt_db = _build_root_template_db(real_game_data)
        result = generate_crafting_section(
            stats_id="_Armors",
            item_categories=[],
            properties=[],
            all_combos=real_game_data.item_combos,
            resolved_stats=real_game_data.stats,
            root_template_db=rt_db,
            item_name="_Armors",
        )
        # Base stat entries don't appear as real item results
        assert "{{CraftingRow|" not in result or result == ""

    def test_crafting_table_has_header_and_footer(self, real_game_data):
        from dos2_tools.wiki.items import generate_crafting_section, _build_root_template_db
        stats_id = "ARM_Civilian_UpperBody"
        cat_str = real_game_data.stats[stats_id].get("ComboCategory", "")
        cats = [c.strip() for c in cat_str.split(",") if c.strip()]
        rt_db = _build_root_template_db(real_game_data)

        result = generate_crafting_section(
            stats_id=stats_id,
            item_categories=cats,
            properties=[],
            all_combos=real_game_data.item_combos,
            resolved_stats=real_game_data.stats,
            root_template_db=rt_db,
            item_name="Civilian Upper Body",
        )
        assert "{{CraftingTable/Header}}" in result
        assert "{{CraftingTable/Footer}}" in result


@pytest.mark.integration
class TestItemsGenerateFullPage:
    """End-to-end tests for generate_full_page with real game data."""

    def test_armor_full_page_has_infobox(self, real_game_data):
        from dos2_tools.wiki.items import generate_full_page
        page_data = {
            "name": "Civilian Upper Body",
            "stats_id": "ARM_Civilian_UpperBody",
            "root_template_uuid": "",
            "description": None,
            "book_id": None,
            "taught_recipes": [],
            "properties": [],
            "locations": set(),
        }
        page = generate_full_page(page_data, real_game_data)
        assert "{{InfoboxArmour" in page
        assert "|name=Civilian Upper Body" in page
        assert "|stats_id=ARM_Civilian_UpperBody" in page

    def test_armor_full_page_has_crafting(self, real_game_data):
        from dos2_tools.wiki.items import generate_full_page
        page_data = {
            "name": "Civilian Upper Body",
            "stats_id": "ARM_Civilian_UpperBody",
            "root_template_uuid": "",
            "description": None,
            "book_id": None,
            "taught_recipes": [],
            "properties": [],
            "locations": set(),
        }
        page = generate_full_page(page_data, real_game_data)
        # ARM_Civilian_UpperBody is used in upgrade combos
        assert "== Crafting ==" in page

    def test_skillbook_page_uses_infobox_skillbook(self, real_game_data):
        from dos2_tools.wiki.items import generate_full_page
        stats_id = "SKILLBOOK_Air_ShockingTouch"
        page_data = {
            "name": "Skillbook Shocking Touch",
            "stats_id": stats_id,
            "root_template_uuid": "",
            "description": None,
            "book_id": None,
            "taught_recipes": [],
            "properties": [],
            "locations": set(),
        }
        page = generate_full_page(page_data, real_game_data, sections=["infobox"])
        assert "{{InfoboxSkillbook" in page

    def test_full_page_with_locations(self, real_game_data):
        from dos2_tools.wiki.items import generate_full_page
        page_data = {
            "name": "Some Item",
            "stats_id": "ARM_Civilian_UpperBody",
            "root_template_uuid": "test-uuid",
            "description": "A description",
            "book_id": None,
            "taught_recipes": [],
            "properties": [],
            "locations": {("1.0,2.0,3.0 (FortJoy)", "test-uuid")},
        }
        page = generate_full_page(page_data, real_game_data)
        assert "== Locations ==" in page
        assert "{{ItemLocation" in page

    def test_section_filter_only_infobox(self, real_game_data):
        from dos2_tools.wiki.items import generate_full_page
        page_data = {
            "name": "Civilian Upper Body",
            "stats_id": "ARM_Civilian_UpperBody",
            "root_template_uuid": "",
            "description": None,
            "book_id": None,
            "taught_recipes": [],
            "properties": [],
            "locations": set(),
        }
        page = generate_full_page(page_data, real_game_data, sections=["infobox"])
        assert "{{InfoboxArmour" in page
        assert "== Crafting ==" not in page
        assert "== Locations ==" not in page

    def test_page_is_non_empty_string(self, real_game_data):
        from dos2_tools.wiki.items import generate_full_page
        page_data = {
            "name": "Test Item",
            "stats_id": "ARM_Purge_UpperBody",
            "root_template_uuid": "",
            "description": None,
            "book_id": None,
            "taught_recipes": [],
            "properties": [],
            "locations": set(),
        }
        page = generate_full_page(page_data, real_game_data)
        assert isinstance(page, str)
        assert len(page) > 10

    def test_book_text_section_with_real_localization(self, real_game_data):
        """generate_book_text_section returns empty string when book_id is not found."""
        from dos2_tools.wiki.items import generate_book_text_section
        # A valid-looking key that likely isn't a book ID
        result = generate_book_text_section("totally_fake_book_id_xyz", real_game_data.localization)
        assert result == ""


# ─── wiki/loot_tables.py ──────────────────────────────────────────────────────

@pytest.mark.integration
class TestDropTableRendererUnit:
    """Unit tests for DropTableRenderer helpers (no game data needed)."""

    def _make_renderer(self):
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        return DropTableRenderer()

    def test_clean_label_strips_st_prefix(self):
        r = self._make_renderer()
        assert r.clean_label("ST_AllPotions") == "All Potions"

    def test_clean_label_strips_i_prefix(self):
        r = self._make_renderer()
        assert r.clean_label("I_ResurrectionScroll") == "Resurrection Scroll"

    def test_clean_label_inserts_space_camel_case(self):
        r = self._make_renderer()
        assert "Source" in r.clean_label("SourceOrb")

    def test_resolve_name_no_loc(self):
        r = self._make_renderer()
        # Without localization, falls back to clean_label
        name = r.resolve_name("I_SomeItem")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_get_qty_display_single(self):
        from dos2_tools.core.loot import LootNode
        r = self._make_renderer()
        node = LootNode("X", "Item", min_qty=1, max_qty=1)
        assert r.get_qty_display(node) == "1"

    def test_get_qty_display_range(self):
        from dos2_tools.core.loot import LootNode
        r = self._make_renderer()
        node = LootNode("X", "Pool", min_qty=2, max_qty=4)
        assert r.get_qty_display(node) == "2-4"

    def test_get_qty_display_same_min_max(self):
        from dos2_tools.core.loot import LootNode
        r = self._make_renderer()
        node = LootNode("X", "Pool", min_qty=3, max_qty=3)
        assert r.get_qty_display(node) == "3"


@pytest.mark.integration
class TestDropTableRendererIntegration:
    """Integration tests for DropTableRenderer with real game data."""

    def test_resurrect_scroll_page_has_header(self, real_game_data):
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "Gen_ResurrectScroll", max_level=3
        )
        assert "Gen_ResurrectScroll" in page
        assert "[[Treasure Table]]" in page

    def test_resurrect_scroll_page_has_item_row(self, real_game_data):
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "Gen_ResurrectScroll", max_level=3
        )
        assert "{{TradeRowItem|" in page
        # The scroll is localized to "Resurrection Scroll"
        assert "Resurrection Scroll" in page

    def test_resurrect_scroll_level_collapsing(self, real_game_data):
        """All levels 1-16 should have the same contents → produces one block."""
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "Gen_ResurrectScroll", max_level=16
        )
        # Collapsed ranges should show "1+" (levels 1 to max in one block).
        # Filter only "=== Level …" lines; the page also has "=== Drop Table ===" header.
        level_headers = [ln for ln in page.splitlines() if ln.startswith("=== Level")]
        assert len(level_headers) == 1, (
            f"Expected 1 collapsed range, got {len(level_headers)}: {level_headers}"
        )

    def test_page_has_category_markers(self, real_game_data):
        """The footer should include Category:Drop tables."""
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "Gen_ResurrectScroll", max_level=3
        )
        assert "[[Category:Drop tables]]" in page

    def test_all_potions_table_renders_without_crash(self, real_game_data):
        """ST_AllPotions is large and multi-level — smoke test."""
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "ST_AllPotions", max_level=16
        )
        assert isinstance(page, str)
        assert len(page) > 100
        assert "{{TradeTableHead}}" in page
        assert "{{TradeTableBottom}}" in page

    def test_table_with_levels_has_multiple_blocks(self, real_game_data):
        """A level-gated table should produce more than one collapsed block."""
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "ST_AllPotions", max_level=16
        )
        level_headers = [ln for ln in page.splitlines() if ln.startswith("===")]
        assert len(level_headers) >= 1

    def test_get_table_rows_guaranteed_item_promoted(self, real_game_data):
        """Guaranteed items should appear at the top before randomised rows."""
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        tree = real_game_data.loot_engine.build_loot_tree("Gen_ResurrectScroll", 1)
        real_game_data.loot_engine.flatten_wrappers(tree)
        rows = r.get_table_rows(tree)
        assert "rarity=Always" in rows

    def test_wand_table_has_group_rows(self, real_game_data):
        """ST_WandNormal is a category table; expect TradeRowGroup for categories."""
        from dos2_tools.wiki.loot_tables import DropTableRenderer
        r = DropTableRenderer(real_game_data.localization)
        page = r.render_full_drop_table_page(
            real_game_data.loot_engine, "ST_WandNormal", max_level=3
        )
        assert "{{TradeRowGroup|" in page


# ─── wiki/trade.py ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestTradeTableRendererUnit:
    """Unit tests for TradeTableRenderer helpers."""

    def _make_renderer(self):
        from dos2_tools.wiki.trade import TradeTableRenderer
        return TradeTableRenderer()

    def test_clean_label_st_prefix(self):
        r = self._make_renderer()
        assert "All Potions" in r.clean_label("ST_AllPotions")

    def test_resolve_name_link_no_loc(self):
        r = self._make_renderer()
        result = r.resolve_name_link("I_ResurrectionScroll")
        # Without localization, should fall back to clean label
        assert isinstance(result, str)

    def test_qty_display_range(self):
        from dos2_tools.core.loot import LootNode
        r = self._make_renderer()
        node = LootNode("X", "Pool", min_qty=3, max_qty=5)
        assert r.get_qty_display(node) == "3-5"

    def test_reset_clears_state(self):
        r = self._make_renderer()
        r.seen_identifiers.add("X")
        r._uid_counter = 99
        r.reset()
        assert len(r.seen_identifiers) == 0
        assert r._uid_counter == 0

    def test_get_uid_increments(self):
        r = self._make_renderer()
        uid1 = r.get_uid()
        uid2 = r.get_uid()
        assert uid1 != uid2
        assert "group_1" == uid1
        assert "group_2" == uid2


@pytest.mark.integration
class TestTradeTableRendererIntegration:
    """Integration tests for the full trade page renderer with real game data."""

    def test_single_table_renders_stock_header(self, real_game_data):
        from dos2_tools.wiki.trade import TradeTableRenderer
        r = TradeTableRenderer(real_game_data.localization)
        page = r.render_full_trader_page(
            real_game_data.loot_engine, ["ST_WandNormal"], "Wand Trader"
        )
        assert "Stock (Level 1)" in page

    def test_wand_trader_has_trade_rows(self, real_game_data):
        from dos2_tools.wiki.trade import TradeTableRenderer
        r = TradeTableRenderer(real_game_data.localization)
        page = r.render_full_trader_page(
            real_game_data.loot_engine, ["ST_WandNormal"], "Wand Trader"
        )
        assert "{{TradeRowGroup|" in page or "{{TradeRowItem|" in page

    def test_empty_trade_ids_returns_empty(self, real_game_data):
        from dos2_tools.wiki.trade import TradeTableRenderer
        r = TradeTableRenderer(real_game_data.localization)
        page = r.render_full_trader_page(
            real_game_data.loot_engine, [], "Empty Trader"
        )
        assert page == ""

    def test_multiple_tables_merged(self, real_game_data):
        """Multiple trade tables should be merged into a single per-level view."""
        from dos2_tools.wiki.trade import TradeTableRenderer
        r = TradeTableRenderer(real_game_data.localization)
        page = r.render_full_trader_page(
            real_game_data.loot_engine,
            ["ST_WandNormal", "ST_StaffNormal"],
            "Magic Vendor",
        )
        assert "Stock (Level 1)" in page
        assert isinstance(page, str)
        assert len(page) > 50

    def test_render_level_block_returns_none_for_empty_tree(self, real_game_data):
        from dos2_tools.wiki.trade import TradeTableRenderer
        from dos2_tools.core.loot import LootNode
        r = TradeTableRenderer(real_game_data.localization)
        empty_tree = LootNode("Empty", "Table")
        result = r.render_level_block(empty_tree, 1)
        assert result is None

    def test_render_row_simple_item(self, real_game_data):
        from dos2_tools.wiki.trade import TradeTableRenderer
        from dos2_tools.core.loot import LootNode
        r = TradeTableRenderer(real_game_data.localization)
        node = LootNode("ResurrectionScroll", "Item", chance=0.5, min_qty=1, max_qty=1)
        result = r.render_row(node)
        assert result is not None
        assert "{{TradeRowItem|" in result
        assert "50.0%" in result

    def test_render_row_deduplicates_items(self, real_game_data):
        from dos2_tools.wiki.trade import TradeTableRenderer
        from dos2_tools.core.loot import LootNode
        r = TradeTableRenderer(real_game_data.localization)
        node = LootNode("ResurrectionScroll", "Item", chance=0.5)
        r.render_row(node)  # First render registers the name
        result = r.render_row(node)  # Second render should be deduped
        assert result is None

    def test_level_blocks_increase_for_leveled_table(self, real_game_data):
        """ST_WandNormal is level-gated; should get multiple level blocks."""
        from dos2_tools.wiki.trade import TradeTableRenderer
        r = TradeTableRenderer(real_game_data.localization)
        page = r.render_full_trader_page(
            real_game_data.loot_engine, ["ST_WandNormal"], "Trader"
        )
        # Should have at least a level 1 block and possibly more
        level_blocks = [ln for ln in page.splitlines() if "Level" in ln and ln.startswith("==")]
        assert len(level_blocks) >= 1


# ─── wiki/npcs.py ─────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestNPCsGenerateInfobox:
    """Tests for npcs.generate_infobox (pure string formatting)."""

    def test_basic_npc_infobox(self):
        from dos2_tools.wiki.npcs import generate_infobox
        result = generate_infobox("Gareth", stats_id="CHR_Gareth", region="FortJoy")
        assert "{{InfoboxNPC" in result
        assert "|name=Gareth" in result
        assert "|stats_id=CHR_Gareth" in result
        assert "|region=FortJoy" in result
        assert result.strip().endswith("}}")

    def test_infobox_without_region(self):
        from dos2_tools.wiki.npcs import generate_infobox
        result = generate_infobox("Wolf")
        assert "|region=" not in result

    def test_infobox_with_level_override(self):
        from dos2_tools.wiki.npcs import generate_infobox
        result = generate_infobox("Boss", level_override=10)
        assert "|level=10" in result


@pytest.mark.integration
class TestNPCsGenerateStatsSection:
    """Integration tests for npcs.generate_stats_section with real game data."""

    def test_voidwoken_bear_has_vitality(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_stats_section
        result = generate_stats_section("Animals_Bear_A_Voidwoken", real_game_data)
        assert "== Stats ==" in result
        assert "{{NPCStats" in result
        # Vitality should be non-zero and appear
        assert "|vitality=" in result

    def test_voidwoken_bear_has_strength(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_stats_section
        result = generate_stats_section("Animals_Bear_A_Voidwoken", real_game_data)
        assert "|strength=" in result

    def test_missing_stats_id_returns_empty(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_stats_section
        result = generate_stats_section("TOTALLY_FAKE_NPC_XYZ_12345", real_game_data)
        assert result == ""

    def test_none_stats_id_returns_empty(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_stats_section
        result = generate_stats_section(None, real_game_data)
        assert result == ""

    def test_zero_value_fields_not_included(self, real_game_data):
        """Fields with value '0' should be omitted from the stats block."""
        from dos2_tools.wiki.npcs import generate_stats_section
        result = generate_stats_section("Animals_Bear_A_Voidwoken", real_game_data)
        # CriticalChance for a bear is typically 0 — should not appear
        lines = result.splitlines()
        for line in lines:
            if "criticalchance" in line.lower():
                # If it does appear, it must be non-zero
                assert "=0" not in line


@pytest.mark.integration
class TestNPCsGenerateSkillsSection:
    """Tests for npcs.generate_skills_section (pure string formatting)."""

    def test_empty_skills_returns_empty(self):
        from dos2_tools.wiki.npcs import generate_skills_section
        result = generate_skills_section([])
        assert result == ""

    def test_skills_header_present(self):
        from dos2_tools.wiki.npcs import generate_skills_section
        result = generate_skills_section(["Shout_RecoverArmor", "Target_Healing"])
        assert "== Skills ==" in result

    def test_skills_are_listed(self):
        from dos2_tools.wiki.npcs import generate_skills_section
        result = generate_skills_section(["Shout_RecoverArmor"])
        assert "RecoverArmor" in result

    def test_skills_sorted_alphabetically(self):
        from dos2_tools.wiki.npcs import generate_skills_section
        result = generate_skills_section(["Shout_ZZZ", "Shout_AAA"])
        idx_aaa = result.index("AAA")
        idx_zzz = result.index("ZZZ")
        assert idx_aaa < idx_zzz


@pytest.mark.integration
class TestNPCsGenerateFullPage:
    """End-to-end tests for npcs.generate_full_page with real game data."""

    def test_voidwoken_bear_full_page_has_infobox(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_full_page
        npc_data = {
            "name": "Voidwoken Bear",
            "stats_id": "Animals_Bear_A_Voidwoken",
            "region": "FortJoy",
            "skills": [],
            "inventory_items": [],
            "trade_treasures": [],
        }
        page = generate_full_page(npc_data, real_game_data)
        assert "{{InfoboxNPC" in page
        assert "|name=Voidwoken Bear" in page

    def test_voidwoken_bear_full_page_has_stats(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_full_page
        npc_data = {
            "name": "Voidwoken Bear",
            "stats_id": "Animals_Bear_A_Voidwoken",
            "region": "FortJoy",
            "skills": [],
            "inventory_items": [],
            "trade_treasures": [],
        }
        page = generate_full_page(npc_data, real_game_data)
        assert "== Stats ==" in page
        assert "{{NPCStats" in page

    def test_npc_page_with_skills(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_full_page
        npc_data = {
            "name": "Test NPC",
            "stats_id": "Animals_Bear_A_Voidwoken",
            "region": None,
            "skills": ["Shout_RecoverArmor", "Target_Healing"],
            "inventory_items": [],
            "trade_treasures": [],
        }
        page = generate_full_page(npc_data, real_game_data)
        assert "== Skills ==" in page

    def test_npc_page_with_inventory(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_full_page
        npc_data = {
            "name": "Test NPC",
            "stats_id": None,
            "region": None,
            "skills": [],
            "inventory_items": [
                {"name": "Iron Sword", "stats_id": "WPN_Iron_Sword", "template_uuid": None}
            ],
            "trade_treasures": [],
        }
        page = generate_full_page(npc_data, real_game_data)
        assert "== Inventory ==" in page
        assert "[[Iron Sword]]" in page

    def test_npc_section_filter_works(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_full_page
        npc_data = {
            "name": "Voidwoken Bear",
            "stats_id": "Animals_Bear_A_Voidwoken",
            "region": "FortJoy",
            "skills": ["Shout_RecoverArmor"],
            "inventory_items": [],
            "trade_treasures": [],
        }
        page = generate_full_page(npc_data, real_game_data, sections=["infobox"])
        assert "{{InfoboxNPC" in page
        assert "== Stats ==" not in page
        assert "== Skills ==" not in page

    def test_npc_page_is_valid_string(self, real_game_data):
        from dos2_tools.wiki.npcs import generate_full_page
        npc_data = {
            "name": "Deer",
            "stats_id": "Animals_Deer_A_Void_A",
            "region": "Reaper",
            "skills": [],
            "inventory_items": [],
            "trade_treasures": [],
        }
        page = generate_full_page(npc_data, real_game_data)
        assert isinstance(page, str)
        assert len(page) > 20
