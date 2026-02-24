"""
Wiki page section generators for DOS2 items.

Each function generates one section of a wiki item page as wikitext.
Sections can be generated individually or composed into a full page.

Usage:
    from dos2_tools.core.game_data import GameData
    from dos2_tools.wiki import items

    game = GameData()
    # Generate just the locations section:
    loc_text = items.generate_locations_section(stats_id, game)

    # Generate a full page:
    page = items.generate_full_page(stats_id, game)

    # Generate only specific sections:
    page = items.generate_full_page(stats_id, game, sections=["infobox", "locations"])
"""

import re
import json
from collections import defaultdict, OrderedDict

from dos2_tools.core.config import VALID_LEVELS, LOAD_ORDER_METADATA
from dos2_tools.core.data_models import LSJNode
from dos2_tools.core.parsers import parse_lsj_templates
from dos2_tools.core.formatters import sanitize_filename
from dos2_tools.core.file_system import get_files_by_pattern


# All available section names, in canonical page order
SECTION_ORDER = [
    "infobox",
    "book_text",
    "book_teaches",
    "locations",
    "crafting",
    "version_history",
]


# ─── Helper Functions ───────────────────────────────────────────────────────

def get_region_name(file_path):
    """Extract the region/level name from a file path."""
    parts = file_path.replace("\\", "/").split("/")
    if "Levels" in parts:
        return parts[parts.index("Levels") + 1]
    if "Globals" in parts:
        return parts[parts.index("Globals") + 1]
    return "Unknown"


def format_coordinate(transform_node):
    """Extract coordinates from a Transform node."""
    if not transform_node:
        return None
    if isinstance(transform_node, list) and len(transform_node) > 0:
        node = LSJNode(transform_node[0])
        val = node.get_value("Position", "")
        if val:
            return val.replace(" ", ",")
    return None


def resolve_node_name(node_data, localization):
    """Resolve the display name of a game object node via localization.

    Only returns text that came from english.xml:
      1. DisplayName.handle → handle_map lookup
      2. Stats value → UUID-based localization lookup

    The raw Name field is intentionally excluded — it is an internal
    object identifier set by developers, never a player-visible string.
    The discriminator between a real name and an internal ID is whether
    the handle resolves in english.xml.
    """
    node = LSJNode(node_data) if not isinstance(node_data, LSJNode) else node_data

    handle = node.get_handle("DisplayName")
    if handle:
        text = localization.get_handle_text(handle)
        if text:
            return text

    stats_id = node.get_value("Stats")
    if stats_id and stats_id != "None":
        return localization.get_text(stats_id)

    return None


def extract_action_data(node_data):
    """Extract book ID and taught recipes from OnUsePeaceActions."""
    node = LSJNode(node_data) if not isinstance(node_data, LSJNode) else node_data
    book_id = None
    direct_recipes = []

    for action_block in node.get_list("OnUsePeaceActions"):
        for act in action_block.get_list("Action"):
            act_node = LSJNode(act) if not isinstance(act, LSJNode) else act
            type_val = act_node.get_value("ActionType", -1)

            for attr in act_node.get_list("Attributes"):
                if type_val == 11:
                    bid = attr.get_value("BookId")
                    if bid:
                        book_id = bid
                elif type_val == 30:
                    val = attr.get_value("RecipeID")
                    if val:
                        direct_recipes.extend(
                            x.strip() for x in val.split(";") if x.strip()
                        )

    return book_id, direct_recipes


def parse_and_group_locations(location_tuples):
    """Group raw location strings by (region, location_name, uuid)."""
    grouped = defaultdict(list)
    pattern = re.compile(
        r"([-\d\.,]+)\s*\(([^)]+)\)(?:\s*inside\s*(.+))?"
    )

    for loc_str, uuid in location_tuples:
        match = pattern.search(loc_str)
        if match:
            coords = match.group(1)
            region = match.group(2)
            container = match.group(3)
            loc_name = container if container else "Ground Spawn"
            safe_uuid = uuid if uuid else ""
            grouped[(region, loc_name, safe_uuid)].append(coords)
        else:
            safe_uuid = uuid if uuid else ""
            grouped[("Unknown", "Unknown", safe_uuid)].append(loc_str)

    return grouped


# ─── Level Scanning ─────────────────────────────────────────────────────────

