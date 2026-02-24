"""
Generate map tile pyramids and metadata for the DOS2 interactive map.

Reads MiniMap.dds + WorldMapMetaData.lsj for each level, tiles the image
into WEBP tile pyramids (Leaflet-compatible), and outputs:
- <outdir>/tiles/<id>/<z>/<x>/<y>.webp  — tile images
- Module_MapData.lua                      — wiki Lua module
- <outdir>/basemaps.json                  — extension config

Requires Pillow: pip install Pillow

Ported from dos2_tools_old/scripts/export_maps.py.

Usage:
    python3 -m dos2_tools.scripts.export_maps
    python3 -m dos2_tools.scripts.export_maps --outdir map_data --tile-size 256
"""

import os
import json
import math
import argparse

try:
    from PIL import Image
except ImportError:
    raise ImportError(
        "Pillow is required for export_maps. Install with: pip install Pillow"
    )

from dos2_tools.core.game_data import GameData
from dos2_tools.core.file_system import get_files_by_pattern
from dos2_tools.core.formatters import to_lua_table


def generate_tiles(image_path, output_dir, tile_size=256):
    """
    Slice an image into a Leaflet-compatible tile pyramid.
    Returns (max_zoom, final_width, final_height) at the highest zoom level.
    """
    try:
        img = Image.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        width, height = img.size
        max_dim = max(width, height)
        max_zoom = int(math.ceil(math.log(max_dim / tile_size, 2)))

        final_w, final_h = width, height

        for z in range(max_zoom + 1):
            num_tiles = 2 ** z
            grid_size = tile_size * num_tiles
            scale_factor = grid_size / max_dim

            new_w = int(width * scale_factor)
            new_h = int(height * scale_factor)

            if z == max_zoom:
                final_w, final_h = new_w, new_h

            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (grid_size, grid_size), (0, 0, 0, 0))
            canvas.paste(resized, (0, 0))

            z_dir = os.path.join(output_dir, str(z))
            os.makedirs(z_dir, exist_ok=True)

            for x in range(num_tiles):
                x_dir = os.path.join(z_dir, str(x))
                os.makedirs(x_dir, exist_ok=True)
                for y in range(num_tiles):
                    left = x * tile_size
                    top = y * tile_size
                    tile = canvas.crop((left, top, left + tile_size, top + tile_size))
                    tile.save(os.path.join(x_dir, f"{y}.webp"), "WEBP", quality=80)

        return max_zoom, final_w, final_h

    except Exception as e:
        print(f"  Error processing {image_path}: {e}")
        return 0, 0, 0


def parse_minimap_lsj(filepath):
    """Extract world-coordinate metadata from a WorldMapMetaData LSJ file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = (
            data.get("save", {})
                .get("regions", {})
                .get("WorldMapMetaData", {})
        )
        return {
            "Width":       meta.get("Width", {}).get("value"),
            "Height":      meta.get("Height", {}).get("value"),
            "WorldWidth":  meta.get("WorldWidth", {}).get("value"),
            "WorldHeight": meta.get("WorldHeight", {}).get("value"),
            "WorldX":      meta.get("WorldX", {}).get("value"),
            "WorldZ":      meta.get("WorldZ", {}).get("value"),
        }
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate DOS2 interactive map tile pyramids and metadata"
    )
    parser.add_argument(
        "--outdir", default="map_data",
        help="Output directory for tiles and basemaps.json (default: map_data)"
    )
    parser.add_argument(
        "--tile-size", type=int, default=256,
        help="Tile size in pixels (default: 256)"
    )
    parser.add_argument(
        "--module-out", default="Module_MapData.lua",
        help="Output path for the Lua map data module"
    )
    args = parser.parse_args()

    tiles_dir = os.path.join(args.outdir, "tiles")
    os.makedirs(tiles_dir, exist_ok=True)

    game = GameData()
    file_index = game.file_index

    # Collect minimap LSJ files from the file index
    minimap_entries = get_files_by_pattern(
        file_index, ["Mods/**/Levels/**/WorldMap/MiniMap.lsj"]
    )

    # Last-write-wins per region (load order already handled by file_index)
    region_paths = {}
    for entry in minimap_entries:
        parts = entry.resolved_path.replace("\\", "/").split("/")
        if "WorldMap" not in parts:
            continue
        region_name = parts[parts.index("WorldMap") - 1]
        region_paths[region_name] = entry.resolved_path

    if not region_paths:
        print("No MiniMap.lsj files found. Make sure the exported game data is present.")
        return

    lua_map_data = {}
    base_maps_list = []
    current_map_id = 1

    for region_name, lsj_path in region_paths.items():
        meta = parse_minimap_lsj(lsj_path)
        if not meta:
            continue

        dds_path = os.path.join(os.path.dirname(lsj_path), "MiniMap.dds")
        if not os.path.exists(dds_path):
            print(f"  Skipping {region_name}: no MiniMap.dds found.")
            continue

        print(f"Processing {region_name} (ID: {current_map_id})...")

        temp_img = "_temp_map.webp"
        try:
            with Image.open(dds_path) as img:
                img.save(temp_img, "WEBP", quality=100)

            map_tile_dir = os.path.join(tiles_dir, str(current_map_id))
            max_zoom, w, h = generate_tiles(temp_img, map_tile_dir, args.tile_size)
        finally:
            if os.path.exists(temp_img):
                os.remove(temp_img)

        if max_zoom == 0:
            print(f"  Skipping {region_name}: tile generation failed.")
            continue

        lua_map_data[region_name] = {
            "id": current_map_id,
            "Width": w,
            "Height": h,
            "WorldWidth": meta["WorldWidth"],
            "WorldHeight": meta["WorldHeight"],
            "WorldX": meta["WorldX"],
            "WorldZ": meta["WorldZ"],
        }

        max_dim = max(w, h)
        norm_scale = args.tile_size / max_dim
        base_maps_list.append({
            "mapId": current_map_id,
            "name": region_name,
            "center": [-(h * norm_scale) / 2, (w * norm_scale) / 2],
            "bounds": [[-256, 0], [0, 256]],
            "zoomLimits": [0, max_zoom],
            "defaultZoom": 2,
            "maxNativeZoom": max_zoom,
        })

        current_map_id += 1

    # Write Lua module
    lua_str = "local p = {}\n\np.data = " + to_lua_table(lua_map_data) + "\n\nreturn p"
    with open(args.module_out, "w", encoding="utf-8") as f:
        f.write(lua_str)
    print(f"Generated {args.module_out}")

    # Write basemaps.json
    basemaps_path = os.path.join(args.outdir, "basemaps.json")
    with open(basemaps_path, "w", encoding="utf-8") as f:
        json.dump(base_maps_list, f, indent=2)
    print(f"Generated {basemaps_path}")

    print("Done.")


if __name__ == "__main__":
    main()
