"""
Stats inheritance resolver for DOS2 game data.

Resolves the "using" inheritance chains in stats entries,
where one entry can inherit and override data from a parent entry.
"""

from collections import OrderedDict


def resolve_entry(entry_id, all_entries, resolved_cache, inheritance_chain=None):
    """
    Resolve a single stats entry, following its inheritance chain.

    Args:
        entry_id: The entry to resolve
        all_entries: All raw (unresolved) stats entries
        resolved_cache: Cache of already-resolved entries (mutated in place)
        inheritance_chain: Set of entry_ids seen in the current chain (cycle detection)

    Returns:
        OrderedDict of resolved key-value data, or None if entry not found.
    """
    if entry_id in resolved_cache:
        return resolved_cache[entry_id]

    if entry_id not in all_entries:
        return None

    if inheritance_chain is None:
        inheritance_chain = set()
    if entry_id in inheritance_chain:
        return None  # Circular inheritance
    inheritance_chain.add(entry_id)

    entry = all_entries[entry_id]
    final_data = OrderedDict()

    # Resolve parent first
    parent_id = entry.get("_using")
    if parent_id:
        parent_data = resolve_entry(
            parent_id, all_entries, resolved_cache, inheritance_chain.copy()
        )
        if parent_data:
            final_data.update(parent_data)

    # Apply own data on top
    final_data.update(entry["_data"])
    if "_type" in entry:
        final_data["_type"] = entry["_type"]

    resolved_cache[entry_id] = final_data
    return final_data


def resolve_all_stats(raw_stats):
    """
    Resolve inheritance for all stats entries.

    Args:
        raw_stats: Dict of entry_id -> raw entry data (from parse_stats_txt)

    Returns:
        Dict of entry_id -> resolved OrderedDict with all inherited fields applied.
    """
    resolved = {}
    cache = {}
    for key in raw_stats:
        data = resolve_entry(key, raw_stats, cache)
        if data:
            resolved[key] = data
    return resolved