def scan_levels_for_items(game_data):
    """
    Scan all level files for item placements.

    Returns:
        tuple: (template_locs, container_locs, unique_variants, found_regions)
    """
    loc = game_data.localization
    root_template_db = _build_root_template_db(game_data)

    template_locs = defaultdict(list)
    container_locs = defaultdict(list)
    unique_variants = {}
    found_regions = set()

    # Scan item level files
    level_item_files = game_data.get_file_paths("level_items")

    for f_path in level_item_files:
        if not any(lv in f_path for lv in VALID_LEVELS):
            continue

        region = get_region_name(f_path)
        found_regions.add(region)
        _, level_objects = parse_lsj_templates(f_path)

        for map_key, obj_data in level_objects.items():
            obj = obj_data.as_lsj_node()  # GameObject → LSJNode for field access
            coords = format_coordinate(obj.get_raw("Transform"))
            if not coords:
                continue

            full_loc_str = f"{coords} ({region})"
            template_uuid = obj_data.template_name

            if template_uuid:
                instance_name = resolve_node_name(obj_data._to_raw_dict(), loc)

                default_rt_data = root_template_db.get(template_uuid, {})

                if (instance_name and
                        instance_name != default_rt_data.get("name")):
                    safe_var_name = sanitize_filename(instance_name)

                    if safe_var_name not in unique_variants:
                        stats_val = obj_data.stats_id
                        if not stats_val:
                            stats_val = default_rt_data.get("stats_id")

                        book_id, recipes = extract_action_data(obj_data)
                        if not book_id:
                            book_id = default_rt_data.get("book_id")
                        if not recipes:
                            recipes = default_rt_data.get("recipes", [])

                        desc_handle = obj.get_handle("Description")
                        desc_override = (
                            loc.get_handle_text(desc_handle) if desc_handle else None
                        )

                        unique_variants[safe_var_name] = {
                            "name": instance_name,
                            "stats_id": stats_val,
                            "root_template_uuid": template_uuid,
                            "description": desc_override,
                            "book_id": book_id,
                            "recipes": recipes,
                            "locations": set(),
                            "is_variant": True,
                        }

                    unique_variants[safe_var_name]["locations"].add(full_loc_str)
                else:
                    template_locs[template_uuid].append(full_loc_str)

            # Items inside containers
            if obj.has("ItemList"):
                container_name = (
                    resolve_node_name(obj_data._to_raw_dict(), loc) or "Container"
                )
                _scan_item_list(
                    obj.get_list("ItemList"), full_loc_str, container_name,
                    template_locs, container_locs
                )

    # Scan character files for inventory items
    char_files = game_data.get_file_paths("level_characters")

    for f_path in char_files:
        if any(x in f_path for x in ("Test", "Develop", "GM_", "Arena")):
            continue

        region = get_region_name(f_path)
        found_regions.add(region)
        _, level_objects = parse_lsj_templates(f_path)

        for map_key, obj_data in level_objects.items():
            obj = obj_data.as_lsj_node()  # GameObject → LSJNode for field access
            coords = format_coordinate(obj.get_raw("Transform"))
            if not coords:
                continue

            npc_name = resolve_node_name(obj_data._to_raw_dict(), loc)
            if npc_name:
                npc_name = f"[[{npc_name}]]|on_npc=Yes"
            else:
                npc_name = "Unknown NPC"

            full_loc_str = f"{coords} ({region})"
            if obj.has("ItemList"):
                _scan_item_list(
                    obj.get_list("ItemList"), full_loc_str, npc_name,
                    template_locs, container_locs
                )

    return template_locs, container_locs, unique_variants, sorted(found_regions)


def _scan_item_list(item_list_nodes, loc_str, container_name,
                    template_locs, container_locs):
    """Scan an ItemList for template/stats references."""
    for item_entry in item_list_nodes:
        for item in item_entry.get_list("Item"):
            t_uuid = item.get_value("TemplateID")
            stats_id = item.get_value("ItemName")

            loc_desc = f"{loc_str} inside {container_name}"
            if t_uuid:
                template_locs[t_uuid].append(loc_desc)
            elif stats_id:
                container_locs[stats_id].append(loc_desc)


