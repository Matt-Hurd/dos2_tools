"""
Tests for core/file_system.py — load order resolution and pattern matching.

Unit tests use tmp_path for small fake directory trees.
Integration tests use the real exported/ directory via the cache.
"""

import os
import pytest
from dos2_tools.core.file_system import (
    _glob_to_regex,
    get_files_by_pattern,
    get_file_history,
    get_load_priority,
    resolve_load_order,
)
from dos2_tools.core.data_models import FileEntry


# ─── _glob_to_regex ──────────────────────────────────────────────────────────

class TestGlobToRegex:
    def test_double_star_matches_subdirectory(self):
        rx = _glob_to_regex("**/*.txt")
        assert rx.search("a/b/c/foo.txt")

    def test_double_star_matches_single_level_path(self):
        # The implementation generates .*/[^/]*\.txt$ — requires at least one /.
        # A bare "foo.txt" does NOT match; use a one-level path instead.
        rx = _glob_to_regex("**/*.txt")
        assert rx.search("subdir/foo.txt")

    def test_single_star_does_not_cross_separator(self):
        rx = _glob_to_regex("Stats/*.txt")
        assert rx.search("Stats/Armor.txt")
        assert not rx.search("Stats/Data/Armor.txt")

    def test_literal_dot_not_wildcard(self):
        rx = _glob_to_regex("foo.txt")
        assert rx.search("foo.txt")
        assert not rx.search("fooXtxt")  # dot must be literal

    def test_case_insensitive(self):
        rx = _glob_to_regex("*.TXT")
        assert rx.search("armor.txt")

    def test_specific_pattern(self):
        rx = _glob_to_regex("Public/**/Stats/Generated/Data/*.txt")
        assert rx.search("Public/Shared/Stats/Generated/Data/Armor.txt")
        assert not rx.search("Public/Shared/Stats/Armor.txt")


# ─── get_files_by_pattern ────────────────────────────────────────────────────

class TestGetFilesByPattern:
    def _make_index(self, paths):
        """Build a minimal file_index dict from a list of relative paths."""
        index = {}
        for p in paths:
            index[p] = FileEntry(
                resolved_path=f"/root/{p}",
                relative_path=p,
                introduced_by="Shared",
                modified_by=["Shared"],
            )
        return index

    def test_basic_glob_match(self):
        index = self._make_index([
            "Public/Shared/Stats/Generated/Data/Armor.txt",
            "Public/Shared/Stats/Generated/Data/Weapon.txt",
            "SomeOther/File.json",
        ])
        results = get_files_by_pattern(index, ["**/*.txt"])
        paths = [e.relative_path for e in results]
        assert "Public/Shared/Stats/Generated/Data/Armor.txt" in paths
        assert "Public/Shared/Stats/Generated/Data/Weapon.txt" in paths
        assert "SomeOther/File.json" not in paths

    def test_multiple_patterns_unioned(self):
        index = self._make_index([
            "Stats/Armor.txt",
            "Stats/Weapon.txt",
            "Other.json",
        ])
        results = get_files_by_pattern(index, ["Stats/Armor.txt", "Stats/Weapon.txt"])
        paths = [e.relative_path for e in results]
        assert "Stats/Armor.txt" in paths
        assert "Stats/Weapon.txt" in paths

    def test_no_match_returns_empty(self):
        index = self._make_index(["Public/Foo.lsj"])
        results = get_files_by_pattern(index, ["**/*.txt"])
        assert results == []

    def test_string_pattern_accepted(self):
        index = self._make_index(["Foo/Bar.txt"])
        results = get_files_by_pattern(index, "**/*.txt")
        assert len(results) == 1

    def test_no_duplicate_entries(self):
        """A file matching multiple patterns should appear only once."""
        index = self._make_index(["Stats/Armor.txt"])
        results = get_files_by_pattern(index, ["**/*.txt", "Stats/*.txt"])
        assert len(results) == 1


# ─── get_file_history ────────────────────────────────────────────────────────

class TestGetFileHistory:
    def test_returns_modified_by_list(self):
        index = {
            "foo.txt": FileEntry(
                resolved_path="/x/foo.txt",
                relative_path="foo.txt",
                introduced_by="Shared",
                modified_by=["Shared", "Patch1", "Patch5"],
            )
        }
        history = get_file_history(index, "foo.txt")
        assert history == ["Shared", "Patch1", "Patch5"]

    def test_missing_file_returns_empty(self):
        assert get_file_history({}, "not_here.txt") == []

    def test_returns_copy_not_reference(self):
        index = {
            "foo.txt": FileEntry("/x", "foo.txt", "Shared", ["Shared"])
        }
        history = get_file_history(index, "foo.txt")
        history.append("Mutation")
        assert len(index["foo.txt"].modified_by) == 1


