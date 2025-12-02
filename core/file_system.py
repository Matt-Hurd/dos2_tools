import os
import re
from dos2_tools.core.config import LOAD_ORDER

def resolve_load_order(root_dir, cache_file=None):
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    resolved_map = {}
    for layer in LOAD_ORDER:
        layer_path = os.path.join(root_dir, layer)
        if not os.path.exists(layer_path):
            continue
        
        for dirpath, _, filenames in os.walk(layer_path):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                # We key by relative path to handle overrides (file masking)
                rel_path = os.path.relpath(abs_path, layer_path)
                resolved_map[rel_path] = abs_path

    final_files = list(resolved_map.values())
    
    if cache_file:
        with open(cache_file, 'w', encoding='utf-8') as f:
            for path in final_files:
                f.write(f"{path}\n")
            
    return final_files

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
        # We manually handle * and ? later, so we temporarily placeholder them
        # or just be careful with replacement order.
        
        # 1. Escape dot
        p = p.replace('.', r'\.')
        
        # 2. Convert glob ** to Regex .* (match anything including slashes)
        p = p.replace('**', '.*')
        
        # 3. Convert glob * to Regex [^/]* (match anything EXCEPT slashes)
        # Note: We must ensure we don't accidentally replace the .* we just made.
        # But since we replaced ** first, any remaining * are single stars.
        p = p.replace('*', r'[^/]*')
        
        # 4. Anchor to end of string ($) to allow matching relative patterns against absolute paths
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

def get_load_priority(filepath):
    parts = filepath.split(os.sep)
    for index, folder in enumerate(LOAD_ORDER):
        if folder in parts:
            return index
    return len(LOAD_ORDER)