def _build_root_template_db(game_data):
    """Build a lookup of root template UUID -> item info.

    Only includes templates that have a DisplayName handle which resolves
    in english.xml. This is the correct discriminator — the Name field
    on root template objects is an internal object identifier, not a
    player-visible display name.
    """
    loc = game_data.localization
    rt_raw = game_data.templates_by_mapkey
    db = {}

    for rt_uuid, rt_data in rt_raw.items():
        if rt_data.type != "item":
            continue

        # Use the GameObject API directly: display_name holds the DisplayName
        # dict with handle → english.xml lookup. Stats fallback also allowed.
        name = None
        if rt_data.display_name and isinstance(rt_data.display_name, dict):
            handle = rt_data.display_name.get("handle")
            if handle:
                name = loc.get_handle_text(handle)
        if not name and rt_data.stats_id:
            name = loc.get_text(rt_data.stats_id)

        # No localized name means this template has no player-visible identity
        if not name:
            continue

        desc_handle = rt_data.get_handle("Description")
        desc = loc.get_handle_text(desc_handle) if desc_handle else None

        book_id, recipes = extract_action_data(rt_data._to_raw_dict())

        db[rt_uuid] = {
            "name": name,
            "stats_id": rt_data.stats_id,
            "description": desc,
            "book_id": book_id,
            "recipes": recipes,
            "raw_data": rt_data,
        }

    return db


# ─── Section Generators ────────────────────────────────────────────────────

def generate_infobox(name, stats_id, root_template_uuid, description=None,
                     properties=None, template="InfoboxItem"):
    """
    Generate the infobox template call for an item.

    Args:
        name: Display name
        stats_id: Stats entry ID
        root_template_uuid: Root template UUID
        description: Item description text
        properties: List of combo property IDs
        template: Infobox template name (InfoboxItem, InfoboxWeapon, etc.)

    Returns:
        str: Wikitext for the infobox
    """
    content = (
        f"{{{{{template}\n"
        f"|name={name}\n"
        f"|stats_id={stats_id}\n"
        f"|root_template_uuid={root_template_uuid or ''}"
    )

    if description:
        safe_desc = description.replace("|", "{{!}}")
        content += f"\n|description={safe_desc}"

    if properties:
        props_str = ",".join(set(properties))
        content += f"\n|properties={props_str}"

    content += "\n}}\n"
    return content


def generate_book_text_section(book_id, localization):
    """
    Generate the book text section (for readable items).

    Args:
        book_id: The book's content handle/UUID
        localization: Localization resolver

    Returns:
        str: Wikitext for the book text, or empty string if none
    """
    if not book_id:
        return ""

    book_text = localization.get_text(book_id)

    if not book_text:
        # Try handle-based lookup
        book_text = localization.get_handle_text(book_id)

    if book_text and isinstance(book_text, str):
        safe_bt = book_text.replace("|", "{{!}}")
        return f"\n{{{{BookText|text={safe_bt}}}}}\n"

    return ""


def generate_book_teaches_section(taught_recipes, recipe_proto_db=None):
    """
    Generate the recipes taught by a book/skillbook.

    Args:
        taught_recipes: List of recipe IDs directly taught
        recipe_proto_db: Optional map of recipe_id -> list of output recipes

    Returns:
        str: Wikitext for taught recipes, or empty string
    """
    final_recipes = set()

    for r_id in taught_recipes:
        if recipe_proto_db and r_id in recipe_proto_db:
            for sub_r in recipe_proto_db[r_id]:
                final_recipes.add(sub_r)
        else:
            final_recipes.add(r_id)

    if not final_recipes:
        return ""

    content = ""
    for r in sorted(final_recipes):
        content += f"\n{{{{BookTeaches|recipe={r}}}}}\n"
    return content


def generate_locations_section(stats_id, root_template_uuid,
                               grouped_locations):
    """
    Generate the Locations section for an item.

    Args:
        stats_id: Item stats ID
        root_template_uuid: Default root template UUID
        grouped_locations: Dict from parse_and_group_locations()

    Returns:
        str: Wikitext for the locations section, or empty string
    """
    if not grouped_locations:
        return ""

    content = "\n== Locations ==\n"
    sorted_keys = sorted(grouped_locations.keys())

    for (region, loc_name, specific_uuid) in sorted_keys:
        coords_list = grouped_locations[(region, loc_name, specific_uuid)]
        coords_str = ";".join(coords_list)
        uuid_to_use = specific_uuid if specific_uuid else root_template_uuid
        content += (
            f"{{{{ItemLocation|stats_id={stats_id}"
            f"|root_template_uuid={uuid_to_use}"
            f"|region={region}|location_name={loc_name}"
            f"|coordinates={coords_str}}}}}\n"
        )

    content += "\n{{ItemLocationTable}}\n"
    return content


