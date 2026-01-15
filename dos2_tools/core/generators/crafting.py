from typing import List, Optional
from dos2_tools.core.generators.base import Generator
from dos2_tools.core.models import WikiPage, Item, CraftingCombo

class CraftingGenerator(Generator):
    def generate(self) -> List[WikiPage]:
        # This generator doesn't generate full pages on its own usually,
        # but provides helper methods for other generators.
        # However, if we wanted "Crafting Only" pages, we could do it here.
        return []

    def generate_crafting_section(self, item: Item) -> str:
        """
        Generates the Crafting section for a specific item.
        Includes both recipes that CREATE this item, and recipes that USE this item.
        """
        if not item.stats_id:
            return ""

        creation_rows = []
        product_rows = []

        target_stats_id = item.stats_id
        target_categories = set(item.categories)
        target_properties = set(item.properties)

        for combo_id, combo in self.context.crafting_combos.items():
            result_id = combo.result_id

            is_creation = (result_id == target_stats_id)
            is_product = False

            if not is_creation:
                for i in range(1, 6):
                    obj_id = combo.ingredients.get(f"Object {i}")
                    obj_type = combo.ingredients.get(f"Type {i}")

                    if not obj_id: continue

                    if obj_type == "Object" and obj_id == target_stats_id:
                        is_product = True
                        break

                    if obj_type == "Category" and obj_id in target_categories:
                        is_product = True
                        break

                    if obj_type == "Property" and obj_id in target_properties:
                        is_product = True
                        break

            if not is_creation and not is_product:
                continue

            row_text = r"{{CraftingRow|%s}}" % combo_id

            if is_creation:
                creation_rows.append(row_text)
            elif is_product:
                product_rows.append(row_text)

        if not creation_rows and not product_rows:
            return ""

        output = ""

        if creation_rows:
            output += "\n== Crafting ==\n"
            output += self._wrap_table(creation_rows) + "\n"

        if product_rows:
            if not creation_rows:
                output += "\n== Crafting ==\n"
            output += "=== Used in ===\n"
            output += self._wrap_table(product_rows) + "\n"

        return output

    def _wrap_table(self, rows: List[str]) -> str:
        if not rows: return ""
        header = '{{CraftingTable/Header}}\n'
        body = '\n'.join(rows)
        footer = '\n{{CraftingTable/Footer}}'
        return header + body + footer
