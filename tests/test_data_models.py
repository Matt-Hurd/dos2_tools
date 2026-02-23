"""
Tests for core/data_models.py — LSJNode and FileEntry.

All tests are pure unit tests (no disk I/O).
"""

import pytest
from dos2_tools.core.data_models import LSJNode, FileEntry


# ─── LSJNode.get_value ───────────────────────────────────────────────────────

class TestLSJNodeGetValue:
    def test_plain_string(self):
        node = LSJNode({"Stats": "ARM_Foo"})
        assert node.get_value("Stats") == "ARM_Foo"

    def test_value_wrapped_dict(self):
        node = LSJNode({"Stats": {"value": "ARM_Foo"}})
        assert node.get_value("Stats") == "ARM_Foo"

    def test_missing_key_returns_default(self):
        node = LSJNode({"Other": "x"})
        assert node.get_value("Stats") is None

    def test_missing_key_custom_default(self):
        node = LSJNode({})
        assert node.get_value("Stats", "fallback") == "fallback"

    def test_none_value_returns_default(self):
        # If value is explicitly None, treat as absent
        node = LSJNode({"Stats": None})
        assert node.get_value("Stats") is None

    def test_numeric_plain_value(self):
        node = LSJNode({"Level": 5})
        assert node.get_value("Level") == 5


# ─── LSJNode.get_handle ──────────────────────────────────────────────────────

class TestLSJNodeGetHandle:
    def test_handle_dict(self):
        node = LSJNode({"DisplayName": {"handle": "h_abc123", "version": 1}})
        assert node.get_handle("DisplayName") == "h_abc123"

    def test_not_a_dict(self):
        node = LSJNode({"DisplayName": "plain_string"})
        assert node.get_handle("DisplayName") is None

    def test_missing_key(self):
        node = LSJNode({})
        assert node.get_handle("DisplayName") is None

    def test_dict_without_handle_key(self):
        node = LSJNode({"DisplayName": {"value": "x"}})
        assert node.get_handle("DisplayName") is None


# ─── LSJNode.get_list ────────────────────────────────────────────────────────

class TestLSJNodeGetList:
    def test_missing_key_returns_empty(self):
        node = LSJNode({})
        assert node.get_list("Tags") == []

    def test_single_dict_is_wrapped(self):
        node = LSJNode({"Tags": {"MapKey": "abc"}})
        items = node.get_list("Tags")
        assert len(items) == 1
        assert isinstance(items[0], LSJNode)
        assert items[0].get_value("MapKey") == "abc"

    def test_list_of_dicts(self):
        node = LSJNode({"Tags": [{"id": "A"}, {"id": "B"}]})
        items = node.get_list("Tags")
        assert len(items) == 2
        assert items[0].get_value("id") == "A"
        assert items[1].get_value("id") == "B"

    def test_already_lsj_nodes_not_double_wrapped(self):
        inner = LSJNode({"id": "X"})
        node = LSJNode({"Tags": [inner]})
        items = node.get_list("Tags")
        assert len(items) == 1
        assert items[0].get_value("id") == "X"

    def test_none_value_returns_empty(self):
        node = LSJNode({"Tags": None})
        assert node.get_list("Tags") == []


# ─── LSJNode.get_node ────────────────────────────────────────────────────────

class TestLSJNodeGetNode:
    def test_nested_dict_wrapped(self):
        node = LSJNode({"save": {"regions": {"foo": "bar"}}})
        save = node.get_node("save")
        assert isinstance(save, LSJNode)
        assert save.get_node("regions").get_value("foo") == "bar"

    def test_missing_key_returns_empty_node(self):
        node = LSJNode({})
        child = node.get_node("missing")
        assert isinstance(child, LSJNode)
        assert not child  # falsy

    def test_chain_with_missing_link_is_safe(self):
        # Should not raise; each missing level returns empty LSJNode
        node = LSJNode({})
        val = node.get_node("a").get_node("b").get_node("c").get_value("d")
        assert val is None


# ─── LSJNode.get_raw ─────────────────────────────────────────────────────────

class TestLSJNodeGetRaw:
    def test_raw_returns_dict_as_is(self):
        inner = {"handle": "h123"}
        node = LSJNode({"DisplayName": inner})
        assert node.get_raw("DisplayName") == inner

    def test_missing_returns_default(self):
        node = LSJNode({})
        assert node.get_raw("X", []) == []


# ─── LSJNode.has ─────────────────────────────────────────────────────────────

class TestLSJNodeHas:
    def test_present_key(self):
        assert LSJNode({"x": "y"}).has("x")

    def test_absent_key(self):
        assert not LSJNode({}).has("x")

    def test_none_value_is_not_has(self):
        assert not LSJNode({"x": None}).has("x")


# ─── LSJNode.deep_find_value ─────────────────────────────────────────────────

class TestLSJNodeDeepFind:
    def test_direct_key(self):
        node = LSJNode({"SkillID": "Skill_Fireball"})
        assert node.deep_find_value("SkillID") == "Skill_Fireball"

    def test_nested_in_dict(self):
        node = LSJNode({"Actions": {"SkillID": {"value": "Skill_Chain"}}})
        assert node.deep_find_value("SkillID") == "Skill_Chain"

    def test_nested_in_list(self):
        node = LSJNode({"Actions": [{"SkillID": "Skill_A"}, {"Other": "x"}]})
        assert node.deep_find_value("SkillID") == "Skill_A"

    def test_id_attribute_pattern(self):
        # Matches the {id: "SkillID", value: "..."} pattern
        node = LSJNode({"attrs": {"id": "SkillID", "value": "Skill_B"}})
        assert node.deep_find_value("SkillID") == "Skill_B"

    def test_not_found_returns_none(self):
        node = LSJNode({"other": "stuff"})
        assert node.deep_find_value("SkillID") is None


# ─── LSJNode bool / repr ─────────────────────────────────────────────────────

class TestLSJNodeMisc:
    def test_empty_is_falsy(self):
        assert not LSJNode()
        assert not LSJNode({})

    def test_non_empty_is_truthy(self):
        assert LSJNode({"x": 1})

    def test_wrapping_lsj_node(self):
        original = LSJNode({"k": "v"})
        wrapped = LSJNode(original)
        assert wrapped.get_value("k") == "v"

    def test_repr_shows_keys(self):
        node = LSJNode({"a": 1, "b": 2})
        r = repr(node)
        assert "LSJNode" in r


# ─── FileEntry ───────────────────────────────────────────────────────────────

class TestFileEntry:
    def test_last_modified_by(self):
        fe = FileEntry(
            resolved_path="/x/Patch5/foo.txt",
            relative_path="foo.txt",
            introduced_by="Shared",
            modified_by=["Shared", "Patch2", "Patch5"],
        )
        assert fe.last_modified_by == "Patch5"

    def test_last_modified_by_empty(self):
        fe = FileEntry(
            resolved_path="/x/foo.txt",
            relative_path="foo.txt",
            introduced_by="Shared",
            modified_by=[],
        )
        assert fe.last_modified_by == "Shared"

    def test_was_overridden_true(self):
        fe = FileEntry("/x", "foo.txt", "Shared", ["Shared", "Patch1"])
        assert fe.was_overridden

    def test_was_overridden_false(self):
        fe = FileEntry("/x", "foo.txt", "Shared", ["Shared"])
        assert not fe.was_overridden
