"""
Generate external drop table wiki pages for DOS2.

Thin CLI using GameData() + DropTableRenderer with level-range collapsing.

Usage:
    python3 -m dos2_tools.scripts.generate_external_tables
    python3 -m dos2_tools.scripts.generate_external_tables --tables ST_AllPotions ST_Ingredients
    python3 -m dos2_tools.scripts.generate_external_tables --outdir treasure_table_wikitext
"""

import os
import argparse

from dos2_tools.core.game_data import GameData
from dos2_tools.wiki.loot_tables import DropTableRenderer


DEFAULT_TABLES = [
    "ST_AllPotions",
    "ST_Ingredients",
    "ST_RareIngredient",
    "ST_Trader_WeaponNormal",
    "ST_Trader_ArmorNormal",
    "ST_Trader_ClothArmor",
]


def main():
    parser = argparse.ArgumentParser(
        description="Generate external drop table wiki pages for DOS2"
    )
    parser.add_argument(
        "--tables", nargs="+", default=DEFAULT_TABLES,
        help="Treasure table IDs to generate (default: standard external tables)"
    )
    parser.add_argument(
        "--outdir", default="treasure_table_wikitext",
        help="Output directory for generated wikitext files"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    parser.add_argument(
        "--max-level", type=int, default=16,
        help="Maximum level to simulate (default 16)"
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    game = GameData(refresh_loc=args.refresh_loc)

    renderer = DropTableRenderer(localization=game.localization)

    for table_id in args.tables:
        print(f"Processing {table_id}...")

        if table_id not in game.loot_engine.tables:
            print(f"  WARNING: '{table_id}' not found in loaded treasure tables. Skipping.")
            continue

        wikitext = renderer.render_full_drop_table_page(
            game.loot_engine, table_id, max_level=args.max_level
        )

        clean_name = renderer.clean_label(table_id).replace(" ", "_")
        fname = f"{clean_name}_DropTable.wikitext"
        path = os.path.join(args.outdir, fname)

        with open(path, "w", encoding="utf-8") as f:
            f.write(wikitext)

        print(f"  Created: {path}")

    print("Done.")


if __name__ == "__main__":
    main()
