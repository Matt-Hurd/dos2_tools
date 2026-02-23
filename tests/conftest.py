"""
Shared fixtures for dos2_tools tests.

Provides both:
  - Tiny in-memory fixtures for fast unit tests
  - Paths to real extracted game files for integration tests
"""

import os
import pytest


# ─── Repository root ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def repo_root():
    """Absolute path to the dos2 workspace root (contains exported/, pytest.ini, etc.)."""
    # tests/ → dos2_tools/ → dos2/
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(tests_dir, "..", ".."))


@pytest.fixture(scope="session")
def exported_dir(repo_root):
    """Path to the exported/ game data directory."""
    return os.path.join(repo_root, "exported")


# ─── Real file paths (integration) ──────────────────────────────────────────

@pytest.fixture(scope="session")
def real_armor_txt(exported_dir):
    """Path to a real Armor.txt stats file (Shared layer)."""
    return os.path.join(
        exported_dir,
        "Shared", "Public", "Shared", "Stats", "Generated", "Data", "Armor.txt"
    )


@pytest.fixture(scope="session")
def real_treasure_table_txt(exported_dir):
    """Path to a real TreasureTable.txt (Origins layer)."""
    return os.path.join(
        exported_dir,
        "Origins", "Public",
        "DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4",
        "Stats", "Generated", "TreasureTable.txt"
    )


@pytest.fixture(scope="session")
def real_file_index(repo_root):
    """
    Version-aware file index built from the real exported/ directory.

    Uses the on-disk cache (cache_file_index.json) so this is fast enough
    to run as a session-scoped fixture even though the data volume is large.
    """
    from dos2_tools.core.file_system import resolve_load_order
    cache = os.path.join(repo_root, "cache_file_index.json")
    return resolve_load_order(
        os.path.join(repo_root, "exported"),
        cache_file=cache if os.path.exists(cache) else None,
    )


@pytest.fixture(scope="session")
def real_game_data(repo_root):
    """
    Full GameData instance loaded from real extracted files.

    Session-scoped so we pay the startup cost only once.
    Expects to be run from the repo root directory (where cache files live).
    """
    os.chdir(repo_root)
    from dos2_tools.core.game_data import GameData
    return GameData()


# ─── Tiny in-memory fixtures (unit tests) ───────────────────────────────────

TINY_ARMOR_TXT = """\
new entry "_BaseArmor"
type "Armor"
data "Slot" "Breast"
data "Value" "10"

new entry "ARM_Child"
type "Armor"
using "_BaseArmor"
data "Value" "20"
data "ObjectCategory" "ClothUpperBody"
data "MinLevel" "3"

new entry "ARM_MultiCat"
type "Armor"
using "_BaseArmor"
data "ObjectCategory" "ClothUpperBody;LeatherUpperBody"
data "MinLevel" "1"
"""

TINY_TREASURE_TXT = """\
new treasuretable "TinyTable"
new subtable "1,1"
object category "ClothUpperBody",5
new "SubTable_A",3

new treasuretable "SubTable_A"
new subtable "1,3;0,3"
new "I_SomeItem",1
"""

TINY_TREASURE_CYCLE_TXT = """\
new treasuretable "CycleA"
new subtable "1,1"
new "CycleB",1

new treasuretable "CycleB"
new subtable "1,1"
new "CycleA",1
"""

TINY_TREASURE_LEVEL_TXT = """\
new treasuretable "LevelTable"
new subtable "1,1"
StartLevel "5"
new "HighLevelItem",1
EndLevel "10"
new "MidItem",1
new "I_AlwaysItem",1
"""


@pytest.fixture
def tiny_raw_stats():
    """Small raw_stats dict suitable for stats engine tests (no file I/O)."""
    from collections import OrderedDict
    return {
        "_BaseArmor": {
            "_id": "_BaseArmor",
            "_type": "Armor",
            "_data": OrderedDict([("Slot", "Breast"), ("Value", "10")]),
        },
        "ARM_Child": {
            "_id": "ARM_Child",
            "_type": "Armor",
            "_using": "_BaseArmor",
            "_data": OrderedDict([("Value", "20"), ("ObjectCategory", "ClothUpperBody"), ("MinLevel", "3")]),
        },
        "ARM_MultiCat": {
            "_id": "ARM_MultiCat",
            "_type": "Armor",
            "_using": "_BaseArmor",
            "_data": OrderedDict([("ObjectCategory", "ClothUpperBody;LeatherUpperBody"), ("MinLevel", "1")]),
        },
    }


@pytest.fixture
def tiny_resolved_stats(tiny_raw_stats):
    """Fully resolved stats (inheritance applied) built from tiny_raw_stats."""
    from dos2_tools.core.stats_engine import resolve_all_stats
    return resolve_all_stats(tiny_raw_stats)


@pytest.fixture
def tiny_stats_manager(tiny_resolved_stats):
    """StatsManager built from tiny resolved stats."""
    from dos2_tools.core.loot import StatsManager
    return StatsManager(tiny_resolved_stats)


@pytest.fixture
def tiny_parser():
    """TreasureParser loaded with TINY_TREASURE_TXT (no stats manager)."""
    from dos2_tools.core.loot import TreasureParser
    p = TreasureParser()
    p.load_data(TINY_TREASURE_TXT)
    return p


@pytest.fixture
def tiny_parser_with_stats(tiny_stats_manager):
    """TreasureParser loaded with TINY_TREASURE_TXT + stats manager."""
    from dos2_tools.core.loot import TreasureParser
    p = TreasureParser(tiny_stats_manager)
    p.load_data(TINY_TREASURE_TXT)
    return p
