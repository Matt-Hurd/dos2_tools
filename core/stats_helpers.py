"""
Shared helpers for building typed stat tables from game data.

Used by generate_armour_module, generate_weapon_module,
generate_potion_module, generate_item_data_module, and
generate_skill_data_module to avoid repeating the same
"filter → OrderedDict → convert_type → resolve Boosts" pattern.
"""

from collections import OrderedDict

from dos2_tools.core.formatters import convert_type


def build_typed_stat_dict(stats_subset):
    """
    Convert a flat stats subset to a typed OrderedDict mapping.

    For each entry, builds an ``OrderedDict`` from the raw stats dict,
    applying ``convert_type()`` to every value and skipping internal
    underscore-prefixed keys (except ``_type`` which is kept for
    downstream filtering).

    Args:
        stats_subset: Dict of ``entry_id -> stats_dict`` already filtered
                      to the desired stat types.

    Returns:
        Dict of ``entry_id -> OrderedDict`` with converted values.
    """
    typed_data = {}
    for entry_id, data in stats_subset.items():
        typed_entry = OrderedDict()
        for key, value in data.items():
            if key.startswith("_") and key != "_type":
                continue
            typed_entry[key] = convert_type(value)
        typed_data[entry_id] = typed_entry
    return typed_data


def resolve_boosts_inline(typed_data):
    """
    Resolve Boosts string references to their stat-entry dicts in place.

    Many armour, weapon, and item stat entries carry a semicolon-separated
    ``Boosts`` field that lists the IDs of other stat entries (boost
    modifiers).  This helper replaces that string with a list of the
    actual resolved stat dicts, so callers can embed them inline when
    generating Lua output.

    Entries whose ``Boosts`` key is already not a string, or whose
    referenced keys are not present in ``typed_data``, are silently
    skipped.

    Args:
        typed_data: Mutable dict produced by ``build_typed_stat_dict``.
                    Modified in place; nothing is returned.
    """
    for data in typed_data.values():
        if "Boosts" not in data or not isinstance(data["Boosts"], str):
            continue
        boost_keys = [k.strip() for k in data["Boosts"].split(";") if k.strip()]
        data["Boosts"] = [typed_data[bk] for bk in boost_keys if bk in typed_data]