def generate_crafting_section(stats_id, item_categories, properties,
                              all_combos, resolved_stats, root_template_db,
                              item_name, root_template_uuid=None):
    """
    Generate the Crafting section for an item.

    Shows recipes that create this item and recipes that use it.

    Args:
        stats_id: The item's stats ID
        item_categories: List of ComboCategory values for this item
        properties: List of combo property IDs
        all_combos: All item combos from the game data
        resolved_stats: All resolved stats
        root_template_db: Root template database
        item_name: Display name of the item
        root_template_uuid: Root template UUID

    Returns:
        str: Wikitext for the crafting section, or empty string
    """
    creation_entries = []
    product_entries = []

    def get_sort_name(sid):
        if not sid or not resolved_stats or not root_template_db:
            return sid or ""
        stat_data = resolved_stats.get(sid)
        if not stat_data:
            return sid
        rt_uuid = stat_data.get("RootTemplate")
        if not rt_uuid or rt_uuid not in root_template_db:
            return sid
        return root_template_db[rt_uuid].get("name", sid)

    for combo_id, combo in all_combos.items():
        data = combo.get("Data", {})
        results = combo.get("Results", {})
        giftbag = combo.get("Giftbag", "None")
        result_id = results.get("Result 1")

        is_creation = (result_id == stats_id)
        is_product = False

        if not is_creation:
            for i in range(1, 6):
                obj_id = data.get(f"Object {i}")
                obj_type = data.get(f"Type {i}")
                if not obj_id:
                    continue
                if obj_type == "Object" and obj_id == stats_id:
                    is_product = True
                    break
                if obj_type == "Category" and item_categories:
                    if obj_id in item_categories:
                        is_product = True
                        break
                if obj_type == "Property" and properties:
                    if obj_id in properties:
                        is_product = True
                        break

        if not is_creation and not is_product:
            continue

        # Filter false-positive creations for items with different root templates
        if is_creation and resolved_stats:
            stat_data = resolved_stats.get(stats_id)
            if stat_data:
                def_rt = stat_data.get("RootTemplate")
                if def_rt:
                    if root_template_uuid and def_rt != root_template_uuid:
                        continue
                    if (root_template_db and item_name
                            and def_rt in root_template_db):
                        rt_name = root_template_db[def_rt].get("name")
                        if rt_name and rt_name != item_name:
                            continue

        if giftbag:
            row_text = "{{CraftingRow|%s|%s}}" % (combo_id, giftbag)
        else:
            row_text = "{{CraftingRow|%s}}" % combo_id

        gb_rank = 0 if not giftbag else 1
        sort_name = (
            get_sort_name(data.get("Object 1")) if is_creation
            else get_sort_name(result_id)
        )

        entry = {"text": row_text, "sort_key": (gb_rank, giftbag, sort_name)}
        if is_creation:
            creation_entries.append(entry)
        else:
            product_entries.append(entry)

    creation_entries.sort(key=lambda x: x["sort_key"])
    product_entries.sort(key=lambda x: x["sort_key"])

    def wrap_table(rows):
        if not rows:
            return None
        header = "{{CraftingTable/Header}}\n"
        body = "\n".join(r["text"] for r in rows)
        footer = "\n{{CraftingTable/Footer}}"
        return header + body + footer

    creation_table = wrap_table(creation_entries)
    product_table = wrap_table(product_entries)

    if not creation_table and not product_table:
        return ""

    content = ""
    if creation_table:
        content += "\n== Crafting ==\n"
        content += creation_table + "\n"

    if product_table:
        if not creation_table:
            content += "\n== Crafting ==\n"
        content += "=== Used in ===\n"
        content += product_table + "\n"

    return content


