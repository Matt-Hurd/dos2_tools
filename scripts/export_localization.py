"""
Export all UUID→localized text mappings to JSON or Lua.

Thin CLI using GameData(). Useful for building wiki modules that need
to look up item names from UUIDs.

Usage:
    python3 -m dos2_tools.scripts.export_localization
    python3 -m dos2_tools.scripts.export_localization --format lua
    python3 -m dos2_tools.scripts.export_localization --format json --output UUID_Localization
"""

import json
import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import sanitize_lua_string


def main():
    parser = argparse.ArgumentParser(
        description="Export DOS2 UUID→localization text mappings"
    )
    parser.add_argument(
        "--format", choices=["json", "lua"], default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "--output", default="UUID_Localization",
        help="Output file stem (without extension, default: UUID_Localization)"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization

    # Build UUID→text by resolving each UUID's handle through the handle map
    final_output = {}
    for uuid, entries in loc.uuid_map.items():
        if not entries:
            continue
        # Pick the canonical handle (deterministic: first by file sort)
        sorted_entries = sorted(entries, key=lambda e: e["file"])
        handle = sorted_entries[0]["handle"]
        text = loc.get_handle_text(handle)
        if text:
            final_output[uuid] = text

    print(f"  Collected {len(final_output)} UUID→text mappings.")

    if args.format == "json":
        fname = f"{args.output}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, sort_keys=True, ensure_ascii=False)
    else:
        fname = f"{args.output}.lua"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("return {\n")
            for uuid, text in sorted(final_output.items()):
                f.write(f'    ["{uuid}"] = "{sanitize_lua_string(text)}",\n')
            f.write("}\n")

    print(f"Exported {len(final_output)} keys to {fname}")


if __name__ == "__main__":
    main()
