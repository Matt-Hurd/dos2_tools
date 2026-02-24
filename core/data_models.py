"""
Data models for DOS2 game entities.

Provides three core building blocks used throughout the toolchain:
  - LSJNode:    accessor wrapper for raw LSJ (JSON) game data dicts
  - GameObject: structured, typed representation of a parsed game object
  - FileEntry:  file with version provenance tracking
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


class LSJNode:
    """
    Wrapper for raw LSJ (JSON) game data nodes.

    Handles the inconsistent patterns in DOS2's LSJ format:
      - Values as plain strings OR {"value": "x"} dicts
      - Localization handles as {"handle": "h...", "version": 1}
      - Single items where a list is expected
      - Deeply nested node hierarchies

    Usage:
        node = LSJNode(raw_dict)
        stats_id = node.get_value("Stats")           # unwraps {"value": "x"}
        handle = node.get_handle("DisplayName")       # extracts handle
        tags = node.get_list("Tags")                  # normalizes to list
        child = node.get_node("Tag").get_value("MapKey")  # chained access
    """

    __slots__ = ("_raw",)

    def __init__(self, raw=None):
        if isinstance(raw, LSJNode):
            self._raw = raw._raw
        elif isinstance(raw, dict):
            self._raw = raw
        else:
            self._raw = {}

    # ─── Core Accessors ─────────────────────────────────────────────────

    def get_value(self, key, default=None):
        """
        Get a scalar value, automatically unwrapping {"value": x} dicts.

        Handles:
          - "Stats": "WPN_Foo"           → "WPN_Foo"
          - "Stats": {"value": "WPN_Foo"} → "WPN_Foo"
          - Missing key                   → default
        """
        val = self._raw.get(key)
        if val is None:
            return default
        if isinstance(val, dict):
            return val.get("value", default)
        return val

    def get_handle(self, key):
        """
        Get a localization handle from a {"handle": "h..."} node.

        Returns None if the key is missing or not a handle node.
        """
        val = self._raw.get(key)
        if isinstance(val, dict):
            return val.get("handle")
        return None

    def get_list(self, key):
        """
        Get a list of child LSJNodes, normalizing single items.

        Handles:
          - Missing key    → []
          - [item1, item2] → [LSJNode(item1), LSJNode(item2)]
          - single_item    → [LSJNode(single_item)]
        """
        val = self._raw.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return [LSJNode(x) if not isinstance(x, LSJNode) else x for x in val]
        return [LSJNode(val)]

    def get_node(self, key):
        """
        Get a child node as an LSJNode.

        Always returns an LSJNode (empty if the key is missing),
        so chained access like node.get_node("A").get_node("B").get_value("C")
        never raises.
        """
        val = self._raw.get(key)
        if isinstance(val, dict):
            return LSJNode(val)
        return LSJNode()

    def get_raw(self, key, default=None):
        """Get a raw value without any unwrapping (escape hatch)."""
        return self._raw.get(key, default)

    # ─── Convenience ────────────────────────────────────────────────────

    def has(self, key):
        """Check if a key exists and is not None."""
        return self._raw.get(key) is not None

    def keys(self):
        """Return the keys of the underlying dict."""
        return self._raw.keys()

    @property
    def raw(self):
        """Direct access to the underlying dict."""
        return self._raw

    def __bool__(self):
        """Truthy if the underlying dict is non-empty."""
        return bool(self._raw)

    def __repr__(self):
        all_keys = list(self._raw.keys())
        keys = all_keys[:5]
        suffix = "..." if len(all_keys) > 5 else ""
        return f"LSJNode({keys}{suffix})"

    # ─── Deep Search ────────────────────────────────────────────────────

    def deep_find_value(self, target_key):
        """
        Recursively search for a key and return its unwrapped value.

        Useful for finding things like SkillID buried deep in
        nested action/attribute trees.
        """
        return _deep_find(self._raw, target_key)


def _deep_find(data, target_key):
    """Recursively search for a key in nested dicts/lists."""
    if isinstance(data, dict):
        if target_key in data:
            val = data[target_key]
            if isinstance(val, dict):
                return val.get("value", val)
            return val

        # Also check the "id" attribute pattern
        if data.get("id") == target_key and "value" in data:
            return data["value"]

        for v in data.values():
            found = _deep_find(v, target_key)
            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = _deep_find(item, target_key)
            if found is not None:
                return found

    return None


# ─── LSJ key → GameObject attribute name ─────────────────────────────────────

_LSJ_KEY_TO_ATTR: dict[str, str] = {
    "MapKey":             "map_key",
    "Stats":              "stats_id",
    "TemplateName":       "template_name",
    "Icon":               "icon",
    "Name":               "name",
    "DisplayName":        "display_name",
    "Description":        "description",
    "Type":               "type",
    "DefaultState":       "default_state",
    "SkillID":            "skill_id",
    "LevelOverride":      "level_override",
    "TradeTreasures":     "trade_treasures",
    "Treasures":          "treasures",
    "SkillList":          "skill_list",
    "Transform":          "transform",
    "Tags":               "tags",
    "ItemList":           "item_list",
    "OnUsePeaceActions":  "on_use_peace_actions",
    "InventoryList":      "inventory_list",
}


@dataclass
class GameObject:
    """
    Structured representation of a parsed DOS2 game object (item or character).

    Produced by parsers._extract_game_object() — the clean side of the boundary
    between the raw LSJ world and the rest of the toolchain.

    Display-name / description fields keep their raw {"handle": ...} dicts so
    callers can resolve localization handles without re-parsing.
    The passthrough raw fields (tags, skill_list, etc.) stay untyped because
    they are consumed via LSJNode by specialised helpers downstream.
    """

    # ─── Identity ────────────────────────────────────────────────────
    map_key: str | None = None             # UUID of this instance
    stats_id: str | None = None            # Stats entry ID (e.g. "ARM_Unique_Foo")
    template_name: str | None = None       # Parent template UUID (TemplateName)

    # ─── Presentation ────────────────────────────────────────────────
    icon: str | None = None
    name: str | None = None                # Name field (internal identifier)
    display_name: dict | None = None       # raw {"handle": "h..."} or {"value": "x"}
    description: dict | None = None        # same

    # ─── Classification ──────────────────────────────────────────────
    type: str | None = None                # "item", "character", etc.
    default_state: Any = None
    skill_id: str | None = None            # extracted from OnUsePeaceActions

    # ─── Level / gameplay ────────────────────────────────────────────
    level_override: dict | None = None     # raw {"value": N} dict
    trade_treasures: list[str] = field(default_factory=list)
    treasures: list[str] = field(default_factory=list)

    # ─── Raw passthrough (consumed by LSJNode-based helpers) ─────────
    skill_list: Any = None
    transform: Any = None
    tags: Any = None
    item_list: Any = None
    on_use_peace_actions: Any = None
    inventory_list: Any = None

    # ─── Helpers ─────────────────────────────────────────────────────

    def get_handle(self, lsj_key: str) -> str | None:
        """
        Extract a localization handle from a raw display-name/description field.

        Args:
            lsj_key: The original LSJ field name (e.g. "DisplayName").

        Returns:
            The handle string (e.g. "h_abc123"), or None.
        """
        attr = _LSJ_KEY_TO_ATTR.get(lsj_key, lsj_key.lower())
        val = getattr(self, attr, None)
        if isinstance(val, dict):
            return val.get("handle")
        return None

    def as_lsj_node(self) -> "LSJNode":
        """
        Return this object as an LSJNode view.

        Escape hatch for callers that still need LSJNode-style access on all
        fields (e.g. deep nested helpers). Reconstructs the raw dict.
        """
        return LSJNode(self._to_raw_dict())

    def _to_raw_dict(self) -> dict:
        """Reconstruct a dict compatible with _extract_game_object output."""
        raw: dict[str, Any] = {}
        for lsj_key, attr in _LSJ_KEY_TO_ATTR.items():
            val = getattr(self, attr)
            if val is not None:
                raw[lsj_key] = val
        # TradeTreasures / Treasures: stored as lists, not LSJNode-wrapped
        if self.trade_treasures:
            raw["TradeTreasures"] = self.trade_treasures
        if self.treasures:
            raw["Treasures"] = self.treasures
        return raw


@dataclass
class FileEntry:
    """
    A file in the game data with version provenance tracking.

    Tracks which load order entry introduced this file and which
    entries modified it, enabling version history queries.
    """
    resolved_path: str
    relative_path: str
    introduced_by: str          # First load order entry containing this file
    modified_by: list[str] = field(default_factory=list)  # All load order entries with this file

    @property
    def last_modified_by(self) -> str:
        """The most recent load order entry that touched this file."""
        return self.modified_by[-1] if self.modified_by else self.introduced_by

    @property
    def was_overridden(self) -> bool:
        """Whether this file was modified after its initial introduction."""
        return len(self.modified_by) > 1
