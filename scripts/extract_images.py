import os
import xml.etree.ElementTree as ET
from PIL import Image
from dos2_tools.core.config import get_config
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern

def main():
    conf = get_config()
    out_dir = 'all_extracted_icons'
    if not os.path.exists(out_dir): os.makedirs(out_dir)

    # Need "Icons" folder which isn't in standard load order
    load_order = ["Icons"] + conf['load_order_dirs']
    file_registry = {}
    
    # Custom resolution for icons to include 'Icons' directory
    for layer in load_order:
        layer_path = os.path.join(conf['base_path'], os.path.basename(layer)) # Handle full paths in config
        if not os.path.exists(layer_path):
             # Fallback if config has full paths but we constructed "Icons" manually
             if os.path.exists(layer): layer_path = layer
             else: continue

        for root, _, files in os.walk(layer_path):
            for filename in files:
                full = os.path.join(root, filename)
                rel = os.path.relpath(full, layer_path)
                norm = os.path.normpath(rel).lower()
                file_registry[norm] = full

    icon_registry = {}
    target_path = os.path.normpath(os.path.join('Public', 'Shared', 'GUI')).lower()
    
    xml_files = [p for k, p in file_registry.items() if k.endswith('.lsx') and target_path in k]

    for xml_path in xml_files:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            width = height = 0
            tex_path = ""
            
            for node in root.findall(".//node"):
                nid = node.get('id')
                if nid == 'TextureAtlasTextureSize':
                    for a in node.findall('attribute'):
                        if a.get('id') == 'Width': width = int(a.get('value'))
                        elif a.get('id') == 'Height': height = int(a.get('value'))
                elif nid == 'TextureAtlasPath':
                    for a in node.findall('attribute'):
                        if a.get('id') == 'Path': tex_path = a.get('value')

            if not width or not height or not tex_path: continue
            
            dds_key = os.path.normpath(os.path.join('Public', 'Shared', tex_path)).lower()
            full_dds = file_registry.get(dds_key)
            if not full_dds: continue
            
            for node in root.findall(".//node"):
                if node.get('id') == 'IconUV':
                    mk = ""
                    u1=u2=v1=v2=0.0
                    for a in node.findall('attribute'):
                        aid = a.get('id')
                        val = a.get('value')
                        if aid == 'MapKey': mk = val
                        elif aid == 'U1': u1 = float(val)
                        elif aid == 'U2': u2 = float(val)
                        elif aid == 'V1': v1 = float(val)
                        elif aid == 'V2': v2 = float(val)
                    
                    if mk:
                        icon_registry[mk] = {
                            'dds': full_dds, 'w': width, 'h': height,
                            'u1': u1, 'u2': u2, 'v1': v1, 'v2': v2
                        }
        except Exception as e:
            print(f"Error {xml_path}: {e}")

    by_atlas = {}
    for k, v in icon_registry.items():
        dds = v['dds']
        if dds not in by_atlas: by_atlas[dds] = []
        by_atlas[dds].append((k, v))
        
    for dds, icons in by_atlas.items():
        try:
            with Image.open(dds) as img:
                for k, v in icons:
                    l = round(v['u1'] * v['w'])
                    r = round(v['u2'] * v['w'])
                    t = round(v['v1'] * v['h'])
                    b = round(v['v2'] * v['h'])
                    
                    try:
                        crop = img.crop((l, t, r, b))
                        crop.save(os.path.join(out_dir, f"{k}_Icon.png"))
                    except: pass
        except: pass
        
    print("Done extracting icons.")

if __name__ == "__main__":
    main()