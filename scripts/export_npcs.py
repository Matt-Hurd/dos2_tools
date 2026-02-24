"""
Export NPC wiki pages: infobox data, skills, trades, loot, inventory.

Thin CLI using GameData(). Ported from export_npcs.py.
Groups NPCs by display name, clusters instances into variants by their
stat signature (stats_id, level, equipment, skills, loot, trade, tags),
and writes one .wikitext file per unique NPC name.

Usage:
    python3 -m dos2_tools.scripts.export_npcs
    python3 -m dos2_tools.scripts.export_npcs --outdir npc_wikitext
"""

import os
import re
import argparse
from collections import defaultdict
from copy import deepcopy

from dos2_tools.core.game_data import GameData
from dos2_tools.core.formatters import sanitize_filename
from dos2_tools.core.parsers import parse_lsj_templates, get_region_name



# NPC stat fields rendered in the wiki infobox
STAT_FIELDS = [
    "Strength", "Finesse", "Intelligence", "Constitution", "Memory", "Wits",
    "Vitality", "MagicPoints", "Armor", "MagicArmor",
    "APMaximum", "APStart", "APRecovery",
    "FireResistance", "EarthResistance", "WaterResistance", "AirResistance",
    "PoisonResistance", "PhysicalResistance", "PiercingResistance",
    "Initiative", "Movement", "CriticalChance", "Dodge", "Accuracy", "Talents",
]


# ── Parse helpers ──────────────────────────────────────────────────────────────

def parse_conditions(condition_list):
    """Convert raw condition list to human-readable string."""
    if not condition_list:
        return ""
    conditions = []
    for cond in condition_list:
        if not isinstance(cond, dict):
            continue
        if cond.get("HasNoPhysicalArmor", {}).get("value") is True:
            conditions.append("No Physical Armor")
        if cond.get("HasNoMagicalArmor", {}).get("value") is True:
            conditions.append("No Magic Armor")
        min_hp = cond.get("MinimumHealthPercentage", {}).get("value", 0)
        max_hp = cond.get("MaximumHealthPercentage", {}).get("value", 100)
        if min_hp > 0 and max_hp < 100:
            conditions.append(f"HP {min_hp}-{max_hp}%")
        elif min_hp > 0:
            conditions.append(f"HP > {min_hp}%")
        elif max_hp < 100:
            conditions.append(f"HP < {max_hp}%")
    return ";".join(conditions)


def parse_skills(skill_list_node):
    """Parse the SkillList node into a list of skill info dicts."""
    parsed = []
    if not skill_list_node:
        return parsed
    for entry in skill_list_node:
        inner = entry.get("Skill", [])
        if not isinstance(inner, list):
            inner = [inner]
        for skill in inner:
            skill_id = skill.get("Skill", {}).get("value")
            if not skill_id:
                continue
            modes = []
            if skill.get("CasualExplorer", {}).get("value") is True:
                modes.append("Explorer")
            if skill.get("Classic", {}).get("value") is True:
                modes.append("Classic")
            if skill.get("TacticianHardcore", {}).get("value") is True:
                modes.append("Tactician")
            if skill.get("HonorHardcore", {}).get("value") is True:
                modes.append("Honor")
            if len(modes) == 4:
                modes = []
            source_cond = parse_conditions(skill.get("SourceConditions", []))
            target_cond = parse_conditions(skill.get("TargetConditions", []))
            cond_str = ""
            if source_cond:
                cond_str += f"Self: {source_cond}"
            if target_cond:
                if cond_str:
                    cond_str += " | "
                cond_str += f"Target: {target_cond}"
            parsed.append({
                "id": skill_id,
                "modes": ";".join(modes),
                "score": skill.get("ScoreModifier", {}).get("value", 1.0),
                "start_round": skill.get("StartRound", {}).get("value", 0),
                "conditions": cond_str,
                "aiflags": skill.get("AIFlags", {}).get("value", 0),
            })
    return parsed


def parse_tags(data):
    """Extract semicolon-separated sorted tag IDs."""
    tags = []
    tag_root = data.get("Tags", [])
    if not isinstance(tag_root, list):
        return ""
    for entry in tag_root:
        inner = entry.get("Tag", [])
        if not isinstance(inner, list):
            inner = [inner]
        for t in inner:
            val = t.get("Object", {}).get("value")
            if val:
                tags.append(val)
    return ";".join(sorted(set(tags)))


def parse_trade_treasures(data):
    """Return semicolon-joined TradeTreasures list."""
    tt_root = data.get("TradeTreasures", [])
    if not isinstance(tt_root, list):
        return ""
    return ";".join(tt_root)