def generate_version_history_section(stats_id, game_data):
    """
    Generate a Version History section showing which patches affected this item.

    This is a NEW section type not present in the old tooling.

    Args:
        stats_id: The item's stats ID
        game_data: GameData instance

    Returns:
        str: Wikitext for the version history section, or empty string
    """
    # Find all files that reference this stats_id
    relevant_files = []
    for rel_path, entry in game_data.file_index.items():
        # Only check stats files (not level data etc.)
        if "Stats/Generated/Data/" not in rel_path:
            continue
        if not entry.was_overridden:
            continue
        relevant_files.append(entry)

    if not relevant_files:
        return ""

    # Check which of these files actually contain our stats_id
    versions_affected = set()
    for entry in relevant_files:
        for version in entry.modified_by:
            metadata = LOAD_ORDER_METADATA.get(version, {})
            if metadata.get("category") in ("patch", "giftbag"):
                versions_affected.add(version)

    if not versions_affected:
        return ""

    content = "\n== Version History ==\n"
    content += "This item's stats file was modified in the following updates:\n"
    for version in sorted(versions_affected):
        label = LOAD_ORDER_METADATA.get(version, {}).get("label", version)
        content += f"* {label}\n"

    return content


# ─── Full Page Generator ───────────────────────────────────────────────────

def generate_full_page(page_data, game_data, sections=None):
    """
    Generate a complete wiki page for an item.

    Args:
        page_data: Dict with keys: name, stats_id, root_template_uuid,
                   description, book_id, taught_recipes, properties,
                   locations (set of (loc_str, uuid) tuples)
        game_data: GameData instance
        sections: Optional list of section names to include.
                  If None, all sections are included.

    Returns:
        str: Complete wikitext for the page
    """
    if sections is None:
        sections = SECTION_ORDER

    name = page_data.get("name", "Unknown")
    stats_id = page_data.get("stats_id", "Unknown")
    rt_uuid = page_data.get("root_template_uuid", "")
    description = page_data.get("description")
    book_id = page_data.get("book_id")
    taught_recipes = page_data.get("taught_recipes", [])
    properties = page_data.get("properties", [])
    raw_locations = page_data.get("locations", set())

    content = ""

    # Determine infobox template type
    template = _determine_infobox_template(name, stats_id, game_data)

    if "infobox" in sections:
        content += generate_infobox(
            name, stats_id, rt_uuid, description, properties, template
        )

    if "book_text" in sections and book_id:
        content += generate_book_text_section(book_id, game_data.localization)

    if "book_teaches" in sections and taught_recipes:
        recipe_db = _load_recipe_prototypes(game_data)
        content += generate_book_teaches_section(taught_recipes, recipe_db)

    if "locations" in sections and raw_locations:
        grouped = parse_and_group_locations(sorted(list(raw_locations)))
        content += generate_locations_section(stats_id, rt_uuid, grouped)

    if "crafting" in sections and stats_id and stats_id != "Unknown":
        item_cats = []
        if stats_id in game_data.stats:
            cat_str = game_data.stats[stats_id].get("ComboCategory", "")
            if cat_str:
                item_cats = [c.strip() for c in cat_str.split(",") if c.strip()]

        rt_db = _build_root_template_db(game_data)
        content += generate_crafting_section(
            stats_id, item_cats, properties, game_data.item_combos,
            game_data.stats, rt_db, name, rt_uuid
        )

    if "version_history" in sections:
        content += generate_version_history_section(stats_id, game_data)

    return content


def _determine_infobox_template(name, stats_id, game_data):
    """Determine which infobox template to use based on item type."""
    safe_name = sanitize_filename(name)
    if "Skillbook" in safe_name:
        return "InfoboxSkillbook"

    stats = game_data.stats.get(stats_id, {})
    item_type = stats.get("_type", "")

    if item_type == "Weapon":
        return "InfoboxWeapon"
    elif item_type == "Armor":
        return "InfoboxArmour"
    elif item_type == "Shield":
        return "InfoboxArmour"

    return "InfoboxItem"


def _load_recipe_prototypes(game_data):
    """Load recipe prototype data from LSJ files."""
    recipe_files = game_data.get_file_paths("recipes")
    recipe_map = defaultdict(list)

    for f_path in recipe_files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        root = LSJNode(data)
        recipes_node = (
            root.get_node("save").get_node("regions").get_node("Recipes")
        )

        for r in recipes_node.get_list("Recipe"):
            title = r.get_value("Title")
            r_id = r.get_value("RecipeID")
            output_str = r.get_value("Recipes")

            if not output_str:
                continue

            outputs = [x.strip() for x in output_str.split(",") if x.strip()]

            if title:
                recipe_map[title].extend(outputs)
            if r_id and r_id != title:
                recipe_map[r_id].extend(outputs)

    return recipe_map
