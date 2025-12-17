import os
import json
import math
from PIL import Image
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.formatters import to_lua_table

# --- CONFIGURATION ---
TILE_SIZE = 256
OUTPUT_DIR = "map_data"
TILES_DIR = os.path.join(OUTPUT_DIR, "tiles")

def generate_tiles(image_path, output_dir):
    try:
        img = Image.open(image_path)
        # Convert to RGBA to support transparency in the empty space of the tiles
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
            
        width, height = img.size
        max_dim = max(width, height)
        
        # Calculate Max Zoom based on the largest dimension fitting into a 256px tile
        max_zoom = int(math.ceil(math.log(max_dim / TILE_SIZE, 2)))
        
        # We need to track the final scaled dimensions at max zoom for the metadata
        final_w, final_h = width, height

        for z in range(max_zoom + 1):
            num_tiles = 2 ** z
            
            # The full square size of the "world" at this zoom level
            grid_size = TILE_SIZE * num_tiles
            
            # Calculate the scale factor to fit the image into this grid
            # while maintaining aspect ratio
            scale_factor = grid_size / max_dim
            
            new_w = int(width * scale_factor)
            new_h = int(height * scale_factor)
            
            # If this is the max zoom, save these dimensions for the return value
            # This ensures markers line up perfectly with the scaled image
            if z == max_zoom:
                final_w, final_h = new_w, new_h

            # Resize the image preserving aspect ratio
            resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Create a transparent square canvas matching the grid size
            canvas = Image.new('RGBA', (grid_size, grid_size), (0, 0, 0, 0))
            
            # Paste the resized image at 0,0 (Top-Left)
            canvas.paste(resized_img, (0, 0))
            
            # --- Standard Slicing Logic ---
            z_dir = os.path.join(output_dir, str(z))
            os.makedirs(z_dir, exist_ok=True)
            
            for x in range(num_tiles):
                x_dir = os.path.join(z_dir, str(x))
                os.makedirs(x_dir, exist_ok=True)
                for y in range(num_tiles):
                    left = x * TILE_SIZE
                    top = y * TILE_SIZE
                    right = left + TILE_SIZE
                    bottom = top + TILE_SIZE
                    
                    # Crop from the CANVAS, not the resized image
                    tile = canvas.crop((left, top, right, bottom))
                    tile.save(os.path.join(x_dir, f"{y}.webp"), 'WEBP', quality=80)
                    
        return max_zoom, final_w, final_h
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return 0, 0, 0

def parse_minimap_lsj(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        meta = data.get("save", {}).get("regions", {}).get("WorldMapMetaData", {})
        return {
            "Width": meta.get("Width", {}).get("value"),
            "Height": meta.get("Height", {}).get("value"),
            "WorldWidth": meta.get("WorldWidth", {}).get("value"),
            "WorldHeight": meta.get("WorldHeight", {}).get("value"),
            "WorldX": meta.get("WorldX", {}).get("value"),
            "WorldZ": meta.get("WorldZ", {}).get("value")
        }
    except:
        return None

def main():
    conf = get_config()
    os.makedirs(TILES_DIR, exist_ok=True)

    all_files = resolve_load_order(conf['base_path'], conf['cache_file'])
    map_files = get_files_by_pattern(all_files, "Mods/**/Levels/**/WorldMap/MiniMap.lsj")
    
    lua_map_data = {}
    base_maps_list = []
    
    current_map_id = 1
    
    seen_maps = set()
    
    for lsj_path in map_files:
        path_parts = lsj_path.replace('\\', '/').split('/')
        if "WorldMap" not in path_parts: continue
        
        region_name = path_parts[path_parts.index("WorldMap") - 1]
        if region_name not in seen_maps:
            # print(f"Warning: Duplicate map for region {region_name}, skipping.")
            seen_maps.add(region_name)
            continue
        meta = parse_minimap_lsj(lsj_path)
        if not meta: continue
        
        dds_path = os.path.join(os.path.dirname(lsj_path), "MiniMap.dds")
        print(dds_path)
        
        if os.path.exists(dds_path):
            print(f"Processing {region_name} (ID: {current_map_id})...")
            
            temp_img = "temp_map.webp"
            with Image.open(dds_path) as img:
                img.save(temp_img, 'WEBP', quality=100)
            
            map_tile_dir = os.path.join(TILES_DIR, str(current_map_id))
            max_zoom, w, h = generate_tiles(temp_img, map_tile_dir)
            
            if os.path.exists(temp_img): os.remove(temp_img)

            # 1. Wiki Lua Data
            lua_map_data[region_name] = {
                "id": current_map_id,
                "Width": w, 
                "Height": h,
                "WorldWidth": meta['WorldWidth'],
                "WorldHeight": meta['WorldHeight'],
                "WorldX": meta['WorldX'],
                "WorldZ": meta['WorldZ']
            }

            # 2. Extension JSON Data
            # Note: OSRS fork uses "maxNativeZoom" to know when to stop requesting tiles
            max_dim = max(w, h)
            norm_scale = TILE_SIZE / max_dim
            
            norm_width = w * norm_scale
            norm_height = h * norm_scale

            base_maps_list.append({
                "mapId": current_map_id,
                "name": region_name,
                "center": [-norm_height/2, norm_width/2], 
                
                # Bounds: Square based on 256 (matches the tile grid)
                # We use [-256, 0] [0, 256] to tell Leaflet "This is a 256x256 world"
                # The user will see transparency if they pan to the edge, but the map won't break.
                "bounds": [[-256, 0], [0, 256]], 
                
                "zoomLimits": [0, max_zoom],
                "defaultZoom": 2,
                "maxNativeZoom": max_zoom
            })
            
            current_map_id += 1

    # Output Lua
    lua_str = "local p = {}\n\np.data = " + to_lua_table(lua_map_data) + "\n\nreturn p"
    with open("Module_MapData.lua", 'w', encoding='utf-8') as f:
        f.write(lua_str)

    # Output basemaps.json (The specific file the extension needs)
    with open(os.path.join(OUTPUT_DIR, "basemaps.json"), 'w', encoding='utf-8') as f:
        json.dump(base_maps_list, f, indent=2)

    print("Done.")

if __name__ == "__main__":
    main()