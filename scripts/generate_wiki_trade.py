"""
Generate wiki trade tables for DOS2 NPC vendors.

Thin CLI using GameData() + TradeTableRenderer.

Usage:
    python3 -m dos2_tools.scripts.generate_wiki_trade "Kalias"
    python3 -m dos2_tools.scripts.generate_wiki_trade "Rezik" --outdir trade_pages
    python3 -m dos2_tools.scripts.generate_wiki_trade "Gareth" --trade-ids ST_Gareth_A ST_Gareth_B
"""

import os
import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.core.data_models import LSJNode
from dos2_tools.wiki.trade import TradeTableRenderer


def find_npc_trade_ids(npc_name, game_data):
    """
    Scan level character files to find TradeTreasures for a named NPC.

    Returns a sorted list of unique trade table IDs.
    """
    char_files = game_data.get_file_paths("level_characters")
    loc = game_data.localization
    found = []

    print(f"Scanning level files for '{npc_name}'...")
    for f_path in char_files:
        if "Test" in f_path or "Develop" in f_path:
            continue

        from dos2_tools.core.parsers import parse_lsj_templates
        _, objects = parse_lsj_templates(f_path)

        for _, obj_data in objects.items():
            node = LSJNode(obj_data)
            handle = node.get_handle("DisplayName")
            display_name = loc.get_handle_text(handle) if handle else None
            if not display_name:
                display_name = node.get_value("DisplayName") or ""

            if npc_name.lower() in display_name.lower():
                trade_list = obj_data.get("TradeTreasures", [])
                if isinstance(trade_list, list):
                    for entry in trade_list:
                        if isinstance(entry, dict):
                            val = entry.get("value") or entry.get("Object")
                            if val:
                                found.append(val)
                        elif isinstance(entry, str):
                            found.append(entry)
                elif isinstance(trade_list, str):
                    found.append(trade_list)

    unique_ids = sorted(set(x for x in found if x))
    print(f"  Found trade IDs: {unique_ids}")
    return unique_ids


def main():
    parser = argparse.ArgumentParser(
        description="Generate wiki trade table for a DOS2 NPC vendor"
    )
    parser.add_argument(
        "npc_name", nargs="?",
        help="NPC display name to search for (e.g. 'Kalias')"
    )
    parser.add_argument(
        "--trade-ids", nargs="+",
        help="Explicit treasure table IDs (bypasses NPC name search)"
    )
    parser.add_argument(
        "--outdir", default=".",
        help="Output directory for generated wikitext files"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    if not args.npc_name and not args.trade_ids:
        parser.error("Either npc_name or --trade-ids is required")

    os.makedirs(args.outdir, exist_ok=True)
    game = GameData(refresh_loc=args.refresh_loc)

    if args.trade_ids:
        trade_ids = args.trade_ids
        npc_name = args.npc_name or "Trader"
    else:
        npc_name = args.npc_name
        trade_ids = find_npc_trade_ids(npc_name, game)

    if not trade_ids:
        print(f"No trade IDs found for '{npc_name}'.")
        return

    print(f"Generating merged table for: {trade_ids}")
    renderer = TradeTableRenderer(localization=game.localization)
    wikitext = renderer.render_full_trader_page(game.loot_engine, trade_ids, npc_name)

    if not wikitext:
        print("No output generated (all levels empty).")
        return

    safe_name = npc_name.replace(" ", "_")
    fname = f"{safe_name}_Trade.wikitext"
    path = os.path.join(args.outdir, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(wikitext)

    print(f"Done: {path}")


if __name__ == "__main__":
    main()