def parse_inventory_items(item_list_root, templates_by_mapkey, loc):
    """Parse ItemList into (display_name, amount) pairs."""
    items_found = []
    if not item_list_root:
        return items_found
    for item_entry in item_list_root:
        items = item_entry.get("Item", [])
        if not isinstance(items, list):
            items = [items]
        for item in items:
            t_uuid = item.get("TemplateID", {}).get("value")
            stats_id = item.get("ItemName", {}).get("value")
            amount = item.get("Amount", {}).get("value", 1)
            # Try template display name first
            name = None
            if t_uuid and t_uuid in templates_by_mapkey:
                rt = templates_by_mapkey[t_uuid]
                dn = rt.get("DisplayName")
                if isinstance(dn, dict):
                    handle = dn.get("handle")
                    if handle:
                        name = loc.get_handle_text(handle)
                    if not name:
                        name = dn.get("value")
            if not name and stats_id:
                name = loc.get_text(stats_id) or stats_id
            if name:
                items_found.append((name, amount))
    return items_found



def get_variant_signature(data):
    """Produce a hashable signature for deduplication of NPC variants."""
    stats = data.get("Stats", "Unknown")
    level = data.get("LevelOverride", {}).get("value", 0)
    dead = data.get("DefaultState", False)
    equip = "None"
    eq_node = data.get("Equipment", {})
    if isinstance(eq_node, dict):
        equip = eq_node.get("value", "None")
    skills = parse_skills(data.get("SkillList", []))
    skill_sig = "|".join(sorted(s["id"] for s in skills))
    loot = "None"
    treasures = data.get("Treasures", [])
    if treasures and isinstance(treasures, list):
        loot = ";".join(sorted(treasures))
    if loot == "Empty":
        loot = ""
    trade = parse_trade_treasures(data)
    if trade == "Empty":
        trade = ""
    tags = parse_tags(data)
    return (stats, level, equip, skill_sig, loot, trade, tags, dead)


def clean_label_string(text):
    """Strip common noisy prefixes from variant labels."""
    text = text.replace("_", " ")
    noise_patterns = [
        r"^(?:WPN|ARM|EQ|RC|FTJ|ARX|LV|TUT)\b",
        r"^(?:Humans?|Lizards?|Elves|Dwarves|Undead)\b",
        r"^(?:Ranged|Melee|Magic)\b",
        r"^(?:Common|Uncommon|Rare|Legendary|Divine|Unique)\b",
    ]
    current = text
    while True:
        prev = current
        for p in noise_patterns:
            current = re.sub(p, "", current, flags=re.IGNORECASE).strip()
        if current == prev:
            break
    current = re.sub(r"\s+[A-Z]$", "", current)
    current = re.sub(r"\s+\d+$", "", current)
    return current if current else text


