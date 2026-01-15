import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Any

from dos2_tools.core.config import get_config, get_module_name_from_path, BASE_GAME_MODULES
from dos2_tools.core.file_system import resolve_load_order, get_files_by_pattern
from dos2_tools.core.models import StatEntry, RootTemplate, Item, Location, CraftingCombo, Recipe
from dos2_tools.core.parsers import (
    parse_stats_txt,
    parse_lsj_templates,
    parse_xml_localization,
    parse_item_combos,
    parse_item_combo_properties,
    parse_object_category_previews,
    _resolve_value_from_dict_or_str,
    _extract_action_data
)

class AppContext:
    def __init__(self, active_modules: Optional[List[str]] = None):
        self.config = get_config(active_modules)
        self.base_path = self.config["base_path"]

        # Data stores
        self.stats: Dict[str, StatEntry] = {}
        self.templates: Dict[str, RootTemplate] = {}
        self.localization: Dict[str, str] = {}
        self.items: Dict[str, Item] = {}
        self.recipes: Dict[str, List[str]] = defaultdict(list)
        self.crafting_combos: Dict[str, CraftingCombo] = {}
        self.combo_properties: Dict[str, Any] = {}
        self.category_previews: Dict[str, Dict[str, str]] = {}

        # Locations mapping: Key=TemplateUUID or StatsID, Value=List[Location]
        self.raw_locations: Dict[str, List[Location]] = defaultdict(list)

        self._load_data()
        self._resolve_items()

    def _load_data(self):
        """Discovers files and parses them."""
        print("Resolving file load order...")
        all_files = resolve_load_order(self.base_path, self.config["load_order_dirs"])

        # 1. Localization
        print("Loading Localization...")
        loc_files = get_files_by_pattern(all_files, self.config["patterns"]["localization_xml"])
        for f in loc_files:
            self.localization.update(parse_xml_localization(f))

        # 2. Stats
        print("Loading Stats...")
        stats_patterns = [
            "stats", "objects", "potions", "armors", "shields", "weapons", "skills"
        ]
        for p_key in stats_patterns:
            files = get_files_by_pattern(all_files, self.config["patterns"][p_key])
            for f in files:
                module_name = get_module_name_from_path(f)
                parsed_entries = parse_stats_txt(f)

                for entry in parsed_entries.values():
                    entry.source_module = module_name

                self.stats.update(parsed_entries)

        # 3. Root Templates
        print("Loading Root Templates...")
        rt_files = get_files_by_pattern(all_files, self.config["patterns"]["merged_lsj"])
        rt_files.extend(get_files_by_pattern(all_files, self.config["patterns"]["root_templates_lsj"]))
        for f in rt_files:
            module_name = get_module_name_from_path(f)
            parsed_templates = parse_lsj_templates(f)

            for tmpl in parsed_templates.values():
                tmpl.source_module = module_name

            self.templates.update(parsed_templates)

        # 4. Crafting
        print("Loading Crafting Data...")
        combo_files = get_files_by_pattern(all_files, self.config["patterns"]["item_combos"])
        for f in combo_files:
            module_name = get_module_name_from_path(f)
            parsed_combos = parse_item_combos(f)
            for c in parsed_combos.values():
                c.source_module = module_name
            self.crafting_combos.update(parsed_combos)

        prop_files = get_files_by_pattern(all_files, self.config["patterns"]["item_combo_properties"])
        for f in prop_files:
            self.combo_properties.update(parse_item_combo_properties(f))

        cat_files = get_files_by_pattern(all_files, self.config["patterns"]["object_categories_item_combos"])
        for f in cat_files:
            self.category_previews.update(parse_object_category_previews(f))

        # 5. Level Scanning (Locations)
        print("Scanning Levels for Items...")
        self._scan_levels(all_files)

    def _get_region_name(self, file_path):
        parts = file_path.replace('\\', '/').split('/')
        if "Levels" in parts:
            return parts[parts.index("Levels")+1]
        if "Globals" in parts:
            return parts[parts.index("Globals")+1]
        return "Unknown"

    def _format_coordinate(self, transform_node):
        if not transform_node: return None
        if isinstance(transform_node, list) and len(transform_node) > 0:
            pos_node = transform_node[0].get("Position")
            if pos_node:
                val = pos_node.get("value", "")
                return val.replace(" ", ",")
        return None

    def _resolve_node_name(self, node_data):
        display_node = node_data.get("DisplayName")
        if display_node and isinstance(display_node, dict):
            handle = display_node.get("handle")
            if handle in self.localization:
                return self.localization[handle]
        return None

    def _scan_levels(self, all_files):
        # We need a temporary reverse map for UUID -> Name lookups if needed,
        # but we mainly rely on localization.

        valid_levels = [
            "ARX_Endgame", "ARX_Main", "CoS_Main", "CoS_Main_Ending",
            "FJ_FortJoy_Main", "LV_HoE_Main", "RC_Main", "TUT_Tutorial_A",
        ]

        level_files = get_files_by_pattern(all_files, self.config["patterns"]["level_items"])
        char_files = get_files_by_pattern(all_files, self.config["patterns"]["level_characters"])

        # Combine both lists and process similarly
        for f_path in level_files + char_files:
            # Basic optimization: skip test levels if desired, though existing logic only filtered specifically.
            if "GM_" in f_path or "Arena" in f_path or "Test" in f_path: continue

            # Filter by valid levels if strict matching is required,
            # but let's be broader or match existing behavior.
            is_valid_level = any(lv in f_path for lv in valid_levels)
            if not is_valid_level and f_path in level_files:
                continue # Original script only filtered level_items, strict on valid_levels.
                         # Original script did NOT filter char_files by valid_levels strictly, only ignored Test/GM.

            region = self._get_region_name(f_path)

            # Using parse_lsj_templates because the structure is GoObjects
            # But the existing parser returns RootTemplates which is slightly semantic mismatch,
            # but the underlying `raw_data` is what we need.
            # However, `parse_lsj_templates` logic might skip things without Stats/MapKey.
            # Ideally we re-use the parser or write a specific one.
            # `parse_lsj_templates` is good enough if it returns the objects.

            # Actually, `parse_lsj_templates` in `parsers.py` returns objects that have MapKey OR Stats.
            # Level objects (instances) definitely have MapKey (GUID).

            parsed_objects = parse_lsj_templates(f_path)

            for uuid, rt_obj in parsed_objects.items():
                obj_data = rt_obj.raw_data

                coords = self._format_coordinate(obj_data.get("Transform"))
                if not coords: continue

                template_uuid = _resolve_value_from_dict_or_str(obj_data.get("TemplateName"))
                stats_id = rt_obj.stats_id

                # Container/NPC Name
                instance_name = self._resolve_node_name(obj_data)

                # Determine if this object IS the item, or CONTAINS items.

                # 1. If this object is an Item (has TemplateName matching a known Item Template)
                # In the original script, it checked if `template_uuid` is in `root_template_db`.
                # If so, it recorded the location for that template.

                if template_uuid:
                    loc = Location(
                        region=region,
                        coordinates=coords,
                        level_name=region,
                        template_uuid=template_uuid
                    )
                    self.raw_locations[template_uuid].append(loc)

                # 2. Check Inventory (ItemList)
                item_list_root = obj_data.get("ItemList", [])
                if item_list_root:
                    container_name = instance_name or "Container"
                    # Refine NPC name
                    if f_path in char_files:
                         npc_name = instance_name or "Unknown NPC"
                         container_label = None # Logic uses npc_name in output
                    else:
                         npc_name = None
                         container_label = container_name

                    for item_entry in item_list_root:
                        items = item_entry.get("Item", [])
                        if not isinstance(items, list): items = [items]

                        for item in items:
                            t_uuid = _resolve_value_from_dict_or_str(item.get("TemplateID"))
                            s_id = _resolve_value_from_dict_or_str(item.get("ItemName"))

                            loc = Location(
                                region=region,
                                coordinates=coords,
                                container_name=container_label,
                                npc_name=npc_name,
                                level_name=region
                            )

                            if t_uuid:
                                self.raw_locations[t_uuid].append(loc)
                            elif s_id:
                                self.raw_locations[s_id].append(loc)

    def _resolve_items(self):
        """
        Links Stats, Templates, and Localization into cohesive Item objects.
        """
        print("Resolving Items...")

        # Link templates to stats first
        stats_to_template = {}
        for uuid, tmpl in self.templates.items():
            if tmpl.stats_id:
                stats_to_template[tmpl.stats_id] = tmpl

        # Create Item objects for all Stats entries
        for stat_name, stat_entry in self.stats.items():
            # Basic validation to skip junk entries
            if not stat_entry.type and not stat_entry.using:
                continue

            item = Item(name=stat_name, stats_id=stat_name, stats_entry=stat_entry)
            item.source_module = stat_entry.source_module # Inherit source from stats

            # Resolve Name
            display_name_handle = stat_entry.data.get("DisplayName")
            if display_name_handle:
                # Handle cases like "Handle;Version"
                clean_handle = display_name_handle.split(";")[0]
                if clean_handle in self.localization:
                    item.name = self.localization[clean_handle]

            # Link Template
            tmpl = stats_to_template.get(stat_name)
            if tmpl:
                item.root_template = tmpl
                item.template_uuid = tmpl.uuid

                # Inherit Book/Recipe Data
                item.book_id = tmpl.book_id
                item.taught_recipes = list(tmpl.taught_recipes) # Copy list

                # Fallback name from template
                if item.name == stat_name and tmpl.display_name_handle:
                     if tmpl.display_name_handle in self.localization:
                         item.name = self.localization[tmpl.display_name_handle]

                # Description
                if tmpl.description_handle:
                    if tmpl.description_handle in self.localization:
                        item.description = self.localization[tmpl.description_handle]

            # Resolve Description from Stats if not found in template
            if not item.description:
                desc_handle = stat_entry.data.get("Description")
                if desc_handle:
                    clean_handle = desc_handle.split(";")[0]
                    if clean_handle in self.localization:
                        item.description = self.localization[clean_handle]

            # Resolve Categories
            cat_str = stat_entry.data.get("ComboCategory")
            if cat_str:
                item.categories = [c.strip() for c in cat_str.split(";") if c.strip()]

            # Resolve Locations
            # 1. By Stats ID
            if stat_name in self.raw_locations:
                item.locations.extend(self.raw_locations[stat_name])

            # 2. By Template UUID
            if item.template_uuid and item.template_uuid in self.raw_locations:
                 item.locations.extend(self.raw_locations[item.template_uuid])

            # Resolve Book Text
            if item.book_id:
                if item.book_id in self.localization:
                    item.book_text = self.localization[item.book_id]

            self.items[stat_name] = item

    def get_item(self, stats_id: str) -> Optional[Item]:
        return self.items.get(stats_id)

    def get_template(self, uuid: str) -> Optional[RootTemplate]:
        return self.templates.get(uuid)

    def get_localized_text(self, handle: str) -> Optional[str]:
        return self.localization.get(handle)
