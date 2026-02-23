"""
Wiki loot/drop table renderer for DOS2.

Renders loot trees (from TreasureParser.build_loot_tree) as MediaWiki
drop table wikitext, with level-range collapsing for compact output.

Output format uses {{TradeRowItem}}, {{TradeRowGroup}}, {{TradeRowChild}},
{{TradeNestedContainer}}, {{TradeNestedLine}}, {{TradeTableHead}},
{{TradeTableBottom}} templates.
"""

import re
from copy import deepcopy

from dos2_tools.core.loot import LootNode


MAX_SIMULATION_LEVEL = 16


class DropTableRenderer:
    """
    Renders loot tree nodes as MediaWiki drop table wikitext.

    Faithfully ports the DropTableExporter extraction and rendering logic
    from generate_external_tables.py, adapted for the canonical LootNode
    structure. Key features:

    - Guaranteed items are extracted and rendered first.
    - 100% chance pools are flattened (children become top-level rows).
    - Pools below 100% become TradeRowGroup containers.
    - Categories and complex tables expand inline with TradeRowChild rows.
    - Level ranges are collapsed: adjacent levels with identical table text
      are merged into a single "Level X-Y" block.
    """

    def __init__(self, localization=None):
        self._uid_counter = 0
        self.seen_identifiers = set()
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

    def resolve_name(self, raw_name):
        """Resolve item name to display text (not a wiki link)."""
        if not raw_name:
            return ""
        clean_internal = raw_name
        if clean_internal.startswith("I_"):
            clean_internal = clean_internal[2:]
        if self.loc:
            display = self.loc.get_text(clean_internal)
            if display:
                return display
        return self.clean_label(raw_name)

    def get_qty_display(self, node, override=None):
        """Format quantity display string."""
        if override is not None:
            return str(override)
        min_q = node.min_qty
        max_q = node.max_qty
        if node.type in ("Item", "Link", "Category") and min_q == 1 and max_q == 1:
            return "1"
        if min_q == max_q:
            return str(min_q)
        return f"{min_q}-{max_q}"

    # ─── Extraction ──────────────────────────────────────────────────────────

    def extract_guaranteed(self, node, multiplier=1):
        """
        Extract guaranteed items (100% chance) from the top level.

        Mutates `node` in place. Returns list of {'node': LootNode, 'qty': int}.
        For Table/Pool children that are 100% chance with a single item, recurses.
        """
        extracted = []

        for child in list(node.children):
            if child.chance >= 0.99:
                qty = child.min_qty * multiplier
                if child.type == "Item":
                    extracted.append({"node": child, "qty": qty})
                    node.children.remove(child)
                elif child.type in ("Table", "Pool"):
                    sub = self.extract_guaranteed(child, qty)
                    extracted.extend(sub)
                    if not child.children:
                        node.children.remove(child)

        return extracted

    # ─── Core Row Rendering ──────────────────────────────────────────────────

    def get_table_rows(self, node):
        """
        Render a loot tree node into a sequence of TradeRow wikitext lines.

        Top-level 100% chance children are flattened; below-100% become groups.
        Pool nodes are transparently unwrapped.
        Returns a newline-joined string.
        """
        if not node:
            return ""

        node_copy = deepcopy(node)
        output_lines = []

        # 1. Guaranteed items (extracted and promoted)
        guaranteed = self.extract_guaranteed(node_copy)
        for entry in guaranteed:
            row = self._render_simple_item_row(
                entry["node"], qty_override=entry["qty"], force_rarity="Always"
            )
            if row:
                output_lines.append(row)

        # 2. Unwrap Pool nodes so their children are treated as top-level
        effective_children = []
        for child in node_copy.children:
            if child.type == "Pool":
                # Apply pool-level chance to each child
                for pool_child in child.children:
                    pool_child.chance = pool_child.chance * child.chance
                    pool_child.min_qty = pool_child.min_qty * child.min_qty
                    pool_child.max_qty = pool_child.max_qty * child.max_qty
                    effective_children.append(pool_child)
            else:
                effective_children.append(child)

        # 3. Remaining children
        for child in sorted(effective_children, key=lambda x: x.chance, reverse=True):
            if child.chance >= 0.99:
                # Flatten 100% pool — render children as top-level rows
                row = self._render_promoted_child_row(child, pool_min_qty=child.min_qty)
                if row:
                    output_lines.append(row)
            else:
                # Keep as expandable group
                pool_text = self._render_as_group(child)
                if pool_text:
                    output_lines.append(pool_text)

        return "\n".join(output_lines)

    def _render_simple_item_row(self, node, qty_override=None, force_rarity=None):
        """Render a simple item or link as a TradeRowItem."""
        name = self._get_display_name(node)
        if not name:
            return None
        qty = self.get_qty_display(node, qty_override)
        rarity = force_rarity or (
            "100%" if node.chance > 0.99 else f"{node.chance:.1%}"
        )
        return f"{{{{TradeRowItem|name={name}|quantity={qty}|rarity={rarity}}}}}"

    def _render_promoted_child_row(self, node, pool_min_qty=1):
        """
        Render a node promoted from inside a 100% pool to top level.

        Simple items → TradeRowItem.
        Categories/Tables → TradeRowGroup (expandable).
        """
        name = self._get_display_name(node)
        if not name:
            return None

        qty = self.get_qty_display(node, pool_min_qty)
        rarity = "100%" if node.chance >= 0.99 else f"{node.chance:.1%}"

        is_complex = node.type in ("Category", "Table", "Table_Cycle")
        if is_complex:
            return self._render_standalone_group(node, name, qty, rarity)
        else:
            return f"{{{{TradeRowItem|name={name}|quantity={qty}|rarity={rarity}}}}}"

    def _render_as_group(self, node):
        """Render a below-100% chance node as a TradeRowGroup with children."""
        uid = self.get_uid()
        child_rows = []

        if node.type == "Category":
            for item_node in node.items:
                c_text = self._render_group_child(item_node, parent_uid=uid)
                if c_text:
                    child_rows.append(c_text)

        elif node.type in ("Table", "Table_Cycle"):
            for child in sorted(node.children, key=lambda x: x.chance, reverse=True):
                c_text = self._render_group_child(child, parent_uid=uid)
                if c_text:
                    child_rows.append(c_text)

        elif node.type == "Item":
            return self._render_simple_item_row(node)

        if not child_rows:
            return None

        qty = self.get_qty_display(node)
        chance = f"{node.chance:.1%}"
        name = self._get_display_name(node) or self.clean_label(node.name)

        out = [
            f"{{{{TradeRowGroup|id={uid}|name={name}|quantity={qty}|rarity={chance}}}}}"
        ]
        out.extend(child_rows)
        return "\n".join(out)

    def _render_standalone_group(self, node, name, qty, rarity):
        """
        Render a Category/Table as a top-level TradeRowGroup.

        Iterates the node's items or children to create TradeRowChild rows.
        """
        uid = self.get_uid()
        children_lines = []

        if node.type == "Category" and node.items:
            total_items = len(node.items)
            c_rar = f"{1/total_items:.1%}" if total_items > 0 else "100%"
            for item_node in node.items:
                if item_node.name not in self.seen_identifiers:
                    self.seen_identifiers.add(item_node.name)
                    c_name = f"[[{item_node.name}]]"
                    children_lines.append(
                        f"{{{{TradeRowChild|id={uid}|name={c_name}"
                        f"|quantity=1|rarity={c_rar}}}}}"
                    )

        elif node.type in ("Table", "Table_Cycle") and node.children:
            for child in sorted(node.children, key=lambda x: x.chance, reverse=True):
                c_text = self._render_group_child(child, parent_uid=uid)
                if c_text:
                    children_lines.append(c_text)

        if not children_lines:
            return None

        out = [
            f"{{{{TradeRowGroup|id={uid}|name={name}|quantity={qty}|rarity={rarity}}}}}"
        ]
        out.extend(children_lines)
        return "\n".join(out)

    def _render_group_child(self, node, parent_uid, qty_override=None):
        """
        Render a child row within a group (TradeRowChild).

        For complex children (tables/categories), uses TradeNestedContainer.
        """
        name = self._get_display_name(node)
        if not name:
            return None

        qty = self.get_qty_display(node, qty_override)
        rarity = f"{node.chance:.1%}"

        is_complex = node.type in ("Category", "Table", "Table_Cycle")
        if is_complex:
            nested = self._render_nested_text_block(node)
            if not nested:
                return None
            return (
                f"{{{{TradeRowChild|id={parent_uid}|name={nested}"
                f"|quantity={qty}|rarity={rarity}}}}}"
            )
        else:
            return (
                f"{{{{TradeRowChild|id={parent_uid}|name={name}"
                f"|quantity={qty}|rarity={rarity}}}}}"
            )

    def _render_nested_text_block(self, node):
        """
        Render a complex item deep inside a structure as {{TradeNestedContainer}}.
        """
        lines = []

        if node.type == "Category" and node.items:
            for item_node in node.items:
                if item_node.name not in self.seen_identifiers:
                    self.seen_identifiers.add(item_node.name)
                    display = self.resolve_name(item_node.name)
                    lines.append(
                        f"{{{{TradeNestedLine|name=[[{display}]]|quantity=1|rarity=1 in 1}}}}"
                    )

        elif node.type in ("Table", "Table_Cycle") and node.children:
            for child in sorted(node.children, key=lambda x: x.chance, reverse=True):
                if child.name in self.seen_identifiers:
                    continue
                self.seen_identifiers.add(child.name)

                k_name = self.clean_label(child.name)
                if child.type in ("Link",):
                    k_name = f"[[{child.name}]]"
                elif child.type in ("Table", "Category"):
                    k_name = f"'''{k_name}''' (Group)"

                k_qty = self.get_qty_display(child)
                k_chance = f"{child.chance:.1%}"
                lines.append(
                    f"{{{{TradeNestedLine|name={k_name}|quantity={k_qty}|rarity={k_chance}}}}}"
                )

        if not lines:
            return None

        content = "".join(lines)
        return (
            f"{{{{TradeNestedContainer|name={self.clean_label(node.name)}"
            f"|content={content}}}}}"
        )

    def _get_display_name(self, node):
        """Get display name for a node. Returns None for duplicate items."""
        if node.type in ("Item", "Link", "InvalidItem"):
            if node.name in self.seen_identifiers:
                return None
            self.seen_identifiers.add(node.name)
            if node.type == "Link":
                return f"[[{node.name}]]"
            return self.resolve_name(node.name)

        if node.type == "Category":
            return (
                f"<span style='color:#a87b00; font-weight:bold;'>[CAT]</span> "
                f"{self.clean_label(node.name)}"
            )

        if node.type in ("Table", "Table_Cycle"):
            return f"'''{self.clean_label(node.name)}'''"

        return self.clean_label(node.name) if node.name else None

    # ─── Level-Range Collapsing ──────────────────────────────────────────────

    def render_full_drop_table_page(self, loot_engine, table_id,
                                    max_level=MAX_SIMULATION_LEVEL):
        """
        Render a complete drop table page with level-range collapsing.

        Adjacent levels with identical rendered table rows are merged into
        a single "Level X-Y" block, matching the old generate_external_tables.py
        output format.

        Args:
            loot_engine: TreasureParser with loaded tables
            table_id: The treasure table ID (e.g. "ST_AllPotions")
            max_level: Maximum level to simulate (default 16)

        Returns:
            str: Complete wikitext page including header and footer
        """
        # Step 1: Build trees and snapshots for all levels
        snapshots = []
        for lvl in range(1, max_level + 1):
            root = loot_engine.build_loot_tree(table_id, lvl)
            loot_engine.flatten_wrappers(root)
            snapshots.append({"lvl": lvl, "tree": root})

        # Step 2: Compare per-level rows to find collapse boundaries
        collapsed_ranges = []
        last_rows = None
        start_lvl = 1

        for entry in snapshots:
            self.reset()
            rows = self.get_table_rows(entry["tree"])

            if last_rows is None:
                last_rows = rows
                continue

            if rows != last_rows:
                collapsed_ranges.append({
                    "s": start_lvl,
                    "e": entry["lvl"] - 1,
                    "tree": snapshots[start_lvl - 1]["tree"],
                })
                start_lvl = entry["lvl"]
                last_rows = rows

        # Append final range
        collapsed_ranges.append({
            "s": start_lvl,
            "e": max_level,
            "tree": snapshots[start_lvl - 1]["tree"],
        })

        # Step 3: Render
        clean_name = self.clean_label(table_id)
        final_wikitext = [self._generate_header(table_id, clean_name)]

        for r in collapsed_ranges:
            self.reset()
            rows = self.get_table_rows(r["tree"])
            if not rows:
                continue

            if r["s"] == r["e"]:
                label = f"Level {r['s']}"
            elif r["e"] == max_level:
                label = f"Level {r['s']}+"
            else:
                label = f"Level {r['s']} - {r['e']}"

            final_wikitext.append(f"=== {label} ===")
            final_wikitext.append("{{TradeTableHead}}")
            final_wikitext.append(rows)
            final_wikitext.append("{{TradeTableBottom}}")
            final_wikitext.append("")

        final_wikitext.append(self._generate_footer())
        return "\n".join(final_wikitext)

    @staticmethod
    def _generate_header(table_id, clean_name):
        return (
            f"The '''{clean_name}''', also known as '''{table_id}''' "
            f"is a leveled [[Treasure Table]].\n\n"
            f"=== Drop Table ===\n"
            f"''{{{{Transcludeable}}}}''<onlyinclude>"
        )

    @staticmethod
    def _generate_footer():
        return (
            "</onlyinclude>\n\n"
            "[[Category:Drop tables]]\n"
            "[[Category:Leveled drop tables]]\n"
            "[[Category:Subtables]]"
        )
