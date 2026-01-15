import re
from typing import List, Optional, Tuple, Dict
from collections import defaultdict
from dos2_tools.core.generators.base import Generator
from dos2_tools.core.generators.crafting import CraftingGenerator
from dos2_tools.core.models import WikiPage, Item, Location
from dos2_tools.core.formatters import sanitize_filename
from dos2_tools.core.config import BASE_GAME_MODULES

class ItemPageGenerator(Generator):
    def generate(self) -> List[WikiPage]:
        pages = []
        crafting_gen = CraftingGenerator(self.context)

        for stats_id, item in self.context.items.items():
            if self._should_skip(item):
                continue

            content = self._generate_page_content(item, crafting_gen)

            safe_name = sanitize_filename(item.name)

            page = WikiPage(
                title=safe_name,
                content=content,
                source_module=item.source_module
            )
            pages.append(page)

        return pages

    def _should_skip(self, item: Item) -> bool:
        if not item.name: return True
        if len(item.name) > 50: return True # Sanity check for bad names

        # Skip items that are purely internal/technical (heuristic)
        if item.name.startswith("SYS_"): return True

        return False

    def _group_locations(self, locations: List[Location]) -> Dict[Tuple[str, str, str], List[str]]:
        grouped = defaultdict(list)
        # Regex to parse legacy coordinates string if needed,
        # but our parser already extracts "X,Y,Z".

        for loc in locations:
            region = loc.region

            if loc.npc_name:
                loc_name = f"[[{loc.npc_name}]]|on_npc=Yes"
            elif loc.container_name:
                loc_name = f"{loc.container_name}"
            else:
                loc_name = "Ground Spawn"

            safe_uuid = loc.template_uuid if loc.template_uuid else ""

            # Key: (Region, Location Name, Specific UUID)
            key = (region, loc_name, safe_uuid)

            if loc.coordinates:
                grouped[key].append(loc.coordinates)
            else:
                # If no coords, we might still want to list it?
                # The original script put the whole string in coords if match failed.
                pass

        return grouped

    def _generate_page_content(self, item: Item, crafting_gen: CraftingGenerator) -> str:
        real_name = item.name
        stats_id = item.stats_id or "Unknown"
        page_header_uuid = item.template_uuid or ""

        # Determine Template Type
        template = "InfoboxItem"
        if "Skillbook" in real_name:
            template = "InfoboxSkillbook"
        elif item.stats_entry and item.stats_entry.type == "Weapon":
            template = "InfoboxWeapon"
        elif item.stats_entry and item.stats_entry.type == "Armor":
             template = "InfoboxArmour"
        elif item.stats_entry and item.stats_entry.type == "Shield":
             template = "InfoboxShield"

        content = f"{{{{{template}\n|name={real_name}\n|stats_id={stats_id}\n|root_template_uuid={page_header_uuid}"

        # Add Source/Giftbag info if applicable
        if item.source_module and item.source_module not in BASE_GAME_MODULES and item.source_module != "Base":
            content += f"\n|source_mod={item.source_module}"

        if item.description:
            safe_desc = item.description.replace('|', '{{!}}')
            content += f"\n|description={safe_desc}"

        if item.properties:
            props_str = ",".join(set(item.properties))
            content += f"\n|properties={props_str}"

        content += "\n}}\n"

        # Book Text
        if item.book_text:
            safe_bt = item.book_text.replace('|', '{{!}}')
            content += f"\n{{{{BookText|text={safe_bt}}}}}\n"

        # Recipes
        if item.taught_recipes:
             for r in sorted(set(item.taught_recipes)):
                 # TODO: Check if recipe prototype expansion is needed (like original script did).
                 # Original script loaded recipes_prototypes.lsj and expanded them.
                 # We haven't implemented that fully yet, just basic list.
                 content += f"\n{{{{BookTeaches|recipe={r}}}}}\n"

        # Locations
        if item.locations:
            grouped_locs = self._group_locations(item.locations)

            if grouped_locs:
                content += "\n== Locations ==\n"
                sorted_keys = sorted(grouped_locs.keys())

                for (region, loc_name, specific_uuid) in sorted_keys:
                    coords_list = grouped_locs[(region, loc_name, specific_uuid)]
                    # Sort coordinates
                    coords_list.sort()
                    coords_str = ";".join(coords_list)

                    uuid_to_use = specific_uuid if specific_uuid else page_header_uuid

                    content += f"{{{{ItemLocation|stats_id={stats_id}|root_template_uuid={uuid_to_use}|region={region}|location_name={loc_name}|coordinates={coords_str}}}}}\n"

                content += "\n{{ItemLocationTable}}\n"

        # Add Crafting Section
        crafting_section = crafting_gen.generate_crafting_section(item)
        content += crafting_section

        return content