# ─── get_load_priority ───────────────────────────────────────────────────────

class TestGetLoadPriority:
    def test_shared_before_patch(self):
        assert get_load_priority("/path/Shared/foo.txt") < get_load_priority("/path/Patch10/foo.txt")

    def test_patch1_before_patch10(self):
        assert get_load_priority("Patch1/x") < get_load_priority("Patch10/x")

    def test_unknown_layer_gets_max_priority(self):
        from dos2_tools.core.config import LOAD_ORDER
        p = get_load_priority("/path/Unknown/foo.txt")
        assert p == len(LOAD_ORDER)


# ─── resolve_load_order (unit, fake tree) ────────────────────────────────────

class TestResolveLoadOrder:
    def test_builds_index_from_fake_dirs(self, tmp_path, monkeypatch):
        """
        Create two minimal load order layers (Shared, Patch1) with one
        overlapping file and verify the index is built correctly.
        """
        from dos2_tools.core import file_system as fs_module

        # Patch LOAD_ORDER to only include our two test layers
        monkeypatch.setattr(fs_module, "LOAD_ORDER", ["Shared", "Patch1"])

        # Create fake exported/ directory
        exported = tmp_path / "exported"
        (exported / "Shared").mkdir(parents=True)
        (exported / "Patch1").mkdir(parents=True)

        # Shared has foo.txt and bar.txt
        (exported / "Shared" / "foo.txt").write_text("shared foo")
        (exported / "Shared" / "bar.txt").write_text("shared bar")
        # Patch1 overrides foo.txt
        (exported / "Patch1" / "foo.txt").write_text("patch1 foo")

        index = resolve_load_order(str(exported))

        assert "foo.txt" in index
        assert "bar.txt" in index

        # foo.txt should resolve to the Patch1 version
        foo = index["foo.txt"]
        assert foo.introduced_by == "Shared"
        assert foo.was_overridden
        assert str(exported / "Patch1" / "foo.txt") == foo.resolved_path

        # bar.txt should only have Shared
        bar = index["bar.txt"]
        assert bar.introduced_by == "Shared"
        assert not bar.was_overridden

    def test_cache_roundtrip(self, tmp_path, monkeypatch):
        from dos2_tools.core import file_system as fs_module
        monkeypatch.setattr(fs_module, "LOAD_ORDER", ["Shared"])

        exported = tmp_path / "exported"
        (exported / "Shared").mkdir(parents=True)
        (exported / "Shared" / "test.lsj").write_text("{}")

        cache = tmp_path / "cache.json"

        # First call: builds and saves cache
        index1 = resolve_load_order(str(exported), cache_file=str(cache))
        assert cache.exists()

        # Second call: loads from cache
        index2 = resolve_load_order(str(exported), cache_file=str(cache))
        assert "test.lsj" in index2
        assert index1["test.lsj"].resolved_path == index2["test.lsj"].resolved_path


# ─── Integration: real exported/ ─────────────────────────────────────────────

@pytest.mark.integration
class TestRealFileIndex:
    def test_index_has_many_files(self, real_file_index):
        assert len(real_file_index) > 10000

    def test_known_file_present(self, real_file_index):
        # Normalize to forward slashes; the key may vary by layer
        keys = set(real_file_index.keys())
        # Look for any key matching armor stats
        armor_keys = [k for k in keys if "Armor.txt" in k and "Stats" in k]
        assert len(armor_keys) > 0

    def test_treasure_table_files_found(self, real_file_index):
        from dos2_tools.core.config import FILE_PATTERNS
        entries = get_files_by_pattern(real_file_index, FILE_PATTERNS["treasure_tables"])
        assert len(entries) >= 1
        assert all(e.resolved_path.endswith("TreasureTable.txt") for e in entries)

    def test_armor_files_found(self, real_file_index):
        from dos2_tools.core.config import FILE_PATTERNS
        entries = get_files_by_pattern(real_file_index, FILE_PATTERNS["armors"])
        assert len(entries) >= 1

    def test_file_entry_resolved_path_exists(self, real_file_index):
        """Spot-check that a few resolved paths actually exist on disk."""
        checked = 0
        for entry in list(real_file_index.values())[:20]:
            assert os.path.exists(entry.resolved_path), \
                f"Resolved path missing: {entry.resolved_path}"
            checked += 1
        assert checked > 0

    def test_overridden_files_have_multiple_layers(self, real_file_index):
        overridden = [e for e in real_file_index.values() if e.was_overridden]
        assert len(overridden) > 0
