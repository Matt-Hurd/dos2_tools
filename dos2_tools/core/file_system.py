import os
import re

def resolve_load_order(root_dir, load_order_dirs):
    """
    Resolves the list of files to load based on the provided load order directories.
    Prioritizes files in later directories over earlier ones (overrides).
    """
    resolved_map = {}

    # We iterate through the load order. Later entries overwrite earlier ones in the map.
    for layer_path in load_order_dirs:
        if not os.path.exists(layer_path):
            continue

        for dirpath, _, filenames in os.walk(layer_path):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                # We key by relative path to handle overrides (file masking)
                rel_path = os.path.relpath(abs_path, layer_path)

                # Normalize key to forward slashes to avoid OS differences affecting overrides
                key = rel_path.replace('\\', '/')
                resolved_map[key] = abs_path

    # Return the final list of absolute paths
    return list(resolved_map.values())

def get_files_by_pattern(file_list, patterns):
    """
    Filters a list of absolute file paths using glob-style patterns (e.g. **/*.txt).
    Converts glob patterns to Regex to handle recursion (**) and suffix matching correctly.
    """
    if isinstance(patterns, str):
        patterns = [patterns]

    regex_patterns = []
    for p in patterns:
        # Normalize slashes
        p = p.replace('\\', '/')

        # Escape Regex characters (like ., +, (, ), etc.)
        p = re.escape(p)

        # Unescape the ones we want to use as wildcards
        p = p.replace(r'\*\*', '.*') # ** -> .*
        p = p.replace(r'\*', r'[^/]*') # * -> [^/]*

        # Anchor to end of string ($) to allow matching relative patterns against absolute paths
        regex_patterns.append(re.compile(p + '$', re.IGNORECASE))

    matched = []
    for f in file_list:
        # Normalize file path slashes for consistent regex matching
        norm_path = f.replace('\\', '/')

        for regex in regex_patterns:
            if regex.search(norm_path):
                matched.append(f)
                break

    return matched