def generate_variant_label(sig, all_sigs):
    """Choose a short human-readable label for this variant."""
    stats, level, equip, skill_sig, loot, trade, tags, dead = sig
    if len(all_sigs) == 1:
        return "Standard"
    labels = []
    levels = set(s[1] for s in all_sigs)
    if len(levels) > 1:
        labels.append(f"Lvl {level}")
    equips = set(s[2] for s in all_sigs)
    if len(equips) > 1:
        labels.append(clean_label_string(equip))
    stat_ids = set(s[0] for s in all_sigs)
    if len(stat_ids) > 1:
        clean_stat = clean_label_string(stats)
        if clean_stat not in " ".join(labels):
            labels.append(clean_stat)
    if not labels:
        return f"Variant {all_sigs.index(sig) + 1}"
    return " - ".join(labels)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Export NPC wiki pages"
    )
    parser.add_argument(
        "--outdir", default="npc_wikitext",
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
    char_stats = {
        k: v for k, v in game.stats.items()
        if v.get("_type", "").lower() in ("character", "creature")
    }
    templates_by_mapkey = game.templates_by_mapkey

    print("Loading characters from level files...")
    char_files = game.get_file_paths("level_characters")
    grouped_npcs = defaultdict(list)

    for f_path in char_files:
        if "Test" in f_path or "Develop" in f_path:
            continue
        _, level_objects = parse_lsj_templates(f_path)
        region_name = get_region_name(f_path)

        for obj_uuid, level_data in level_objects.items():
            template_uuid = level_data.get("TemplateName")
            final_data = {}
            if template_uuid and template_uuid in templates_by_mapkey:
                final_data = deepcopy(templates_by_mapkey[template_uuid])
            final_data.update(level_data)

            # Resolve display name
            dn_node = final_data.get("DisplayName")
            final_name = None
            if isinstance(dn_node, dict):
                handle = dn_node.get("handle")
                if handle:
                    final_name = loc.get_handle_text(handle)
                if not final_name:
                    val = dn_node.get("value")
                    if val:
                        final_name = loc.get_text(val) or val

            if not final_name:
                continue

            final_data["_REGION"] = region_name
            final_data["_INVENTORY"] = parse_inventory_items(
                final_data.get("ItemList", []), templates_by_mapkey, loc
            )
            grouped_npcs[final_name].append(final_data)

    print(f"Grouped into {len(grouped_npcs)} unique NPC names.")

    for name, instances in grouped_npcs.items():
        safe_name = sanitize_filename(name)
        if not safe_name:
            continue

        variants = defaultdict(list)
        for inst in instances:
            sig = get_variant_signature(inst)
            variants[sig].append(inst)

        all_sigs = list(variants.keys())
        output_lines = ['<div style="display:none;">']

        loot_map = defaultdict(set)
        trade_map = defaultdict(set)
        inventory_set = set()

        for sig, var_instances in variants.items():
            label = generate_variant_label(sig, all_sigs)
            primary = var_instances[0]
            stats_id = primary.get("Stats", "Unknown")
            level_str = primary.get("LevelOverride", {}).get("value", "-1")

            # Coordinates
            coords = []
            for v in var_instances:
                transform = v.get("Transform")
                if isinstance(transform, list) and transform:
                    pos = transform[0].get("Position", {}).get("value", "")
                    if pos:
                        coords.append(f"{pos.replace(' ', ',')},{v.get('_REGION')}")
                for item_name, amount in v.get("_INVENTORY", []):
                    inventory_set.add((item_name, amount))

            _, level_int, _, _, loot, trade, _, _ = sig
            if loot and loot != "Empty":
                for l in loot.split(";"):
                    if l:
                        loot_map[l].add(level_int)
            if trade:
                for t in trade.split(";"):
                    if t:
                        trade_map[t].add(level_int)

            # Skills rendering
            raw_skills = parse_skills(primary.get("SkillList", []))
            skill_lines = []
            for s in raw_skills:
                parts = [f"| skill_id = {s['id']}"]
                if s["modes"]:
                    parts.append(f"| modes = {s['modes']}")
                if s["score"] != 1.0:
                    parts.append(f"| score = {s['score']}")
                if s["start_round"] != 0:
                    parts.append(f"| start_round = {s['start_round']}")
                if s["conditions"]:
                    parts.append(f"| conditions = {s['conditions']}")
                skill_lines.append("\t{{NPC Skill" + "".join(parts) + "}}")

            output_lines.append("")
            output_lines.append("{{NPC Variant")
            output_lines.append(f"| label = {label}")
            output_lines.append(f"| guid = {primary.get('MapKey', '')}")
            output_lines.append(f"| stats_id = {stats_id}")
            output_lines.append(f"| level = {level_str}")
            output_lines.append(f"| icon = {primary.get('Icon', '')}_Icon.webp")
            if primary.get("DefaultState"):
                output_lines.append("| dead = true")

            # Character stats block
            if stats_id in char_stats:
                stat_block = char_stats[stats_id]
                for field in STAT_FIELDS:
                    val = stat_block.get(field) or stat_block.get(field.replace(" ", ""))
                    if val:
                        param = re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()
                        output_lines.append(f"| {param} = {val}")

            output_lines.append(f"| treasure_id = {loot}")
            if trade:
                output_lines.append(f"| trade_treasure_id = {trade}")
            if len(coords) == 1:
                output_lines.append(f"| coordinates = {coords[0]}")
            elif len(coords) > 1:
                output_lines.append(f"| coordinates = {';'.join(coords)}")
            if parse_tags(primary):
                output_lines.append(f"| tags = {parse_tags(primary)}")
            if skill_lines:
                output_lines.append(f"| skills = \n" + "\n".join(skill_lines))
            output_lines.append("}}")

        output_lines.append("</div>")
        output_lines.append("{{InfoboxNPC")
        output_lines.append(f"| name = {name}")
        output_lines.append("}}")

        has_any_skills = any(
            parse_skills(v[0].get("SkillList", []))
            for v in variants.values()
        )
        if has_any_skills:
            output_lines += ["", "== Skills ==", "", "{{NPC Skills}}"]

        output_lines += ["", "== Locations ==", "", "{{LocationTable}}"]

        if trade_map and ";".join(trade_map.keys()) != "Empty":
            output_lines.append("")
            output_lines.append("== Trades ==")
            output_lines.append("")
            output_lines.append(
                f"{{{{NPC Trades|table_ids={';'.join(map(str, trade_map.keys()))}}}}}"
            )

        if loot_map:
            output_lines.append("")
            output_lines.append("== Loot ==")
            for t_id in sorted(loot_map.keys()):
                for lvl in sorted(loot_map[t_id]):
                    output_lines.append("")
                    if lvl > 0:
                        output_lines.append(
                            f"{{{{NPC Loot|table_id={t_id}|level={lvl}}}}}"
                        )
                    else:
                        output_lines.append(f"{{{{NPC Loot|table_id={t_id}}}}}")

        if inventory_set:
            output_lines += ["", "== Inventory =="]
            output_lines.append('{| class="wikitable"')
            output_lines.append("! Item !! Amount")
            output_lines.append("|-")
            for item, amount in sorted(inventory_set, key=lambda x: x[0]):
                output_lines.append(f"| {{{{ SmItemIcon|{item} }}}}")
                output_lines.append(f"| {amount}")
                output_lines.append("|-")
            output_lines.append("|}")

        path = os.path.join(args.outdir, f"{safe_name}.wikitext")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))

    print(f"Generated {len(grouped_npcs)} files in {args.outdir}/")


if __name__ == "__main__":
    main()
