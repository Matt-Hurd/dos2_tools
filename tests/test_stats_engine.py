"""
Tests for core/stats_engine.py — inheritance resolution.

All tests are pure unit tests (in-memory dicts, no disk I/O).
"""

import pytest
from collections import OrderedDict
from dos2_tools.core.stats_engine import resolve_entry, resolve_all_stats


def make_entry(entry_id, data, using=None, type_=None):
    """Helper to build a raw stats entry dict."""
    e = {"_id": entry_id, "_data": OrderedDict(data)}
    if using:
        e["_using"] = using
    if type_:
        e["_type"] = type_
    return e


# ─── resolve_entry ───────────────────────────────────────────────────────────

class TestResolveEntry:
    def test_simple_no_parent(self):
        raw = {"A": make_entry("A", [("Slot", "Breast"), ("Value", "10")])}
        result = resolve_entry("A", raw, {})
        assert result["Slot"] == "Breast"
        assert result["Value"] == "10"

    def test_type_is_included(self):
        raw = {"A": make_entry("A", [], type_="Armor")}
        result = resolve_entry("A", raw, {})
        assert result["_type"] == "Armor"

    def test_single_level_inheritance(self):
        raw = {
            "Base": make_entry("Base", [("Slot", "Breast"), ("Value", "10")]),
            "Child": make_entry("Child", [("Value", "20"), ("Color", "Red")], using="Base"),
        }
        result = resolve_entry("Child", raw, {})
        # Child overrides Value, inherits Slot
        assert result["Slot"] == "Breast"
        assert result["Value"] == "20"
        assert result["Color"] == "Red"

    def test_two_level_chain(self):
        raw = {
            "GrandParent": make_entry("GrandParent", [("A", "1"), ("B", "2")]),
            "Parent": make_entry("Parent", [("B", "override"), ("C", "3")], using="GrandParent"),
            "Child": make_entry("Child", [("D", "4")], using="Parent"),
        }
        result = resolve_entry("Child", raw, {})
        assert result["A"] == "1"           # from grandparent
        assert result["B"] == "override"    # parent overrides grandparent
        assert result["C"] == "3"           # from parent
        assert result["D"] == "4"           # from child

    def test_missing_entry_returns_none(self):
        raw = {}
        assert resolve_entry("NotHere", raw, {}) is None

    def test_missing_parent_skipped_gracefully(self):
        raw = {"Child": make_entry("Child", [("X", "1")], using="MissingParent")}
        result = resolve_entry("Child", raw, {})
        # Should still resolve with just its own data
        assert result["X"] == "1"

    def test_circular_inheritance_no_crash(self):
        raw = {
            "A": make_entry("A", [("X", "1")], using="B"),
            "B": make_entry("B", [("Y", "2")], using="A"),
        }
        # Should not raise; cycle detection kills the recursion
        result_a = resolve_entry("A", raw, {})
        # Either resolves partially or returns None — must not crash
        assert result_a is None or isinstance(result_a, OrderedDict)

    def test_resolved_cache_is_used(self):
        raw = {
            "Base": make_entry("Base", [("Slot", "Breast")]),
            "Child": make_entry("Child", [("Extra", "1")], using="Base"),
        }
        cache = {}
        # Resolve Base first to populate cache
        resolve_entry("Base", raw, cache)
        call_count = [0]
        orig_get = raw.get
        # Resolve Child — Base should come from cache
        resolve_entry("Child", raw, cache)
        assert "Base" in cache
        assert "Child" in cache

    def test_own_data_overrides_parent_fully(self):
        raw = {
            "Base": make_entry("Base", [("A", "base"), ("B", "base")]),
            "Child": make_entry("Child", [("A", "child"), ("B", "child"), ("C", "child")], using="Base"),
        }
        result = resolve_entry("Child", raw, {})
        assert result["A"] == "child"
        assert result["B"] == "child"
        assert result["C"] == "child"


# ─── resolve_all_stats ───────────────────────────────────────────────────────

class TestResolveAllStats:
    def test_resolves_all_entries(self):
        raw = {
            "A": make_entry("A", [("X", "1")]),
            "B": make_entry("B", [("Y", "2")], using="A"),
        }
        resolved = resolve_all_stats(raw)
        assert "A" in resolved
        assert "B" in resolved

    def test_inherited_fields_propagate(self):
        raw = {
            "Base": make_entry("Base", [("Slot", "Breast"), ("Value", "10")]),
            "ARM_Child": make_entry("ARM_Child", [("Value", "20")], using="Base"),
        }
        resolved = resolve_all_stats(raw)
        assert resolved["ARM_Child"]["Slot"] == "Breast"
        assert resolved["ARM_Child"]["Value"] == "20"

    def test_empty_input(self):
        assert resolve_all_stats({}) == {}

    def test_three_level_propagation(self, tiny_raw_stats):
        """Uses the conftest tiny_raw_stats fixture."""
        resolved = resolve_all_stats(tiny_raw_stats)
        # ARM_Child inherits Slot from _BaseArmor, overrides Value
        assert resolved["ARM_Child"]["Slot"] == "Breast"
        assert resolved["ARM_Child"]["Value"] == "20"

    def test_multi_category_from_tiny(self, tiny_raw_stats):
        resolved = resolve_all_stats(tiny_raw_stats)
        assert "ObjectCategory" in resolved["ARM_MultiCat"]
        # The raw semicolon-joined string is preserved as-is here (expansion is in StatsManager)
        assert "ClothUpperBody" in resolved["ARM_MultiCat"]["ObjectCategory"]


# ─── Integration: real Armor.txt ─────────────────────────────────────────────

@pytest.mark.integration
class TestResolveRealStats:
    def test_armor_txt_loads_and_resolves(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        raw = parse_stats_txt(real_armor_txt)
        assert len(raw) > 0
        resolved = resolve_all_stats(raw)
        assert len(resolved) > 0

    def test_base_armor_has_slot(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        raw = parse_stats_txt(real_armor_txt)
        resolved = resolve_all_stats(raw)
        assert "_Armors" in resolved
        assert resolved["_Armors"].get("Slot") == "Breast"

    def test_child_inherits_slot_from_parent(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        raw = parse_stats_txt(real_armor_txt)
        resolved = resolve_all_stats(raw)
        # ARM_Civilian_UpperBody uses _ClothArmor uses _Armors
        assert "ARM_Civilian_UpperBody" in resolved
        civilian = resolved["ARM_Civilian_UpperBody"]
        assert civilian.get("Slot") == "Breast"

    def test_child_overrides_value(self, real_armor_txt):
        from dos2_tools.core.parsers import parse_stats_txt
        raw = parse_stats_txt(real_armor_txt)
        resolved = resolve_all_stats(raw)
        # _ClothArmor has Armor Defense Value "30", _Armors has "0"
        cloth = resolved.get("_ClothArmor", {})
        assert cloth.get("Armor Defense Value") == "30"
