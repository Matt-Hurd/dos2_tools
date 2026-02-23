"""
Find which treasure tables drop a specific item.

Thin CLI using GameData() + TreasureParser.flatten_probabilities().
Debug/query tool: given a stats ID or display name, shows all treasure
tables that can drop it and the probability at a given level.

Usage:
    python3 -m dos2_tools.scripts.find_drops "Source Orb"
    python3 -m dos2_tools.scripts.find_drops LOOT_Source_Orb_000 --level 10
    python3 -m dos2_tools.scripts.find_drops "Lucky Rabbit Paw" --level 5 --min-prob 0.01
"""

import argparse

from dos2_tools.core.game_data import GameData


def main():
    parser = argparse.ArgumentParser(
        description="Find which treasure tables drop a specific item"
    )
    parser.add_argument(
        "item",
        help="Item stats ID or display name to search for"
    )
    parser.add_argument(
        "--level", type=int, default=10,
        help="Player level to simulate (default: 10)"
    )
    parser.add_argument(
        "--min-prob", type=float, default=0.0,
        help="Minimum probability to display (default: 0.0 = all)"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    game = GameData(refresh_loc=args.refresh_loc)
    loot_engine = game.loot_engine
    loc = game.localization

    # Resolve item to stats IDs
    target_ids = set()

    # Direct stats ID match
    if args.item in game.stats:
        target_ids.add(args.item)
        print(f"Searching for: {args.item}")
    else:
        # Try display name match
        for stats_id in game.stats:
            name = game.resolve_display_name(stats_id)
            if name and args.item.lower() in name.lower():
                target_ids.add(stats_id)
        if target_ids:
            print(f"Matching stats IDs: {', '.join(sorted(target_ids))}")
        else:
            print(f"No item found matching '{args.item}'")
            return

    # Search all treasure tables
    results = []

    for table_id in sorted(loot_engine.tables.keys()):
        root = loot_engine.build_loot_tree(table_id, args.level)
        if not root:
            continue

        flat = loot_engine.flatten_probabilities(root)

        for target_id in target_ids:
            if target_id in flat:
                info = flat[target_id]
                if info["prob"] >= args.min_prob:
                    results.append({
                        "table": table_id,
                        "stats_id": target_id,
                        "prob": info["prob"],
                        "min_qty": info["min_qty"],
                        "max_qty": info["max_qty"],
                    })

    if not results:
        print(f"No treasure tables drop this item at level {args.level}.")
        return

    # Sort by probability descending
    results.sort(key=lambda x: x["prob"], reverse=True)

    print(f"\nFound in {len(results)} treasure table(s) at level {args.level}:\n")
    print(f"{'Probability':<14} {'Qty':<10} {'Table ID'}")
    print("-" * 70)
    for r in results:
        qty = (
            f"{r['min_qty']}"
            if r["min_qty"] == r["max_qty"]
            else f"{r['min_qty']}-{r['max_qty']}"
        )
        prob = f"{r['prob']:.2%}"
        print(f"{prob:<14} {qty:<10} {r['table']}")


if __name__ == "__main__":
    main()
