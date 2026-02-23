"""
Tests for core/parsers.py — file format parsers.

Unit tests use tmp_path to write small inline fixtures.
Integration tests (@pytest.mark.integration) hit real extracted game files.
"""

import os
import pytest
from collections import OrderedDict


# ─── parse_stats_txt (unit) ──────────────────────────────────────────────────

class TestParseStatsTxt:
    def test_basic_entry(self, tmp_path):
        from dos2_tools.core.parsers import parse_stats_txt
        f = tmp_path / "test.txt"
        f.write_text(
            'new entry "MyItem"\n'
            'type "Armor"\n'
            'data "Slot" "Breast"\n'
            'data "Value" "42"\n'
        )
        result = parse_stats_txt(str(f))
        assert "MyItem" in result
        entry = result["MyItem"]
        assert entry["_id"] == "MyItem"
        assert entry["_type"] == "Armor"
        assert entry["_data"]["Slot"] == "Breast"
        assert entry["_data"]["Value"] == "42"

    def test_using_field(self, tmp_path):
        from dos2_tools.core.parsers import parse_stats_txt
        f = tmp_path / "test.txt"
        f.write_text(
            'new entry "Parent"\n'
            'data "X" "1"\n\n'
            'new entry "Child"\n'
            'using "Parent"\n'
            'data "Y" "2"\n'
        )
        result = parse_stats_txt(str(f))
        assert result["Child"]["_using"] == "Parent"
        assert result["Child"]["_data"]["Y"] == "2"

    def test_multiple_entries(self, tmp_path):
        from dos2_tools.core.parsers import parse_stats_txt
        f = tmp_path / "test.txt"
        f.write_text(
            'new entry "A"\ndata "K" "1"\n\n'
            'new entry "B"\ndata "K" "2"\n\n'
            'new entry "C"\ndata "K" "3"\n'
        )
        result = parse_stats_txt(str(f))
        assert set(result.keys()) == {"A", "B", "C"}

    def test_empty_file(self, tmp_path):
        from dos2_tools.core.parsers import parse_stats_txt
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert parse_stats_txt(str(f)) == {}

    def test_missing_file_returns_empty(self):
        from dos2_tools.core.parsers import parse_stats_txt
        result = parse_stats_txt("/nonexistent/path/file.txt")
        assert result == {}

    def test_preserves_insertion_order(self, tmp_path):
        from dos2_tools.core.parsers import parse_stats_txt
        f = tmp_path / "test.txt"
        f.write_text(
            'new entry "E"\n'
            'data "Z" "26"\n'
            'data "A" "1"\n'
        )
        result = parse_stats_txt(str(f))
        keys = list(result["E"]["_data"].keys())
        assert keys == ["Z", "A"]  # OrderedDict preserves insertion order


# ─── parse_xml_localization (unit) ──────────────────────────────────────────

class TestParseXmlLocalization:
    def test_parses_content_nodes(self, tmp_path):
        from dos2_tools.core.parsers import parse_xml_localization
        f = tmp_path / "english.xml"
        f.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<contentList>\n'
            '  <content contentuid="uid001" version="1">Hello World</content>\n'
            '  <content contentuid="uid002" version="1">Goodbye</content>\n'
            '</contentList>\n'
        )
        result = parse_xml_localization(str(f))
        assert result["uid001"] == "Hello World"
        assert result["uid002"] == "Goodbye"

    def test_empty_content(self, tmp_path):
        from dos2_tools.core.parsers import parse_xml_localization
        f = tmp_path / "english.xml"
        f.write_text(
            '<contentList>\n'
            '  <content contentuid="uid003"></content>\n'
            '</contentList>\n'
        )
        result = parse_xml_localization(str(f))
        assert result["uid003"] == ""

    def test_no_contentuid_skipped(self, tmp_path):
        from dos2_tools.core.parsers import parse_xml_localization
        f = tmp_path / "english.xml"
        f.write_text('<contentList><content>No uid here</content></contentList>')
        result = parse_xml_localization(str(f))
        assert result == {}

    def test_empty_path_returns_empty(self):
        from dos2_tools.core.parsers import parse_xml_localization
        assert parse_xml_localization("") == {}

    def test_none_path_returns_empty(self):
        from dos2_tools.core.parsers import parse_xml_localization
        assert parse_xml_localization(None) == {}


# ─── parse_item_combos (unit) ────────────────────────────────────────────────

