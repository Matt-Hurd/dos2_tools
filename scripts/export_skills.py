"""
Export skill stub wiki pages.

Thin CLI using GameData(). Ported from export_skills.py.
Writes one .wikitext file per unique skill with an InfoboxSkill template stub.

Usage:
    python3 -m dos2_tools.scripts.export_skills
    python3 -m dos2_tools.scripts.export_skills --outdir skill_wikitext
"""

import os
import argparse

from dos2_tools.core.game_data import GameData


def main():
    parser = argparse.ArgumentParser(
        description="Export skill stub wiki pages"
    )
    parser.add_argument(
        "--outdir", default="skill_wikitext",
        help="Output directory for .wikitext files"
    )
    parser.add_argument(
        "--refresh-loc", action="store_true",
        help="Force rebuild of localization cache"
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    game = GameData(refresh_loc=args.refresh_loc)
    loc = game.localization

    # Filter to skill stats entries
    skill_stats = {
        k: v for k, v in game.stats.items()
        if v.get("_type", "").lower() in ("skill", "skilldata")
        or "DisplayName" in v
        and v.get("_type", "") not in ("Object", "Armor", "Weapon", "Shield")
    }

    count = 0
    seen_names = set()

    for skill_id, data in sorted(skill_stats.items()):
        raw_dn = data.get("DisplayName")
        if not raw_dn:
            continue

        # Try resolving via localization
        name = loc.get_text(raw_dn)
        if not name:
            continue

        safe_name = name.strip()
        if not safe_name or safe_name in seen_names:
            continue
        seen_names.add(safe_name)

        content = f"{{{{InfoboxSkill|skill_id={skill_id}}}}}\n\n"
        content += f"{{{{SkillFooter|skill_id={skill_id}}}}}\n"

        path = os.path.join(args.outdir, f"{safe_name}.wikitext")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        count += 1

    print(f"Generated {count} skill pages in {args.outdir}/")


if __name__ == "__main__":
    main()
