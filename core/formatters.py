"""
Output formatters for DOS2 data.

Handles conversion to:
  - Lua table syntax (for MediaWiki Scribunto modules)
  - Wikitext markup (infoboxes, template calls)
  - Filename sanitization for wiki uploads
  - Type conversion (string -> int/float/bool)
"""

import re


# ─── Filename Sanitization ──────────────────────────────────────────────────

def sanitize_filename(name):
    """
    Sanitize a string for use as a wiki page filename.

    Strips "Template:" prefix and URL-encodes characters that are
    invalid in MediaWiki page titles.
    """
    if name.startswith("Template:"):
        name = name[9:]

    def hex_repl(match):
        return f"%{ord(match.group(0)):02X}"

    clean = re.sub(r'[\\/*?:"<>|]', hex_repl, name)
    return clean.strip()


# ─── Type Conversion ────────────────────────────────────────────────────────

def convert_type(value):
    """
    Convert a string value to its appropriate Python type.

    Handles integers (including negative), booleans, floats,
    and quoted strings. Used when building typed Lua modules.
    """
    if not isinstance(value, str):
        return value

    # Integer (including negative)
    if re.match(r"^-?\d+$", value):
        return int(value)

    # Boolean
    val_lower = value.lower()
    if val_lower in ("true", "yes"):
        return True
    if val_lower in ("false", "no"):
        return False

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # Strip surrounding quotes if present
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return value[1:-1].replace('\\"', '"')

    return value.replace('"', '\\"')


# ─── Lua Serialization ─────────────────────────────────────────────────────

def sanitize_lua_string(text):
    """Escape a string for embedding in a Lua string literal."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "<br>")
    return text


def to_lua_value(value, indent_level=0):
    """Convert a Python value to its Lua representation."""
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
    """Convert a Python list to a Lua array literal."""
    base_indent = "\t" * indent_level
    entry_indent = "\t" * (indent_level + 1)
    parts = []
    for item in data:
        lua_val = to_lua_value(item, indent_level)
        parts.append(f"{entry_indent}{lua_val},")
    if not parts:
        return "{}"
    return "{\n" + "\n".join(parts) + "\n" + base_indent + "}"


def to_lua_table(data, indent_level=0, skip_internal_keys=False):
    """
    Convert a Python dict to a Lua table literal.

    Args:
        data: Dict to convert
        indent_level: Current indentation depth
        skip_internal_keys: If True, skip keys starting with "_" (except "_type")
    """
    base_indent = "\t" * indent_level
    entry_indent = "\t" * (indent_level + 1)
    parts = []

    for key, value in data.items():
        if skip_internal_keys and str(key).startswith("_") and key != "_type":
            continue

        lua_key = (
            f'["{key}"]'
            if not re.match(r"^[a-zA-Z_]\w*$", str(key))
            else str(key)
        )
        lua_value = to_lua_value(value, indent_level)
        parts.append(f"{entry_indent}{lua_key} = {lua_value},")

    if not parts:
        return "{}"
    return "{\n" + "\n".join(parts) + "\n" + base_indent + "}"


# ─── Wikitext Formatting ───────────────────────────────────────────────────

def to_wikitext_infobox(template_name, params):
    """
    Generate a MediaWiki infobox template call.

    Args:
        template_name: Name of the infobox template
        params: Dict of parameter_name -> value

    Returns:
        Wikitext string like {{TemplateName\n|key1 = val1\n|key2 = val2\n}}
    """
    lines = [f"{{{{{template_name}"]
    for key, value in sorted(params.items()):
        if value is not None and str(value) != "":
            lines.append(f"|{key} = {value}")
    lines.append("}}")
    return "\n".join(lines)
