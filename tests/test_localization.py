"""
Tests for core/localization.py — Localization class and load_localization().

Unit tests use in-memory data.
Integration tests use the cache_localization.json file.
"""

import json
import os
import pytest
from dos2_tools.core.localization import Localization


# ─── Localization.get_text ───────────────────────────────────────────────────

class TestLocalizationGetText:
    def test_direct_handle_lookup(self):
        loc = Localization(handle_map={"h001": "Hello"})
        assert loc.get_text("h001") == "Hello"

    def test_uuid_chain_lookup(self):
        loc = Localization(
            handle_map={"h001": "via UUID"},
            uuid_map={"uuid-abc": [{"file": "test.lsj", "handle": "h001"}]},
        )
        assert loc.get_text("uuid-abc") == "via UUID"

    def test_missing_key_returns_none(self):
        loc = Localization(handle_map={"h001": "x"})
        assert loc.get_text("not-here") is None

    def test_none_key_returns_none(self):
        loc = Localization(handle_map={})
        assert loc.get_text(None) is None

    def test_empty_string_key_returns_none(self):
        loc = Localization(handle_map={})
        assert loc.get_text("") is None

    def test_semicolons_stripped(self):
        # Some game entries include trailing semicolons in handle IDs
        loc = Localization(handle_map={"h001": "Text"})
        assert loc.get_text("h001;") == "Text"

    def test_uuid_with_multiple_mappings_sorted(self):
        """get_text should be deterministic: files sorted, first picked."""
        loc = Localization(
            handle_map={"h_a": "From A", "h_b": "From B"},
            uuid_map={
                "uuid-123": [
                    {"file": "z_file.lsj", "handle": "h_b"},
                    {"file": "a_file.lsj", "handle": "h_a"},
                ]
            },
        )
        # Sorted by file: "a_file.lsj" comes first → "From A"
        assert loc.get_text("uuid-123") == "From A"


# ─── Localization.get_handle_text ────────────────────────────────────────────

class TestLocalizationGetHandleText:
    def test_present_handle(self):
        loc = Localization(handle_map={"h999": "The Text"})
        assert loc.get_handle_text("h999") == "The Text"

    def test_absent_handle_returns_none(self):
        loc = Localization(handle_map={})
        assert loc.get_handle_text("h999") is None

    def test_none_handle_returns_none(self):
        loc = Localization(handle_map={})
        assert loc.get_handle_text(None) is None


# ─── Empty / default construction ────────────────────────────────────────────

class TestLocalizationConstruction:
    def test_no_args_safe(self):
        loc = Localization()
        assert loc.get_text("anything") is None
        assert loc.get_handle_text("anything") is None

    def test_handle_map_and_uuid_map_stored(self):
        hm = {"h1": "x"}
        um = {"u1": [{"file": "f.lsj", "handle": "h1"}]}
        loc = Localization(handle_map=hm, uuid_map=um)
        assert loc.handle_map is hm
        assert loc.uuid_map is um


# ─── parse_xml_localization (indirect via load) ───────────────────────────────

class TestParseXmlLocalizationViaLoad:
    def test_xml_file_loaded_into_handle_map(self, tmp_path):
        from dos2_tools.core.parsers import parse_xml_localization
        xml = tmp_path / "english.xml"
        xml.write_text(
            '<contentList>'
            '<content contentuid="hABC">Item Name</content>'
            '</contentList>'
        )
        hm = parse_xml_localization(str(xml))
        loc = Localization(handle_map=hm)
        assert loc.get_handle_text("hABC") == "Item Name"


# ─── Integration: real cache_localization.json ───────────────────────────────

@pytest.mark.integration
class TestRealLocalization:
    @pytest.fixture(scope="class")
    def loc(self, repo_root):
        cache = os.path.join(repo_root, "cache_localization.json")
        assert os.path.exists(cache), f"cache_localization.json not found at {cache}"
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        return Localization(
            handle_map=data.get("handles", {}),
            uuid_map=data.get("uuids", {}),
        )

    def test_handle_map_nonempty(self, loc):
        assert len(loc.handle_map) > 1000

    def test_uuid_map_nonempty(self, loc):
        assert len(loc.uuid_map) > 0

    def test_known_handle_not_none(self, loc):
        """At least some handles should resolve to non-empty text."""
        found = sum(1 for v in loc.handle_map.values() if v)
        assert found > 1000

    def test_get_text_with_valid_handle(self, loc):
        """Any key in handle_map should be retrievable via get_text."""
        some_handle = next(k for k, v in loc.handle_map.items() if v)
        text = loc.get_text(some_handle)
        assert text is not None
        assert isinstance(text, str)
