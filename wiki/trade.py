"""
Wiki trade table renderer for DOS2 vendor/NPC trade data.

Renders loot trees (from TreasureParser.build_loot_tree) as MediaWiki
trade-table wikitext using the OSRS-style template set.

Output format uses {{TradeRowItem}}, {{TradeRowGroup}}, {{TradeRowChild}},
{{TradeNestedContainer}}, {{TradeNestedLine}} templates.
"""

import re
from copy import deepcopy

from dos2_tools.core.loot import LootNode


# Tables treated as opaque links (not expanded recursively)
EXTERNAL_TABLES = [
    "ST_AllPotions",
    "ST_Ingredients",
    "ST_RareIngredient",
    "ST_Trader_WeaponNormal",
    "ST_Trader_ArmorNormal",
    "ST_Trader_ClothArmor",
]

MAX_SIMULATION_LEVEL = 16


class TradeTableRenderer:
    """
    Renders loot tree nodes as MediaWiki trade table wikitext.

    Faithfully ports the OSRSWikiExporter extraction and rendering logic
    from the old generate_wiki_trade.py, adapted for the canonical LootNode
    structure (flat children list instead of Pool nodes).

    Key rendering rules:
    - Guaranteed items (100% chance) are hoisted and rendered first.
    - Gold entries are extracted and rendered via {{TradeTraderGold}}.
    - Pools that select from multiple items become TradeRowGroup/TradeRowChild.
    - Complex nested structures use TradeNestedContainer/TradeNestedLine.
    """

    def __init__(self, localization=None):
        self._uid_counter = 0
        self.seen_identifiers = set()
        self.has_rendered_gold = False
        self.loc = localization

    def reset(self):
        """Reset renderer state for reuse across levels."""
        self._uid_counter = 0
        self.seen_identifiers = set()

    def get_uid(self):
        self._uid_counter += 1
        return f"group_{self._uid_counter}"

    # ─── Name Helpers ────────────────────────────────────────────────────────

    def clean_label(self, text):
        """Strip internal prefixes and format for display."""
        if not text:
            return ""
        text = re.sub(r"^(ST_|I_)", "", text)
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        return text.replace("_", " ").strip()

    def resolve_name_link(self, raw_name):
        """Convert a raw item/category name to a [[wiki link]]."""
        if not raw_name:
            return ""

        clean_internal = raw_name
        if clean_internal.startswith("I_"):
            clean_internal = clean_internal[2:]

        if self.loc:
            display = self.loc.get_text(clean_internal)
            if display:
                safe = display.replace("_", " ").strip()
                return f"[[{safe}]]"

        return self.clean_label(raw_name)

    def get_qty_display(self, node, override=None):
        """Format quantity display string."""
        if override is not None:
            return str(override)
        if node.type in ("Item", "Link", "Category"):
            # Leaf nodes: always display as 1 unless explicitly set
            if node.min_qty == 1 and node.max_qty == 1:
                return "1"
        if node.min_qty == node.max_qty:
            return str(node.min_qty)
        return f"{node.min_qty}-{node.max_qty}"

    # ─── Extraction Helpers ─────────────────────────────────────────────────

    def extract_trader_gold(self, node, multiplier=1):
        """
        Find and remove gold entries from the tree. Returns display qty string.

        Mutates `node` in place (on a deepcopy). Returns None if no gold found.
        """
        found_gold = None

        for child in list(node.children):
            clean = self.clean_label(child.name)
            is_gold = clean in ("Trader Gold", "Gold", "TraderGold")

            if child.type in ("Table", "Pool"):
                res = self.extract_trader_gold(child, multiplier)
                if res:
                    found_gold = res
            elif is_gold:
                qty = self.get_qty_display(child, multiplier)
                found_gold = qty
                node.children.remove(child)

        return found_gold

    def extract_guaranteed(self, node, multiplier=1):
        """
        Find and remove guaranteed (100% chance) leaf items.

        Returns list of {'node': LootNode, 'qty': int} dicts.
        Mutates `node` in place (on a deepcopy).
        """
        extracted = []

        for child in list(node.children):
            if child.chance >= 0.99:
                if child.type == "Item":
                    extracted.append({"node": child, "qty": multiplier})
                    node.children.remove(child)
                elif child.type in ("Table", "Pool"):
                    sub = self.extract_guaranteed(child, multiplier * child.min_qty)
                    extracted.extend(sub)
                    if not child.children:
                        node.children.remove(child)

        return extracted

    # ─── Rendering ───────────────────────────────────────────────────────────

    def render_level_block(self, node, level):
        """
        Render per-level wikitext block for a merged trade tree.

        Returns None if nothing to render.
        """
        if not node:
            return None

        node_copy = deepcopy(node)

        # Extract gold
        raw_gold_qty = self.extract_trader_gold(node_copy)
        display_gold_qty = None
        if raw_gold_qty and not self.has_rendered_gold:
            display_gold_qty = raw_gold_qty
            self.has_rendered_gold = True

        # Extract guaranteed items
        guaranteed_items = self.extract_guaranteed(node_copy)
        guaranteed_rows = []
        for entry in guaranteed_items:
            row = self.render_row(entry["node"], qty_override=entry["qty"],
                                  force_rarity="Always")
            if row:
                guaranteed_rows.append(row)

        # Remaining random drops
        pool_rows = []
        # Sort by chance descending
        for child in sorted(node_copy.children, key=lambda x: x.chance, reverse=True):
            row = self.render_row(child)
            if row:
                pool_rows.append(row)

        if not guaranteed_rows and not pool_rows and not display_gold_qty:
            return None

        output = []
        header_text = f"Stock (Level {level})" if level == 1 else f"New at Level {level}"
        output.append(f"=={header_text}==")

        if display_gold_qty:
            output.append(f"{{{{TradeTraderGold|quantity={display_gold_qty}}}}}")
            output.append("")

        if guaranteed_rows:
            output.append("{{TradeTableHead}}")
            output.extend(guaranteed_rows)
            output.append("{{TradeTableBottom}}")
            output.append("")

        if pool_rows:
            output.append(f"==={header_text} (Random)===")
            for row in pool_rows:
                output.append("{{TradePoolHead}}")
                output.append(row)
                output.append("{{TradeTableBottom}}")

        return "\n".join(output)

    def render_row(self, node, qty_override=None, force_rarity=None):
        """
        Render a single loot node as a trade row, with possible children.

        Returns the wikitext string, or None if the node should be skipped.
        """
        # Pool: unwrap to children, applying pool-level chance/qty
        if node.type == "Pool":
            pool_chance = node.chance
            pool_qty = node.min_qty
            rows = []
            for child in sorted(node.children, key=lambda x: x.chance, reverse=True):
                # Scale child chance by this pool's selection chance
                child_eff_chance = child.chance * pool_chance
                # Temporarily set chance for qty/rarity computation
                orig_chance = child.chance
                child.chance = child_eff_chance
                row = self.render_row(child, qty_override=pool_qty if pool_qty > 1 else qty_override)
                child.chance = orig_chance
                if row:
                    rows.append(row)
            return "\n".join(rows) if rows else None

        # Deduplicate simple items/links
        if node.type in ("Item", "Link", "InvalidItem"):
            if node.name in self.seen_identifiers:
                return None
            self.seen_identifiers.add(node.name)

        qty = self.get_qty_display(node, qty_override)
        rarity = force_rarity or (
            "100%" if node.chance > 0.99 else f"{node.chance:.1%}"
        )

        # Simple item
        if node.type in ("Item", "Link", "InvalidItem"):
            name = self.resolve_name_link(node.name)
            return f"{{{{TradeRowItem|name={name}|quantity={qty}|rarity={rarity}}}}}"

        # Category: expands to items
        # If the category name starts with T_ and has no items, it's a table reference
        # mistakenly stored as a Category by the parser — render as a table link.
        if node.type == "Category" and node.name.startswith("T_") and not node.items:
            link_name = node.name[2:]  # strip T_ prefix
            if link_name not in self.seen_identifiers:
                self.seen_identifiers.add(link_name)
                return f"{{{{TradeRowItem|name=[[T_{link_name}]]|quantity={qty}|rarity={rarity}}}}}"
            return None

        if node.type == "Category":
            name = (
                f"<span style='color:#a87b00; font-weight:bold;'>[CAT]</span> "
                f"{self.clean_label(node.name)}"
            )
            children_data = []
            for item_node in node.items:
                if item_node.name not in self.seen_identifiers:
                    self.seen_identifiers.add(item_node.name)
                    display = self.resolve_name_link(item_node.name)
                    children_data.append({
                        "name": display,
                        "qty": "1",
                        "rar": f"{item_node.chance:.1%}" if hasattr(item_node, 'chance') else "100%",
                    })

            if not children_data:
                return None

            uid = self.get_uid()
            out = [
                f"{{{{TradeRowGroup|id={uid}|name={name}|quantity={qty}|rarity={rarity}}}}}"
            ]
            for c in children_data:
                out.append(
                    f"{{{{TradeRowChild|id={uid}|name={c['name']}"
                    f"|quantity={c['qty']}|rarity={c['rar']}}}}}"
                )
            return "\n".join(out)

        # Table: render immediate children as sub-rows
        if node.type in ("Table", "Table_Cycle"):
            name = f"'''{self.clean_label(node.name)}'''"
            children_data = []

            for child in sorted(node.children, key=lambda x: x.chance, reverse=True):
                if child.type in ("Table", "Table_Cycle", "Category"):
                    deep_tmpl = self._render_deep_container(child)
                    if deep_tmpl:
                        children_data.append({
                            "name": deep_tmpl,
                            "qty": "1",
                            "rar": f"{child.chance:.1%}",
                        })
                else:
                    if child.name not in self.seen_identifiers:
                        self.seen_identifiers.add(child.name)
                        k_name = self.resolve_name_link(child.name)
                        k_qty = self.get_qty_display(child)
                        children_data.append({
                            "name": k_name,
                            "qty": k_qty,
                            "rar": f"{child.chance:.1%}",
                        })

            if not children_data:
                return None

            uid = self.get_uid()
            out = [
                f"{{{{TradeRowGroup|id={uid}|name={name}|quantity={qty}|rarity={rarity}}}}}"
            ]
            for c in children_data:
                out.append(
                    f"{{{{TradeRowChild|id={uid}|name={c['name']}"
                    f"|quantity={c['qty']}|rarity={c['rar']}}}}}"
                )
            return "\n".join(out)

        return None

    def _render_deep_container(self, node):
        """
        Render a complex nested node as a {{TradeNestedContainer}} block.

        Used when a complex item is deep inside a structure.
        """
        lines = []

        if node.type == "Category" and node.items:
            for item_node in node.items:
                if item_node.name not in self.seen_identifiers:
                    self.seen_identifiers.add(item_node.name)
                    display = self.resolve_name_link(item_node.name)
                    rar = f"{item_node.chance:.1%}" if hasattr(item_node, 'chance') else "100%"
                    lines.append(
                        f"{{{{TradeNestedLine|name={display}|quantity=1|rarity={rar}}}}}"
                    )

        elif node.type in ("Table", "Table_Cycle") and node.children:
            for child in sorted(node.children, key=lambda x: x.chance, reverse=True):
                if child.name in self.seen_identifiers:
                    continue
                self.seen_identifiers.add(child.name)

                k_name = self.clean_label(child.name)
                if child.type == "Item":
                    k_name = self.resolve_name_link(child.name)
                elif child.type == "Link":
                    k_name = f"[[{child.name}]]"
                elif child.type in ("Table", "Category"):
                    k_name = f"'''{k_name}''' (Group)"

                k_qty = self.get_qty_display(child)
                k_chance = f"{child.chance:.1%}"
                lines.append(
                    f"{{{{TradeNestedLine|name={k_name}|quantity={k_qty}|rarity={k_chance}}}}}"
                )

        if not lines:
            return ""

        content_block = "".join(lines)
        return (
            f"{{{{TradeNestedContainer|name={self.clean_label(node.name)}"
            f"|content={content_block}}}}}"
        )

    # ─── Full Table Rendering ────────────────────────────────────────────────

    def render_full_trader_page(self, loot_engine, trade_ids, npc_name="Trader"):
        """
        Render a complete per-level trade table for an NPC.

        Runs the simulation for all levels 1-MAX and renders each level
        block only if the inventory differs from the previous level.

        Args:
            loot_engine: TreasureParser with loaded tables
            trade_ids: List of treasure table IDs for this NPC
            npc_name: Display name for headers

        Returns:
            str: Complete wikitext for the trade page
        """
        if not trade_ids:
            return ""

        output_blocks = []

        for lvl in range(1, MAX_SIMULATION_LEVEL + 1):
            self.reset()
            master = LootNode("Master_Merged", "Table")

            for trade_id in trade_ids:
                root = loot_engine.build_loot_tree(trade_id, lvl)
                if root:
                    master.children.extend(root.children)

            block = self.render_level_block(master, lvl)
            if block:
                output_blocks.append(block)

        return "\n\n".join(output_blocks)
