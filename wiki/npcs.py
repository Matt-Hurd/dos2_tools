"""
Wiki page section generators for DOS2 NPCs.

Each function generates one section of a wiki NPC page as wikitext.
Sections can be generated individually or composed into a full page.
"""

import re
from collections import defaultdict

from dos2_tools.core.config import VALID_LEVELS
from dos2_tools.core.data_models import LSJNode
from dos2_tools.core.parsers import parse_lsj_templates
from dos2_tools.wiki.items import get_region_name, format_coordinate, resolve_node_name


# Stats fields to include in NPC stat blocks
NPC_STAT_FIELDS = [
    "Strength", "Finesse", "Intelligence", "Constitution", "Memory", "Wits",
    "Vitality", "MagicArmor", "Armor",
    "FireResistance", "EarthResistance", "WaterResistance", "AirResistance",
    "PoisonResistance", "PhysicalResistance", "PiercingResistance",
    "Initiative", "Movement", "CriticalChance", "Dodge", "Accuracy", "Talents",
]


# ─── Helper Functions ───────────────────────────────────────────────────────

def parse_conditions(condition_list):
    """Parse condition entries from NPC data."""
    if not condition_list:
        return []
    if not isinstance(condition_list, list):
        condition_list = [condition_list]

    return [
        str(LSJNode(cond).get_value("Type", ""))
        for cond in condition_list
    ]


def parse_skills(skill_list_node):
    """Parse skill list from NPC data."""
    node = LSJNode({"SkillList": skill_list_node})
    skills = []
    for entry in node.get_list("SkillList"):
        for skill in entry.get_list("Skill"):
            skill_id = skill.get_value("MapKey")
            if skill_id:
                skills.append(skill_id)
    return skills


def parse_tags(data):
    """Parse tags from NPC data."""
    node = LSJNode(data) if not isinstance(data, LSJNode) else data
    tags = []
    for tag_entry in node.get_list("Tags"):
        value = tag_entry.get_node("Tag").get_node("Object").get_value("MapKey")
        if value:
            tags.append(value)
    return tags


def parse_trade_treasures(data):
    """Extract trade treasure table IDs from NPC data."""
    tts = data.get("TradeTreasures", [])
    if isinstance(tts, list):
        return tts
    return []


def resolve_item_name(template_uuid, stats_id, game_data):
    """Resolve an item name from template UUID or stats ID."""
    if template_uuid:
        rt_data = game_data.templates_by_mapkey.get(template_uuid)
        if rt_data:
            name = resolve_node_name(rt_data, game_data.localization)
            if name:
                return name

    if stats_id:
        return game_data.resolve_display_name(stats_id)

    return None


def parse_inventory_items(item_list_root, game_data):
    """Parse items from an NPC's inventory."""
    if not item_list_root:
        return []

    wrapper = LSJNode({"ItemList": item_list_root})
    items = []
    for item_entry in wrapper.get_list("ItemList"):
        for item in item_entry.get_list("Item"):
            t_uuid = item.get_value("TemplateID")
            stats_id = item.get_value("ItemName")
            name = resolve_item_name(t_uuid, stats_id, game_data)

            items.append({
                "template_uuid": t_uuid,
                "stats_id": stats_id,
                "name": name or stats_id or t_uuid or "Unknown",
            })

    return items


# ─── Section Generators ────────────────────────────────────────────────────

def generate_infobox(npc_name, stats_id=None, region=None,
                     level_override=None, template="InfoboxNPC"):
    """Generate the NPC infobox."""
    content = f"{{{{{template}\n|name={npc_name}"

    if stats_id:
        content += f"\n|stats_id={stats_id}"
    if region:
        content += f"\n|region={region}"
    if level_override:
        content += f"\n|level={level_override}"

    content += "\n}}\n"
    return content


def generate_stats_section(stats_id, game_data):
    """Generate the stats section for an NPC."""
    if not stats_id:
        return ""

    stats = game_data.stats.get(stats_id)
    if not stats:
        return ""

    content = "\n== Stats ==\n"
    content += "{{NPCStats\n"

    for field in NPC_STAT_FIELDS:
        val = stats.get(field)
        if val and val != "0":
            content += f"|{field.lower()}={val}\n"

    content += "}}\n"
    return content


def generate_skills_section(skills):
    """Generate the skills section for an NPC."""
    if not skills:
        return ""

    content = "\n== Skills ==\n"
    for skill in sorted(skills):
        # Strip common prefixes for display
        display = skill
        for prefix in ("Shout_", "Target_", "Projectile_", "Zone_", "Jump_"):
            if display.startswith(prefix):
                display = display[len(prefix):]
                break
        content += f"* [[{display}]] ({skill})\n"

    return content


def generate_inventory_section(inventory_items):
    """Generate the inventory section for an NPC."""
    if not inventory_items:
        return ""

    content = "\n== Inventory ==\n"
    for item in inventory_items:
        name = item.get("name", "Unknown")
        content += f"* [[{name}]]\n"

    return content


def generate_trade_section(trade_treasures, game_data):
    """
    Generate the trade section for an NPC.

    Shows what treasure tables the NPC's vendor inventory draws from.
    """
    if not trade_treasures:
        return ""

    content = "\n== Trade ==\n"
    for tt_id in trade_treasures:
        content += f"* Treasure Table: {tt_id}\n"

    return content


# ─── Full Page Generator ───────────────────────────────────────────────────

def generate_full_page(npc_data, game_data, sections=None):
    """
    Generate a complete wiki page for an NPC.

    Args:
        npc_data: Dict with NPC information
        game_data: GameData instance
        sections: Optional list of section names to include

    Returns:
        str: Complete wikitext for the NPC page
    """
    all_sections = ["infobox", "stats", "skills", "inventory", "trade"]
    if sections is None:
        sections = all_sections

    name = npc_data.get("name", "Unknown")
    stats_id = npc_data.get("stats_id")
    region = npc_data.get("region")

    content = ""

    if "infobox" in sections:
        content += generate_infobox(name, stats_id, region)

    if "stats" in sections:
        content += generate_stats_section(stats_id, game_data)

    if "skills" in sections:
        content += generate_skills_section(npc_data.get("skills", []))

    if "inventory" in sections:
        content += generate_inventory_section(npc_data.get("inventory_items", []))

    if "trade" in sections:
        content += generate_trade_section(
            npc_data.get("trade_treasures", []), game_data
        )

    return content
