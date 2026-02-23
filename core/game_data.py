"""
Central game data loader for DOS2.

Replaces the boilerplate that was repeated in every script's main() function.
Provides lazy-loaded access to all game data through a single GameData instance.

Usage:
    game = GameData()
    # Access stats, templates, localization, loot engine, etc.
    item_stats = game.stats.get("ARM_UNIQUE_BlazingJustice")
    name = game.localization.get_text(some_handle)
    tree = game.loot_engine.build_loot_tree("ST_SomeTable")
"""

from dos2_tools.core.config import get_config, FILE_PATTERNS
from dos2_tools.core.file_system import (
    resolve_load_order,
    get_files_by_pattern,
    get_all_resolved_paths,
    get_file_history,
)
from dos2_tools.core.parsers import (
    parse_stats_txt,
    parse_lsj,
    parse_lsj_templates,
    parse_item_combos,
    parse_item_combo_properties,
    parse_object_category_previews,
    parse_item_progression_names,
    parse_item_progression_visuals,
    parse_treasure_table,
)
from dos2_tools.core.stats_engine import resolve_all_stats
from dos2_tools.core.localization import load_localization
from dos2_tools.core.loot import StatsManager, TreasureParser
from dos2_tools.core.data_models import FileEntry, LSJNode


class GameData:
    """
    Central loader for all DOS2 game data.

    Load once, query many times. Data is lazy-loaded on first access
    and cached for subsequent queries.

    Args:
        refresh_loc: Force rebuild of localization cache
        cache_file_index: Path to file index cache (None to disable)
    """

    def __init__(self, refresh_loc=False, cache_file_index="cache_file_index.json"):
        self.config = get_config()
        self._refresh_loc = refresh_loc
        self._cache_file_index = cache_file_index

        # Lazy-loaded data stores
        self._file_index = None
        self._stats = None
        self._templates_by_stats = None
        self._templates_by_mapkey = None
        self._localization = None
        self._loot_engine = None
        self._item_combos = None
        self._combo_properties = None
        self._combo_previews = None
        self._item_prog_names = None
        self._item_prog_visuals = None
        self._item_prog_keys = None

    # ─── File Index ─────────────────────────────────────────────────────

    @property
    def file_index(self):
        """Version-aware file index (lazy-loaded)."""
        if self._file_index is None:
            print("Resolving load order...")
            self._file_index = resolve_load_order(
                self.config["base_path"],
                cache_file=self._cache_file_index,
            )
            print(f"  Indexed {len(self._file_index)} files.")
        return self._file_index

    def get_file_version_info(self, relative_path):
        """Get version provenance for a specific file."""
        return self.file_index.get(relative_path)

    def get_file_history(self, relative_path):
        """Get the ordered list of versions that include a specific file."""
        return get_file_history(self.file_index, relative_path)

    def get_files(self, pattern_key):
        """
        Get FileEntry objects matching a named pattern from config.

        Args:
            pattern_key: Key into FILE_PATTERNS (e.g. "stats", "armors")

        Returns:
            list[FileEntry]: Matching file entries
        """
        patterns = FILE_PATTERNS.get(pattern_key, [])
        return get_files_by_pattern(self.file_index, patterns)

    def get_file_paths(self, pattern_key):
        """
        Get resolved file paths matching a named pattern.

        Convenience wrapper that returns just the paths (not FileEntry objects).
        """
        entries = self.get_files(pattern_key)
        return [e.resolved_path for e in entries]

    # ─── Stats ──────────────────────────────────────────────────────────

    @property
    def stats(self):
        """All resolved stats entries with inheritance applied (lazy-loaded)."""
        if self._stats is None:
            self._load_stats()
        return self._stats

    def _load_stats(self):
        print("Parsing stats files...")
        stats_files = self.get_file_paths("stats")
        raw_stats = {}
        for f in stats_files:
            raw_stats.update(parse_stats_txt(f))
        print(f"  Resolving inheritance for {len(raw_stats)} entries...")
        self._stats = resolve_all_stats(raw_stats)
        print(f"  Resolved {len(self._stats)} stats entries.")

    # ─── Templates ──────────────────────────────────────────────────────

    @property
    def templates_by_stats(self):
        """Root templates indexed by Stats ID (lazy-loaded)."""
        if self._templates_by_stats is None:
            self._load_templates()
        return self._templates_by_stats

    @property
    def templates_by_mapkey(self):
        """Root templates indexed by MapKey/UUID (lazy-loaded)."""
        if self._templates_by_mapkey is None:
            self._load_templates()
        return self._templates_by_mapkey

    def _load_templates(self):
        print("Loading root templates...")
        merged_files = self.get_file_paths("merged_lsj")
        merged_files.extend(self.get_file_paths("root_templates_lsj"))

        self._templates_by_stats = {}
        self._templates_by_mapkey = {}

        for f in merged_files:
            by_stats, by_mapkey = parse_lsj_templates(f)
            self._templates_by_stats.update(by_stats)
            self._templates_by_mapkey.update(by_mapkey)

        print(f"  Loaded {len(self._templates_by_stats)} templates by stats, "
              f"{len(self._templates_by_mapkey)} by mapkey.")

    # ─── Localization ───────────────────────────────────────────────────

    @property
    def localization(self):
        """Localization resolver (lazy-loaded)."""
        if self._localization is None:
            print("Loading localization...")
            self._localization = load_localization(
                self.file_index, self.config, force_refresh=self._refresh_loc
            )
        return self._localization

    # ─── Loot Engine ────────────────────────────────────────────────────

    @property
    def loot_engine(self):
        """Treasure table parser with loaded data (lazy-loaded)."""
        if self._loot_engine is None:
            self._load_loot_engine()
        return self._loot_engine

    @property
    def stats_manager(self):
        """StatsManager instance (lazy-loaded, shares stats with loot_engine)."""
        # Ensure loot engine is loaded (which creates the stats manager)
        _ = self.loot_engine
        return self._stats_manager

    def _load_loot_engine(self):
        print("Loading treasure tables...")
        self._stats_manager = StatsManager(self.stats)
        self._loot_engine = TreasureParser(self._stats_manager)

        tt_files = self.get_file_paths("treasure_tables")
        for f in tt_files:
            data = parse_treasure_table(f)
            if data:
                self._loot_engine.load_data(data)

        print(f"  Loaded {len(self._loot_engine.tables)} treasure tables.")

    # ─── Crafting (Item Combos) ─────────────────────────────────────────

    @property
    def item_combos(self):
        """All item combo (crafting) recipes (lazy-loaded)."""
        if self._item_combos is None:
            self._load_item_combos()
        return self._item_combos

    @property
    def combo_properties(self):
        """Item combo properties (lazy-loaded)."""
        if self._combo_properties is None:
            self._load_item_combos()
        return self._combo_properties

    @property
    def combo_previews(self):
        """Object category combo preview data (lazy-loaded)."""
        if self._combo_previews is None:
            self._load_item_combos()
        return self._combo_previews

    def _load_item_combos(self):
        print("Loading crafting recipes...")
        self._item_combos = {}
        combo_files = self.get_file_paths("item_combos")
        for f in combo_files:
            self._item_combos.update(parse_item_combos(f))

        self._combo_properties = {}
        prop_files = self.get_file_paths("item_combo_properties")
        for f in prop_files:
            self._combo_properties.update(parse_item_combo_properties(f))

        self._combo_previews = {}
        preview_files = self.get_file_paths("object_categories_item_combos")
        for f in preview_files:
            self._combo_previews.update(parse_object_category_previews(f))

        print(f"  Loaded {len(self._item_combos)} combos, "
              f"{len(self._combo_properties)} properties.")

    # ─── Item Progression ───────────────────────────────────────────────

    @property
    def item_prog_names(self):
        """Item progression name groups (lazy-loaded)."""
        if self._item_prog_names is None:
            self._load_item_progression()
        return self._item_prog_names

    @property
    def item_prog_visuals(self):
        """Item progression visual groups (lazy-loaded)."""
        if self._item_prog_visuals is None:
            self._load_item_progression()
        return self._item_prog_visuals

    @property
    def item_prog_keys(self):
        """Item progression LSJ keys (lazy-loaded)."""
        if self._item_prog_keys is None:
            self._load_item_progression()
        return self._item_prog_keys

    def _load_item_progression(self):
        print("Loading item progression data...")
        self._item_prog_names = {}
        for f in self.get_file_paths("item_prog_names"):
            self._item_prog_names.update(parse_item_progression_names(f))

        self._item_prog_visuals = {}
        for f in self.get_file_paths("item_prog_visuals"):
            self._item_prog_visuals.update(parse_item_progression_visuals(f))

        self._item_prog_keys = []
        for f in self.get_file_paths("item_prog_lsj"):
            data = parse_lsj(f)
            if data:
                root = LSJNode(data)
                keys_node = (
                    root.get_node("save")
                    .get_node("regions")
                    .get_node("TranslatedStringKeys")
                )
                for key in keys_node.get_list("TranslatedStringKey"):
                    self._item_prog_keys.append(key.raw)

        print(f"  Loaded {len(self._item_prog_names)} name groups, "
              f"{len(self._item_prog_visuals)} visual groups, "
              f"{len(self._item_prog_keys)} progression keys.")

    # ─── Convenience Methods ────────────────────────────────────────────

    def resolve_display_name(self, stats_id=None, template_data=None):
        """
        Resolve the display name for an item using the multi-pattern approach.

        Tries in order:
          1. Template DisplayName handle
          2. Item progression name group
          3. Item progression LSJ ExtraData
          4. Stats ID as-is (fallback)
        """
        loc = self.localization

        # Pattern 1: Template DisplayName
        if template_data:
            td = LSJNode(template_data)
            handle = td.get_handle("DisplayName")
            if handle:
                text = loc.get_handle_text(handle)
                if text:
                    return text

        # Pattern 2: Item progression name group
        if stats_id:
            stat_entry = self.stats.get(stats_id, {})
            item_group = stat_entry.get("ItemGroup")

            if item_group and item_group in self.item_prog_names:
                raw_name = self.item_prog_names[item_group].get("name")
                if raw_name:
                    for key_raw in self.item_prog_keys:
                        key = LSJNode(key_raw)
                        if key.get_value("UUID") == raw_name:
                            handle = key.get_handle("Content")
                            text = loc.get_handle_text(handle)
                            if text:
                                return text

            # Pattern 3: LSJ ExtraData
            for key_raw in self.item_prog_keys:
                key = LSJNode(key_raw)
                if key.get_value("ExtraData") == stats_id:
                    handle = key.get_handle("Content")
                    text = loc.get_handle_text(handle)
                    if text:
                        return text

        # Fallback: try localization by stats_id
        if stats_id:
            text = loc.get_text(stats_id)
            if text:
                return text

        return None