class TestParseItemCombos:
    def test_single_combo(self, tmp_path):
        from dos2_tools.core.parsers import parse_item_combos
        f = tmp_path / "ItemCombos.txt"
        f.write_text(
            'new ItemCombination "Combo_Foo"\n'
            'data "CraftingStation" "None"\n'
            'data "Ingredient1" "Knife"\n'
            'new ItemCombinationResult "Combo_Foo_Result"\n'
            'data "ResultObject" "WPN_Dagger"\n'
        )
        result = parse_item_combos(str(f))
        assert "Combo_Foo" in result
        combo = result["Combo_Foo"]
        assert combo["Data"]["CraftingStation"] == "None"
        assert combo["Data"]["Ingredient1"] == "Knife"
        assert combo["Results"]["ResultObject"] == "WPN_Dagger"
        assert combo["Giftbag"] is None

    def test_multiple_combos(self, tmp_path):
        from dos2_tools.core.parsers import parse_item_combos
        f = tmp_path / "ItemCombos.txt"
        f.write_text(
            'new ItemCombination "Combo_A"\ndata "X" "1"\n\n'
            'new ItemCombination "Combo_B"\ndata "Y" "2"\n'
        )
        result = parse_item_combos(str(f))
        assert "Combo_A" in result
        assert "Combo_B" in result

    def test_giftbag_detection(self, tmp_path):
        from dos2_tools.core.parsers import parse_item_combos
        # place the file in a path containing a giftbag key
        gb_dir = tmp_path / "CMP_CraftingOverhaul"
        gb_dir.mkdir()
        f = gb_dir / "ItemCombos.txt"
        f.write_text('new ItemCombination "GB_Combo"\ndata "X" "1"\n')
        result = parse_item_combos(str(f))
        assert result["GB_Combo"]["Giftbag"] == "Crafting Overhaul"


# ─── parse_treasure_table (unit) ─────────────────────────────────────────────

class TestParseTreasureTable:
    def test_returns_file_contents(self, tmp_path):
        from dos2_tools.core.parsers import parse_treasure_table
        f = tmp_path / "TreasureTable.txt"
        content = 'new treasuretable "Test"\nnew subtable "1,1"\n'
        f.write_text(content)
        assert parse_treasure_table(str(f)) == content

    def test_missing_file_returns_empty(self):
        from dos2_tools.core.parsers import parse_treasure_table
        assert parse_treasure_table("/nonexistent/TreasureTable.txt") == ""


# ─── parse_item_progression_names (unit) ─────────────────────────────────────

class TestParseItemProgressionNames:
    def test_parses_namegroup(self, tmp_path):
        from dos2_tools.core.parsers import parse_item_progression_names
        f = tmp_path / "ItemProgressionNames.txt"
        f.write_text(
            'new namegroup "SwordGroup"\n'
            'add name "sword_name_uuid","sword_description_uuid"\n'
        )
        result = parse_item_progression_names(str(f))
        assert "SwordGroup" in result
        assert result["SwordGroup"]["name"] == "sword_name_uuid"
        assert result["SwordGroup"]["description"] == "sword_description_uuid"

    def test_missing_file_returns_empty(self):
        from dos2_tools.core.parsers import parse_item_progression_names
        assert parse_item_progression_names("/nonexistent/file.txt") == {}


# ─── Integration: real game files ────────────────────────────────────────────

@pytest.mark.integration
class TestRealStatsParsing:
    def test_armor_txt_returns_entries(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        result = parse_stats_txt(real_armor_txt)
        assert len(result) > 10

    def test_base_armor_entry_exists(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        result = parse_stats_txt(real_armor_txt)
        assert "_Armors" in result

    def test_base_armor_has_slot(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        result = parse_stats_txt(real_armor_txt)
        assert result["_Armors"]["_data"]["Slot"] == "Breast"

    def test_child_entry_has_using(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        result = parse_stats_txt(real_armor_txt)
        assert "ARM_Civilian_UpperBody" in result
        assert result["ARM_Civilian_UpperBody"]["_using"] == "_ClothArmor"

    def test_data_order_preserved(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        result = parse_stats_txt(real_armor_txt)
        entry = result["_Armors"]
        assert isinstance(entry["_data"], OrderedDict)


@pytest.mark.integration
class TestRealTreasureTableParsing:
    def test_parse_returns_nonempty_string(self, real_treasure_table_txt):
        from dos2_tools.core.parsers import parse_treasure_table
        data = parse_treasure_table(real_treasure_table_txt)
        assert len(data) > 100

    def test_known_tables_after_load(self, real_treasure_table_txt):
        from dos2_tools.core.parsers import parse_treasure_table
        from dos2_tools.core.loot import TreasureParser
        p = TreasureParser()
        p.load_data(parse_treasure_table(real_treasure_table_txt))
        assert len(p.tables) >= 10
        assert "ST_SourceSkillBook" in p.tables
