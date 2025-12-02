import re

def sanitize_filename(name):
    if name.startswith("Template:"):
        name = name[9:]
        
    def hex_repl(match):
        return f'%{ord(match.group(0)):02X}'
        
    clean = re.sub(r'[\\/*?:"<>|]', hex_repl, name)
    return clean.strip()

def sanitize_lua_string(text):
    if not text: return ""
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    text = text.replace('\n', '<br>')
    return text

def _to_lua_value(value, indent_level):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{sanitize_lua_string(value)}"'
    if isinstance(value, dict):
        return to_lua_table(value, indent_level + 1)
    if isinstance(value, list):
        return _to_lua_list(value, indent_level + 1)
    if value is None:
        return "nil"
    return f'"{str(value)}"'

def _to_lua_list(data, indent_level):
    base_indent = '\t' * indent_level
    entry_indent = '\t' * (indent_level + 1)
    parts = []
    for item in data:
        lua_val = _to_lua_value(item, indent_level)
        parts.append(f'{entry_indent}{lua_val},')
    if not parts: return "{}"
    return "{\n" + "\n".join(parts) + "\n" + base_indent + "}"

def to_lua_table(data, indent_level=0):
    base_indent = '\t' * indent_level
    entry_indent = '\t' * (indent_level + 1)
    parts = []
    
    for key, value in data.items():
        lua_key = f'["{key}"]' if not re.match(r'^[a-zA-Z_]\w*$', str(key)) else str(key)
        lua_value = _to_lua_value(value, indent_level)
        parts.append(f'{entry_indent}{lua_key} = {lua_value},')
    
    if not parts: return "{}"
    return "{\n" + "\n".join(parts) + "\n" + base_indent + "}"

def to_wikitext_infobox(template_name, params):
    lines = [f"{{{{{template_name}"]
    for key, value in sorted(params.items()):
        if value is not None and str(value) != "":
            lines.append(f"|{key} = {value}")
    lines.append("}}")
    return "\n".join(lines)