from collections import OrderedDict
from copy import deepcopy

def resolve_entry(entry_id, all_entries, resolved_cache, inheritance_chain=None):
    if entry_id in resolved_cache:
        return resolved_cache[entry_id]
        
    if entry_id not in all_entries:
        return None

    if inheritance_chain is None:
        inheritance_chain = set()
    if entry_id in inheritance_chain:
        return None
    inheritance_chain.add(entry_id)

    entry = all_entries[entry_id]
    final_data = OrderedDict()
    
    parent_id = entry.get("_using")
    if parent_id:
        parent_data = resolve_entry(parent_id, all_entries, resolved_cache, inheritance_chain.copy())
        if parent_data:
            final_data.update(parent_data)
            
    final_data.update(entry["_data"])
    if "_type" in entry:
        final_data["_type"] = entry["_type"]
    
    resolved_cache[entry_id] = final_data
    return final_data

def resolve_all_stats(raw_stats):
    resolved = {}
    cache = {}
    for key in raw_stats:
        data = resolve_entry(key, raw_stats, cache)
        if data:
            resolved[key] = data
    return resolved