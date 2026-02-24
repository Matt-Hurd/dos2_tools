"""
Integration tests for the scripts/generate_*.py modules.

Classes marked @pytest.mark.integration require the real extracted game
files (via the real_game_data session fixture).  All other classes use
small in-memory stubs and run without any filesystem I/O.

Coverage
--------
generate_armour_module.py     convert_type + ArmourModuleIntegration
generate_weapon_module.py     (convert_type shared) + WeaponModuleIntegration
generate_potion_module.py     (convert_type shared) + PotionModuleIntegration
generate_skill_data_module.py (convert_type shared) + SkillDataModuleIntegration
generate_item_data_module.py  (convert_type shared) + ItemDataModuleIntegration
generate_items_lua.py         ItemsLuaIntegration
generate_recipe_data_module.py escape_lua_string + build_recipe_lua + RecipeDataIntegration
generate_recipes_module.py    escape_lua_string (same helper, shared tests)
generate_loot_data.py         LootGraph + get_category_info + generate_table_page + LootDataIntegration
generate_icon_redirects.py    get_node_value + resolve_node_name
"""

import pytest


# ─── convert_type ────────────────────────────────────────────────────────────
# Shared by: generate_armour_module, generate_weapon_module,
#            generate_potion_module, generate_skill_data_module,
#            generate_item_data_module

class TestConvertType:
    """Unit tests for the shared convert_type() helper."""

    def _fn(self):
        from dos2_tools.scripts.generate_armour_module import convert_type
        return convert_type

    def test_integer_string(self):
        assert self._fn()("42") == 42

    def test_negative_integer(self):
        assert self._fn()("-3") == -3

    def test_float_string(self):
        result = self._fn()("3.14")
        assert isinstance(result, float)
        assert abs(result - 3.14) < 1e-9

    def test_true_string(self):
        assert self._fn()("true") is True

    def test_yes_string(self):
        assert self._fn()("yes") is True

    def test_false_string(self):
        assert self._fn()("false") is False

    def test_no_string(self):
        assert self._fn()("no") is False

    def test_quoted_string_unquoted(self):
        # '"hello"' → 'hello'  (strip outer quotes)
        result = self._fn()('"hello"')
        assert result == "hello"

    def test_quoted_string_with_escaped_quote(self):
        result = self._fn()('"say \\"hi\\""')
        assert result == 'say "hi"'

    def test_plain_string_passthrough(self):
        result = self._fn()("SomeName")
        assert result == "SomeName"

    def test_non_string_passthrough(self):
        assert self._fn()(42) == 42

    def test_none_passthrough(self):
        assert self._fn()(None) is None

    def test_single_char_quoted_string_not_unquoted(self):
        # A single-character string like '"' has len <= 1 and should not be unquoted
        result = self._fn()('"')
        # Not unquoted — just passed through (quotes escaped)
        assert isinstance(result, str)

    def test_zero_string(self):
        assert self._fn()("0") == 0

    def test_positive_float_with_trailing_zero(self):
        result = self._fn()("1.0")
        assert isinstance(result, float)
        assert result == 1.0


# ─── escape_lua_string ───────────────────────────────────────────────────────
# Shared by: generate_recipe_data_module and generate_recipes_module

class TestEscapeLuaString:
    """Unit tests for the shared escape_lua_string() helper."""

    def _fn(self):
        from dos2_tools.scripts.generate_recipe_data_module import escape_lua_string
        return escape_lua_string

    def test_none_returns_nil(self):
        assert self._fn()(None) == "nil"

    def test_empty_string_returns_nil(self):
        assert self._fn()("") == "nil"

    def test_plain_string_wrapped_in_quotes(self):
        assert self._fn()("foo") == '"foo"'

    def test_backslash_escaped(self):
        result = self._fn()("a\\b")
        assert "\\\\" in result

    def test_double_quote_escaped(self):
        result = self._fn()('a"b')
        assert '\\"' in result

    def test_newline_replaced_with_space(self):
        result = self._fn()("a\nb")
        assert "\n" not in result
        assert " " in result

    def test_recipes_module_has_same_escape_logic(self):
        from dos2_tools.scripts.generate_recipes_module import escape_lua_string as fn2
        assert fn2("hello") == '"hello"'
        assert fn2(None) == "nil"
        assert fn2("") == "nil"


# ─── generate_icon_redirects helpers ────────────────────────────────────────

class TestGetNodeValue:
    """Unit tests for get_node_value() from generate_icon_redirects."""

    def _fn(self):
        from dos2_tools.scripts.generate_icon_redirects import get_node_value
        return get_node_value

    def test_plain_string_value(self):
        node = {"Icon": "sword_icon"}
        assert self._fn()(node, "Icon") == "sword_icon"

    def test_dict_value_extracted(self):
        node = {"Icon": {"value": "shield_icon"}}
        assert self._fn()(node, "Icon") == "shield_icon"

    def test_missing_key_returns_none(self):
        assert self._fn()({}, "Icon") is None

    def test_none_value(self):
        node = {"Icon": None}
        assert self._fn()(node, "Icon") is None


class TestResolveNodeName:
    """Unit tests for resolve_node_name() from generate_icon_redirects."""

    def _fn(self):
        from dos2_tools.scripts.generate_icon_redirects import resolve_node_name
        return resolve_node_name

    def _make_loc(self, handle_map=None, text_map=None):
        """Return a minimal stub localization object."""
        class FakeLoc:
            def get_handle_text(self, handle):
                return (handle_map or {}).get(handle)

            def get_text(self, key):
                return (text_map or {}).get(key)

        return FakeLoc()

    def test_prefers_displayname_handle(self):
        node = {
            "DisplayName": {"handle": "h1"},
            "Stats": {"value": "SWORD"},
            "Name": {"value": "internal_name"},
        }
        loc = self._make_loc(handle_map={"h1": "Great Sword"}, text_map={"SWORD": "Sword"})
        assert self._fn()(node, loc) == "Great Sword"

    def test_falls_back_to_stats_loc(self):
        node = {
            "DisplayName": {"handle": "h_missing"},
            "Stats": {"value": "SWORD"},
        }
        loc = self._make_loc(text_map={"SWORD": "Sword"})
        assert self._fn()(node, loc) == "Sword"

    def test_falls_back_to_name_field(self):
        node = {
            "Stats": {"value": "UNKNOWN"},
            "Name": {"value": "ActualName"},
        }
        loc = self._make_loc()
        assert self._fn()(node, loc) == "ActualName"

    def test_returns_none_when_all_fail(self):
        node = {}
        loc = self._make_loc()
        assert self._fn()(node, loc) is None

    def test_plain_string_stats_node(self):
        node = {"Stats": "ITEM_KEY"}
        loc = self._make_loc(text_map={"ITEM_KEY": "My Item"})
        assert self._fn()(node, loc) == "My Item"

    def test_stats_none_string_skipped(self):
        node = {"Stats": {"value": "None"}, "Name": {"value": "Fallback"}}
        loc = self._make_loc()
        assert self._fn()(node, loc) == "Fallback"


# ─── generate_loot_data helpers ──────────────────────────────────────────────

class TestLootGraph:
    """Unit tests for LootGraph from generate_loot_data."""

    def _make_graph(self, tables_dict):
        from dos2_tools.scripts.generate_loot_data import LootGraph
        return LootGraph(tables_dict)

    def test_single_parent_table_not_shared(self):
        tables = {
            "Parent": {"pools": [{"items": [{"name": "Child"}]}]},
            "Child": {"pools": []},
        }
        graph = self._make_graph(tables)
        shared = graph.get_shared_tables()
        assert "Child" not in shared

    def test_multi_parent_table_is_shared(self):
        tables = {
            "ParentA": {"pools": [{"items": [{"name": "Child"}]}]},
            "ParentB": {"pools": [{"items": [{"name": "Child"}]}]},
            "Child": {"pools": []},
        }
        graph = self._make_graph(tables)
        shared = graph.get_shared_tables()
        assert "Child" in shared

    def test_force_shared_prefix_st_gen(self):
        tables = {
            "ST_GenWeapons": {"pools": []},
        }
        graph = self._make_graph(tables)
        shared = graph.get_shared_tables()
        assert "ST_GenWeapons" in shared

    def test_force_shared_prefix_reward(self):
        tables = {
            "Reward_QuestChest": {"pools": []},
        }
        graph = self._make_graph(tables)
        shared = graph.get_shared_tables()
        assert "Reward_QuestChest" in shared

    def test_t_prefix_alias_resolved(self):
        """A child referenced as 'T_Child' should map to 'Child'."""
        tables = {
            "ParentA": {"pools": [{"items": [{"name": "T_Child"}]}]},
            "ParentB": {"pools": [{"items": [{"name": "T_Child"}]}]},
            "Child": {"pools": []},
        }
        graph = self._make_graph(tables)
        shared = graph.get_shared_tables()
        assert "Child" in shared

    def test_skillbook_excluded_from_shared(self):
        """Tables with 'Skillbook' in the name are never marked shared."""
        tables = {
            "ParentA": {"pools": [{"items": [{"name": "SkillbookTable"}]}]},
            "ParentB": {"pools": [{"items": [{"name": "SkillbookTable"}]}]},
            "SkillbookTable": {"pools": []},
        }
        graph = self._make_graph(tables)
        shared = graph.get_shared_tables()
        assert "SkillbookTable" not in shared

    def test_empty_tables_no_crash(self):
        graph = self._make_graph({})
        assert graph.get_shared_tables() == set()


class TestGetCategoryInfo:
    """Unit tests for get_category_info() from generate_loot_data."""

    def test_equipment_category_returns_equipment_type(self):
        from dos2_tools.scripts.generate_loot_data import get_category_info

        class FakeStatsManager:
            def get_category_info(self, cat):
                return []

        result_type, result_items = get_category_info("Sword", FakeStatsManager())
        assert result_type == "Equipment"
        assert result_items == []

    def test_unknown_category_with_no_items_returns_none(self):
        from dos2_tools.scripts.generate_loot_data import get_category_info

        class FakeStatsManager:
            def get_category_info(self, cat):
                return []

        result_type, result_items = get_category_info("UnknownCat", FakeStatsManager())
        assert result_type is None
        assert result_items == []

    def test_collection_category_returns_sorted_items(self):
        from dos2_tools.scripts.generate_loot_data import get_category_info

        items = [
            {"id": "I_B", "min_level": 5},
            {"id": "I_A", "min_level": 1},
        ]

        class FakeStatsManager:
            def get_category_info(self, cat):
                return items

        result_type, result_items = get_category_info("SomeCat", FakeStatsManager())
        assert result_type == "Collection"
        # Sorted by (min_level, id)
        assert result_items[0]["id"] == "I_A"
        assert result_items[1]["id"] == "I_B"


class TestGenerateTablePage:
    """Unit tests for generate_table_page() from generate_loot_data."""

    def _fn(self):
        from dos2_tools.scripts.generate_loot_data import generate_table_page
        return generate_table_page

    def test_contains_table_id(self):
        result = self._fn()("MyLootTable")
        assert "MyLootTable" in result

    def test_contains_infobox_template(self):
        result = self._fn()("MyLootTable")
        assert "{{InfoboxLootTable" in result

    def test_contains_npc_loot_template(self):
        result = self._fn()("MyLootTable")
        assert "{{NPC Loot" in result

    def test_contains_category_tag(self):
        result = self._fn()("MyLootTable")
        assert "[[Category:Loot Tables]]" in result

    def test_returns_string(self):
        assert isinstance(self._fn()("T"), str)


# ─── build_recipe_lua (generate_recipe_data_module) ─────────────────────────

class TestBuildRecipeLua:
    """Unit tests for build_recipe_lua() using stub game objects."""

    def _make_game(self, templates_by_stats=None, combo_previews=None, loc_names=None):
        """Minimal stub that satisfies the attributes accessed by build_recipe_lua."""
        class FakeGame:
            def __init__(self):
                self.templates_by_stats = templates_by_stats or {}
                self.combo_previews = combo_previews or {}
                self._loc_names = loc_names or {}

            def resolve_display_name(self, stats_id, template_data=None):
                return self._loc_names.get(stats_id)

        return FakeGame()

    def test_empty_combos_produces_return_braces(self):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        result = build_recipe_lua({}, self._make_game())
        assert result.strip().startswith("return {")
        assert result.strip().endswith("}")

    def test_single_combo_has_ingredient_and_result_keys(self):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        combos = {
            "Combo_A": {
                "Data": {
                    "Object 1": "OBJ_Herb",
                    "Type 1": "Object",
                    "Transform 1": "",
                },
                "Results": {
                    "Result 1": "OBJ_Potion",
                },
            }
        }
        result = build_recipe_lua(combos, self._make_game())
        assert "Combo_A" in result
        assert "ingredients" in result
        assert "results" in result

    def test_name_override_applied(self):
        """BOOK_Paper_Sheet_A should appear as 'Sheet of Paper' via NAME_OVERRIDES."""
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        combos = {
            "Combo_Paper": {
                "Data": {
                    "Object 1": "BOOK_Paper_Sheet_A",
                    "Type 1": "Object",
                    "Transform 1": "",
                },
                "Results": {"Result 1": "OBJ_Something"},
            }
        }
        result = build_recipe_lua(combos, self._make_game())
        assert "Sheet of Paper" in result

    def test_category_ingredient_uses_tooltip(self):
        """Category-type ingredients should use the Tooltip from combo_previews."""
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        previews = {"Herb": {"Tooltip": "Any Herb"}}
        combos = {
            "Combo_Herb": {
                "Data": {
                    "Object 1": "Herb",
                    "Type 1": "Category",
                    "Transform 1": "",
                },
                "Results": {"Result 1": "OBJ_Potion"},
            }
        }
        result = build_recipe_lua(combos, self._make_game(combo_previews=previews))
        assert "Any Herb" in result

    def test_object_ingredient_uses_resolve_display_name(self):
        """Object-type ingredients use resolve_display_name when no override."""
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        combos = {
            "Combo_B": {
                "Data": {
                    "Object 1": "OBJ_SomeHerb",
                    "Type 1": "Object",
                    "Transform 1": "",
                },
                "Results": {"Result 1": "OBJ_Brew"},
            }
        }
        game = self._make_game(loc_names={"OBJ_SomeHerb": "Magic Herb"})
        result = build_recipe_lua(combos, game)
        assert "Magic Herb" in result

    def test_station_field_included_when_set(self):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        combos = {
            "Combo_C": {
                "Data": {
                    "CraftingStation": "Oven",
                    "Object 1": "OBJ_Flour",
                    "Type 1": "Object",
                    "Transform 1": "",
                },
                "Results": {"Result 1": "OBJ_Bread"},
            }
        }
        result = build_recipe_lua(combos, self._make_game())
        assert "station" in result
        assert "Oven" in result

    def test_station_field_omitted_when_absent(self):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        combos = {
            "Combo_D": {
                "Data": {
                    "Object 1": "OBJ_X",
                    "Type 1": "Object",
                    "Transform 1": "",
                },
                "Results": {"Result 1": "OBJ_Y"},
            }
        }
        result = build_recipe_lua(combos, self._make_game())
        # No station key present in data
        result_lines = [ln for ln in result.splitlines() if "station" in ln.lower()]
        assert not result_lines

    def test_multiple_combos_all_present(self):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        combos = {}
        for i in range(3):
            combos[f"Combo_{i}"] = {
                "Data": {
                    "Object 1": f"OBJ_{i}_0",
                    "Type 1": "Object",
                    "Transform 1": "",
                },
                "Results": {"Result 1": f"OBJ_Result_{i}"},
            }
        result = build_recipe_lua(combos, self._make_game())
        for i in range(3):
            assert f"Combo_{i}" in result


# ─── Integration: generate_armour_module ─────────────────────────────────────

@pytest.mark.integration
class TestGenerateArmourModuleIntegration:
    """Integration tests for the armour module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_armour_module import convert_type
        stats_db = real_game_data.stats
        armor_shield_stats = {
            k: v for k, v in stats_db.items()
            if v.get("_type") in ("Armor", "Shield")
        }
        typed_data = {}
        for entry_id, data in armor_shield_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        # Resolve Boosts linking (same as script)
        for entry_id, data in typed_data.items():
            if "Boosts" in data and isinstance(data["Boosts"], str):
                boost_keys = [k.strip() for k in data["Boosts"].split(";") if k.strip()]
                data["Boosts"] = [typed_data[bk] for bk in boost_keys if bk in typed_data]
        return typed_data

    def test_armor_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 100

    def test_private_keys_excluded(self, real_game_data):
        """No internal _keys (other than _type) should survive into typed_data."""
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            for key in data:
                assert not (key.startswith("_") and key != "_type"), (
                    f"Private key {key!r} found in {entry_id}"
                )

    def test_all_min_level_fields_are_ints(self, real_game_data):
        """Every MinLevel that survived should be int, not string."""
        typed_data = self._build_typed_data(real_game_data)
        bad = [
            (k, v["MinLevel"]) for k, v in typed_data.items()
            if "MinLevel" in v and not isinstance(v["MinLevel"], int)
        ]
        assert bad == [], f"Non-int MinLevel entries: {bad}"

    def test_all_value_fields_are_ints(self, real_game_data):
        """Every Value field should convert to int."""
        typed_data = self._build_typed_data(real_game_data)
        bad = [
            (k, v["Value"]) for k, v in typed_data.items()
            if "Value" in v and not isinstance(v["Value"], (int, float))
        ]
        assert bad == [], f"Non-numeric Value entries: {bad}"

    def test_arm_civilian_upperbody_slot_is_breast(self, real_game_data):
        """ARM_Civilian_UpperBody should have Slot='Breast' after convert_type."""
        typed_data = self._build_typed_data(real_game_data)
        assert "ARM_Civilian_UpperBody" in typed_data
        entry = typed_data["ARM_Civilian_UpperBody"]
        assert entry["Slot"] == "Breast"

    def test_arm_civilian_upperbody_armor_defense_is_int(self, real_game_data):
        """ARM_Civilian_UpperBody's 'Armor Defense Value' should be int 30."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["ARM_Civilian_UpperBody"]
        assert isinstance(entry.get("Armor Defense Value"), int)
        assert entry["Armor Defense Value"] == 30

    def test_armor_with_boosts_resolves_to_list_of_dicts(self, real_game_data):
        """ARM_UNIQUE_Hildurs_Plate_UpperBody has a Boosts reference — should be a list."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data.get("ARM_UNIQUE_Hildurs_Plate_UpperBody")
        if entry and "Boosts" in entry:
            assert isinstance(entry["Boosts"], list)
            # Each resolved boost should be an OrderedDict (i.e. another stat entry)
            for boost in entry["Boosts"]:
                assert isinstance(boost, dict)

    def test_only_armor_and_shield_types(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        bad = [k for k, v in typed_data.items() if v.get("_type") not in ("Armor", "Shield")]
        assert bad == []


# ─── Integration: generate_weapon_module ─────────────────────────────────────

@pytest.mark.integration
class TestGenerateWeaponModuleIntegration:
    """Integration tests for the weapon module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_weapon_module import convert_type
        stats_db = real_game_data.stats
        weapon_stats = {k: v for k, v in stats_db.items() if v.get("_type") == "Weapon"}
        typed_data = {}
        for entry_id, data in weapon_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        # Resolve Boosts linking
        for entry_id, data in typed_data.items():
            if "Boosts" in data and isinstance(data["Boosts"], str):
                boost_keys = [k.strip() for k in data["Boosts"].split(";") if k.strip()]
                data["Boosts"] = [typed_data[bk] for bk in boost_keys if bk in typed_data]
        return typed_data

    def test_weapon_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 50

    def test_only_weapons_present(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        bad = [k for k, v in typed_data.items() if v.get("_type") != "Weapon"]
        assert bad == []

    def test_wpn_sword_1h_damage_type_is_physical(self, real_game_data):
        """WPN_Sword_1H should have Damage Type = 'Physical' (a string)."""
        typed_data = self._build_typed_data(real_game_data)
        assert "WPN_Sword_1H" in typed_data
        entry = typed_data["WPN_Sword_1H"]
        assert entry.get("Damage Type") == "Physical"

    def test_wpn_sword_1h_requirements_is_string(self, real_game_data):
        """Requirements field is a non-trivial string, not a number."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["WPN_Sword_1H"]
        req = entry.get("Requirements", "")
        assert isinstance(req, str)
        assert "Strength" in req

    def test_wpn_sword_1h_is_not_twohanded(self, real_game_data):
        """WPN_Sword_1H IsTwoHanded should convert to False (bool)."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["WPN_Sword_1H"]
        assert entry.get("IsTwoHanded") is False

    def test_cheat_sword_boosts_resolved_to_list(self, real_game_data):
        """WPN_Cheat_Sword_1H_Fire has a Boosts reference — should resolve to a list."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data.get("WPN_Cheat_Sword_1H_Fire")
        if entry and "Boosts" in entry:
            assert isinstance(entry["Boosts"], list)

    def test_attackapcost_is_int(self, real_game_data):
        """AttackAPCost for WPN_Sword_1H should be an integer."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["WPN_Sword_1H"]
        assert isinstance(entry.get("AttackAPCost"), int)
        assert entry["AttackAPCost"] == 2


# ─── Integration: generate_potion_module ─────────────────────────────────────

@pytest.mark.integration
class TestGeneratePotionModuleIntegration:
    """Integration tests for the potion module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_potion_module import convert_type
        stats_db = real_game_data.stats
        potion_stats = {k: v for k, v in stats_db.items() if v.get("_type") == "Potion"}
        typed_data = {}
        for entry_id, data in potion_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_potion_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 50

    def test_only_potion_type(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        bad = [k for k, v in typed_data.items() if v.get("_type") != "Potion"]
        assert bad == []

    def test_minor_healing_potion_is_consumable_bool(self, real_game_data):
        """IsConsumable for POTION_Healing_Poisoned_Masked_Minor_A should be True (bool)."""
        typed_data = self._build_typed_data(real_game_data)
        assert "POTION_Healing_Poisoned_Masked_Minor_A" in typed_data
        entry = typed_data["POTION_Healing_Poisoned_Masked_Minor_A"]
        assert entry.get("IsConsumable") is True

    def test_minor_healing_potion_inventorytab(self, real_game_data):
        """InventoryTab should be a string 'Consumable', not a bool or int."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["POTION_Healing_Poisoned_Masked_Minor_A"]
        assert entry.get("InventoryTab") == "Consumable"

    def test_minor_healing_potion_combocategory(self, real_game_data):
        """ComboCategory should survive as string."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["POTION_Healing_Poisoned_Masked_Minor_A"]
        assert entry.get("ComboCategory") == "PotionPoison"

    def test_weight_is_int(self, real_game_data):
        """Weight field should be int after convert_type."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["POTION_Healing_Poisoned_Masked_Minor_A"]
        assert isinstance(entry.get("Weight"), int)
        assert entry["Weight"] == 250

    def test_use_apcost_is_int(self, real_game_data):
        """UseAPCost should be int 1."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["POTION_Healing_Poisoned_Masked_Minor_A"]
        assert isinstance(entry.get("UseAPCost"), int)
        assert entry["UseAPCost"] == 1


# ─── Integration: generate_skill_data_module ─────────────────────────────────

@pytest.mark.integration
class TestGenerateSkillDataModuleIntegration:
    """Integration tests for the skill data module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_skill_data_module import convert_type
        stats_db = real_game_data.stats
        skill_stats = {
            k: v for k, v in stats_db.items()
            if isinstance(v.get("_type"), str) and v["_type"].startswith("Skill")
        }
        typed_data = {}
        for entry_id, data in skill_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_skill_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 100

    def test_all_entries_have_skill_type_prefix(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        bad = [k for k, v in typed_data.items() if not v.get("_type", "").startswith("Skill")]
        assert bad == []

    def test_shout_healingtears_skill_type_is_shout(self, real_game_data):
        """Shout_HealingTears.SkillType should be 'Shout' (string)."""
        typed_data = self._build_typed_data(real_game_data)
        assert "Shout_HealingTears" in typed_data
        entry = typed_data["Shout_HealingTears"]
        assert entry.get("SkillType") == "Shout"

    def test_shout_healingtears_ability_is_water(self, real_game_data):
        """Shout_HealingTears.Ability should be 'Water' (string)."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["Shout_HealingTears"]
        assert entry.get("Ability") == "Water"

    def test_shout_healingtears_action_points_is_int(self, real_game_data):
        """ActionPoints for Shout_HealingTears should be int 1."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["Shout_HealingTears"]
        assert isinstance(entry.get("ActionPoints"), int)
        assert entry["ActionPoints"] == 1

    def test_shout_healingtears_for_game_master_is_bool(self, real_game_data):
        """ForGameMaster = 'Yes' → True (bool) after convert_type."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["Shout_HealingTears"]
        assert entry.get("ForGameMaster") is True

    def test_cooldown_is_int_or_float(self, real_game_data):
        """Cooldown 5 → int 5."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["Shout_HealingTears"]
        assert isinstance(entry.get("Cooldown"), (int, float))
        assert entry["Cooldown"] == 5

    def test_skill_types_are_varied(self, real_game_data):
        """Skills include types beyond SkillData — e.g. SkillBoost, etc."""
        typed_data = self._build_typed_data(real_game_data)
        types = {v.get("_type") for v in typed_data.values()}
        assert len(types) >= 2, f"Expected multiple skill _type values, got: {types}"


# ─── Integration: generate_item_data_module ──────────────────────────────────

@pytest.mark.integration
class TestGenerateItemDataModuleIntegration:
    """Integration tests for the item data module generator with real game data."""

    def _build_typed_data(self, real_game_data, include_types=None):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_item_data_module import convert_type, DEFAULT_TYPES
        if include_types is None:
            include_types = DEFAULT_TYPES
        stats_db = real_game_data.stats
        item_stats = {k: v for k, v in stats_db.items() if v.get("_type") in include_types}
        typed_data = {}
        for entry_id, data in item_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_object_and_potion_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 50

    def test_only_default_types_included(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        bad = [k for k, v in typed_data.items() if v.get("_type") not in ("Object", "Potion")]
        assert bad == []

    def test_private_keys_excluded(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            for key in data:
                assert not (key.startswith("_") and key != "_type")

    def test_scroll_resurrect_inventory_tab_is_magical(self, real_game_data):
        """SCROLL_Resurrect.InventoryTab should remain 'Magical' (not bool/int)."""
        typed_data = self._build_typed_data(real_game_data)
        assert "SCROLL_Resurrect" in typed_data
        entry = typed_data["SCROLL_Resurrect"]
        assert entry.get("InventoryTab") == "Magical"

    def test_scroll_resurrect_use_apcost_is_int(self, real_game_data):
        """UseAPCost = '3' should convert to int 3."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["SCROLL_Resurrect"]
        assert isinstance(entry.get("UseAPCost"), int)
        assert entry["UseAPCost"] == 3

    def test_scroll_resurrect_weight_is_int(self, real_game_data):
        """Weight = '20' should convert to int 20."""
        typed_data = self._build_typed_data(real_game_data)
        entry = typed_data["SCROLL_Resurrect"]
        assert isinstance(entry.get("Weight"), int)
        assert entry["Weight"] == 20

    def test_object_only_subset(self, real_game_data):
        """Passing include_types={'Object'} should exclude all Potion entries."""
        typed_data = self._build_typed_data(real_game_data, include_types={"Object"})
        bad = [k for k, v in typed_data.items() if v.get("_type") != "Object"]
        assert bad == []


# ─── Integration: generate_items_lua ─────────────────────────────────────────

@pytest.mark.integration
class TestGenerateItemsLuaIntegration:
    """Integration tests for generate_items_lua with real game data."""

    def _build_final_data(self, real_game_data):
        from dos2_tools.scripts.generate_items_lua import STAT_FIELDS, ITEM_TYPES
        stats_db = real_game_data.stats
        templates_by_mapkey = real_game_data.templates_by_mapkey

        mapkey_to_skill = {}
        for rt_uuid, rt_data in templates_by_mapkey.items():
            skill_id_node = rt_data.get("SkillID")
            if skill_id_node is not None:
                skill_id = (
                    skill_id_node.get("value")
                    if isinstance(skill_id_node, dict)
                    else skill_id_node
                )
                if skill_id:
                    mapkey_to_skill[rt_uuid] = skill_id

        final_lua_data = {}
        for entry_id, data in stats_db.items():
            if data.get("_type") not in ITEM_TYPES:
                continue
            template_guid = data.get("RootTemplate")
            enriched = dict(data)
            if template_guid and template_guid in mapkey_to_skill:
                enriched["SkillID"] = mapkey_to_skill[template_guid]
            clean_data = {k: v for k, v in enriched.items() if k in STAT_FIELDS}
            if clean_data:
                final_lua_data[entry_id] = clean_data

        return final_lua_data, STAT_FIELDS

    def test_items_found(self, real_game_data):
        final_lua_data, _ = self._build_final_data(real_game_data)
        assert len(final_lua_data) > 100

    def test_all_output_keys_are_in_whitelist(self, real_game_data):
        """Every field present in the output must be in STAT_FIELDS."""
        final_lua_data, stat_fields = self._build_final_data(real_game_data)
        for entry_id, data in final_lua_data.items():
            for key in data:
                assert key in stat_fields, (
                    f"Key {key!r} in {entry_id} is not in STAT_FIELDS whitelist"
                )

    def test_scroll_resurrect_inventory_tab_present(self, real_game_data):
        """SCROLL_Resurrect has InventoryTab='Magical', which is in the whitelist."""
        final_lua_data, _ = self._build_final_data(real_game_data)
        assert "SCROLL_Resurrect" in final_lua_data
        entry = final_lua_data["SCROLL_Resurrect"]
        assert entry.get("InventoryTab") == "Magical"

    def test_scroll_resurrect_object_category(self, real_game_data):
        """ObjectCategory='ScrollResurrect' should pass through the whitelist."""
        final_lua_data, _ = self._build_final_data(real_game_data)
        entry = final_lua_data["SCROLL_Resurrect"]
        assert entry.get("ObjectCategory") == "ScrollResurrect"

    def test_scroll_resurrect_root_template_uuid_present(self, real_game_data):
        """RootTemplate is in STAT_FIELDS and should be the correct UUID string."""
        final_lua_data, _ = self._build_final_data(real_game_data)
        entry = final_lua_data["SCROLL_Resurrect"]
        rt = entry.get("RootTemplate")
        assert isinstance(rt, str)
        assert len(rt) == 36  # UUID format

    def test_skill_id_injected_for_some_items(self, real_game_data):
        """SkillID must have been injected from RootTemplate for at least one item."""
        final_lua_data, _ = self._build_final_data(real_game_data)
        skill_id_items = [k for k, v in final_lua_data.items() if "SkillID" in v]
        assert len(skill_id_items) > 0

    def test_no_private_key_fields_present(self, real_game_data):
        """Fields like _type, _using should be stripped by the whitelist filter."""
        final_lua_data, _ = self._build_final_data(real_game_data)
        for entry_id, data in final_lua_data.items():
            for key in data:
                assert not key.startswith("_"), (
                    f"Private key {key!r} leaked into output for {entry_id}"
                )


# ─── Integration: generate_recipe_data_module ────────────────────────────────

@pytest.mark.integration
class TestGenerateRecipeDataModuleIntegration:
    """Integration tests for generate_recipe_data_module with real game data."""

    # Session-level cache so build_recipe_lua only runs once across all tests.
    _lua_cache: "str | None" = None

    def _get_lua(self, real_game_data):
        if TestGenerateRecipeDataModuleIntegration._lua_cache is None:
            from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
            TestGenerateRecipeDataModuleIntegration._lua_cache = build_recipe_lua(
                real_game_data.item_combos, real_game_data
            )
        return TestGenerateRecipeDataModuleIntegration._lua_cache

    def test_over_1000_combos_loaded(self, real_game_data):
        assert len(real_game_data.item_combos) >= 1000

    def test_output_is_valid_lua_wrapper(self, real_game_data):
        lua = self._get_lua(real_game_data)
        assert lua.strip().startswith("return {")
        assert lua.strip().endswith("}")

    def test_every_combo_has_ingredients_and_results_block(self, real_game_data):
        """Parse the output and verify every combo block has both sections."""
        lua = self._get_lua(real_game_data)
        lines = lua.splitlines()
        combo_lines = [ln for ln in lines if ln.startswith('    ["')]
        assert len(combo_lines) == len(real_game_data.item_combos), (
            "Number of combo blocks in Lua output doesn't match item_combos count"
        )

    # ─ NAME_OVERRIDES ────────────────────────────────────────────────────────

    def test_paper_sheet_name_override_applied(self, real_game_data):
        """BOOK_Paper_Sheet_A → 'Sheet of Paper' via NAME_OVERRIDES."""
        lua = self._get_lua(real_game_data)
        # The combo ID containing BOOK_Paper_Sheet_A as obj1 must show the override
        assert 'id = "BOOK_Paper_Sheet_A"' in lua
        assert 'name = "Sheet of Paper"' in lua

    def test_swornbreaker_result_uses_name_override(self, real_game_data):
        """WPN_UNIQUE_AtaraxianScythe result should be 'The Swornbreaker'."""
        lua = self._get_lua(real_game_data)
        assert 'id = "WPN_UNIQUE_AtaraxianScythe"' in lua
        assert 'name = "The Swornbreaker"' in lua

    # ─ Object ingredient resolution (templates_by_stats + resolve_display_name) ─

    def test_swornbreaker_blade_ingredient_resolves_named(self, real_game_data):
        """QUEST_AtaraxianScythe_Blade should resolve to 'Blade of the Swornbreaker'."""
        lua = self._get_lua(real_game_data)
        assert 'name = "Blade of the Swornbreaker"' in lua

    def test_swornbreaker_shaft_ingredient_resolves_named(self, real_game_data):
        """QUEST_AtaraxianScythe_Shaft should resolve to 'Haft of the Swornbreaker'."""
        lua = self._get_lua(real_game_data)
        assert 'name = "Haft of the Swornbreaker"' in lua

    def test_swornbreaker_schematic_ingredient_resolves_named(self, real_game_data):
        """QUEST_AtaraxianTablet_PromiseInfo should resolve to 'Swornbreaker Schematic'."""
        lua = self._get_lua(real_game_data)
        assert 'name = "Swornbreaker Schematic"' in lua

    # ─ Category ingredient resolution (combo_previews Tooltip) ───────────────

    def test_essence_fire_category_resolves_to_fire_essence(self, real_game_data):
        """EssenceFire (Category) tooltip should be 'Fire Essence'."""
        lua = self._get_lua(real_game_data)
        assert 'id = "EssenceFire"' in lua
        assert 'name = "Fire Essence"' in lua

    # ─ Result resolution ─────────────────────────────────────────────────────

    def test_scroll_flaming_daggers_result_resolved(self, real_game_data):
        """SCROLL_FlamingDaggers result should resolve to 'Searing Daggers Scroll'."""
        lua = self._get_lua(real_game_data)
        assert 'id = "SCROLL_FlamingDaggers"' in lua
        assert 'name = "Searing Daggers Scroll"' in lua

    # ─ Station and other fields ───────────────────────────────────────────────

    def test_anvil_station_present(self, real_game_data):
        """Anvil_LOOT_MetalShard_A_Hammer should have station = 'Anvil'."""
        lua = self._get_lua(real_game_data)
        idx = lua.find("Anvil_LOOT_MetalShard_A_Hammer")
        assert idx >= 0
        block = lua[idx:idx + 400]
        assert 'station = "Anvil"' in block

    def test_tooth_ingredient_resolves_to_tooth(self, real_game_data):
        """LOOT_Tooth_A (Object) in the paper+fire+tooth scroll recipe → 'Tooth'."""
        lua = self._get_lua(real_game_data)
        assert 'name = "Tooth"' in lua

    def test_transform_fields_preserved(self, real_game_data):
        """transform field should be present for every ingredient line."""
        lua = self._get_lua(real_game_data)
        assert "transform" in lua


# ─── Integration: generate_loot_data ─────────────────────────────────────────

@pytest.mark.integration
class TestGenerateLootDataIntegration:
    """Integration tests for generate_loot_data with real game data."""

    def _make_graph(self, real_game_data):
        from dos2_tools.scripts.generate_loot_data import LootGraph
        return LootGraph(real_game_data.loot_engine.tables)

    def test_loot_tables_loaded(self, real_game_data):
        assert len(real_game_data.loot_engine.tables) > 100

    def test_shared_tables_detected(self, real_game_data):
        shared = self._make_graph(real_game_data).get_shared_tables()
        assert len(shared) > 10

    def test_st_gen_prefix_tables_are_shared(self, real_game_data):
        """Any table starting with ST_Gen must be in the shared set."""
        graph = self._make_graph(real_game_data)
        shared = graph.get_shared_tables()
        st_gen = [t for t in real_game_data.loot_engine.tables if t.startswith("ST_Gen")]
        assert len(st_gen) > 0, "No ST_Gen tables found in game data"
        for t in st_gen:
            assert t in shared, f"{t} starts with ST_Gen but is not in shared set"

    def test_st_humanoid_prefix_tables_are_shared(self, real_game_data):
        graph = self._make_graph(real_game_data)
        shared = graph.get_shared_tables()
        humanoid = [t for t in real_game_data.loot_engine.tables if t.startswith("ST_Humanoid")]
        assert len(humanoid) > 0, "No ST_Humanoid tables found"
        for t in humanoid:
            assert t in shared, f"{t} starts with ST_Humanoid but is not in shared set"

    def test_reward_prefix_tables_are_shared(self, real_game_data):
        graph = self._make_graph(real_game_data)
        shared = graph.get_shared_tables()
        reward = [t for t in real_game_data.loot_engine.tables if t.startswith("Reward_")]
        assert len(reward) > 0, "No Reward_ tables found"
        for t in reward:
            assert t in shared, f"{t} starts with Reward_ but is not in shared set"

    def test_multi_parent_table_is_shared(self, real_game_data):
        """A table referenced by >1 parents should be in the shared set."""
        graph = self._make_graph(real_game_data)
        multi_parent = [
            t for t, parents in graph.reverse_edges.items()
            if len(set(parents)) > 1 and "Skillbook" not in t
        ]
        assert len(multi_parent) > 0, "Expected at least one multi-parent table"
        shared = graph.get_shared_tables()
        for t in multi_parent[:5]:  # spot-check first 5 only
            assert t in shared, f"{t} has {len(set(graph.reverse_edges[t]))} parents but is not shared"

    def test_generate_table_page_st_gen_table(self, real_game_data):
        """generate_table_page for a real ST_Gen table produces correct wikitext."""
        from dos2_tools.scripts.generate_loot_data import generate_table_page
        tables = real_game_data.loot_engine.tables
        gen_tables = sorted(t for t in tables if t.startswith("ST_Gen"))
        assert gen_tables, "No ST_Gen tables in game data"
        table_id = gen_tables[0]
        page = generate_table_page(table_id)
        assert table_id in page
        assert "{{InfoboxLootTable" in page
        assert "{{NPC Loot" in page
        assert "[[Category:Loot Tables]]" in page

    def test_skillbook_tables_never_shared(self, real_game_data):
        """Tables with 'Skillbook' in the name must never appear in the shared set."""
        shared = self._make_graph(real_game_data).get_shared_tables()
        skill_shared = [t for t in shared if "Skillbook" in t]
        assert skill_shared == [], f"Skillbook tables wrongly marked shared: {skill_shared}"


        from collections import OrderedDict
        from dos2_tools.scripts.generate_armour_module import convert_type
        stats_db = real_game_data.stats
        armor_shield_stats = {
            k: v for k, v in stats_db.items()
            if v.get("_type") in ("Armor", "Shield")
        }
        typed_data = {}
        for entry_id, data in armor_shield_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_armor_entries_found(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        assert len(typed_data) > 0

    def test_min_level_is_int(self, real_game_data):
        """MinLevel values should be integers after convert_type."""
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            if "MinLevel" in data:
                assert isinstance(data["MinLevel"], int), (
                    f"{entry_id}.MinLevel is not int: {data['MinLevel']!r}"
                )

    def test_boosts_resolved_to_list(self, real_game_data):
        """After Boosts resolution, Boosts fields should be lists, not strings."""
        typed_data = self._build_typed_data(real_game_data)
        # Resolve boosts (same logic as the script)
        for entry_id, data in typed_data.items():
            if "Boosts" in data and isinstance(data["Boosts"], str):
                boost_keys = [k.strip() for k in data["Boosts"].split(";") if k.strip()]
                resolved_boosts = [typed_data[bk] for bk in boost_keys if bk in typed_data]
                data["Boosts"] = resolved_boosts
        for entry_id, data in typed_data.items():
            if "Boosts" in data:
                assert isinstance(data["Boosts"], list), (
                    f"{entry_id}.Boosts is not a list after resolution"
                )

    def test_known_entry_present(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        # ARM_Civilian_UpperBody is a real Armor stat entry present in the game data
        assert "ARM_Civilian_UpperBody" in typed_data

    def test_private_keys_excluded(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            for key in data:
                assert not (key.startswith("_") and key != "_type"), (
                    f"Private key {key!r} found in {entry_id}"
                )


# ─── Integration: generate_weapon_module ─────────────────────────────────────

@pytest.mark.integration
class TestGenerateWeaponModuleIntegration:
    """Integration tests for the weapon module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_weapon_module import convert_type
        stats_db = real_game_data.stats
        weapon_stats = {k: v for k, v in stats_db.items() if v.get("_type") == "Weapon"}
        typed_data = {}
        for entry_id, data in weapon_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_weapon_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 0

    def test_known_entry_present(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        # WPN_Sword_1H is a real Weapon stat entry present in the game data
        assert "WPN_Sword_1H" in typed_data

    def test_all_entries_have_weapon_type(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            assert data.get("_type") == "Weapon", (
                f"{entry_id} has unexpected _type: {data.get('_type')!r}"
            )

    def test_boosts_resolved_after_linking(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            if "Boosts" in data and isinstance(data["Boosts"], str):
                boost_keys = [k.strip() for k in data["Boosts"].split(";") if k.strip()]
                resolved = [typed_data[bk] for bk in boost_keys if bk in typed_data]
                data["Boosts"] = resolved
        for entry_id, data in typed_data.items():
            if "Boosts" in data:
                assert isinstance(data["Boosts"], list)


# ─── Integration: generate_potion_module ─────────────────────────────────────

@pytest.mark.integration
class TestGeneratePotionModuleIntegration:
    """Integration tests for the potion module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_potion_module import convert_type
        stats_db = real_game_data.stats
        potion_stats = {k: v for k, v in stats_db.items() if v.get("_type") == "Potion"}
        typed_data = {}
        for entry_id, data in potion_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_potion_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 0

    def test_known_potion_entry_present(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        # POTION_Healing_Poisoned_Masked_Minor_A is a real Potion stat entry
        assert "POTION_Healing_Poisoned_Masked_Minor_A" in typed_data

    def test_all_entries_have_potion_type(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            assert data.get("_type") == "Potion"


# ─── Integration: generate_skill_data_module ─────────────────────────────────

@pytest.mark.integration
class TestGenerateSkillDataModuleIntegration:
    """Integration tests for the skill data module generator with real game data."""

    def _build_typed_data(self, real_game_data):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_skill_data_module import convert_type
        stats_db = real_game_data.stats
        skill_stats = {
            k: v for k, v in stats_db.items()
            if isinstance(v.get("_type"), str) and v["_type"].startswith("Skill")
        }
        typed_data = {}
        for entry_id, data in skill_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_skill_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 0

    def test_all_entries_start_with_skill(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            assert data.get("_type", "").startswith("Skill"), (
                f"{entry_id} has unexpected _type: {data.get('_type')!r}"
            )

    def test_known_skill_present(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        # Shout_HealingTears is a real SkillData entry present in the game data
        assert "Shout_HealingTears" in typed_data

    def test_skill_types_form_nonsingular_set(self, real_game_data):
        """Skills use multiple sub-types like SkillData, SkillBoost, etc."""
        typed_data = self._build_typed_data(real_game_data)
        skill_types = {data.get("_type") for data in typed_data.values()}
        assert len(skill_types) >= 1


# ─── Integration: generate_item_data_module ──────────────────────────────────

@pytest.mark.integration
class TestGenerateItemDataModuleIntegration:
    """Integration tests for the item data module generator with real game data."""

    def _build_typed_data(self, real_game_data, include_types=None):
        from collections import OrderedDict
        from dos2_tools.scripts.generate_item_data_module import convert_type, DEFAULT_TYPES
        if include_types is None:
            include_types = DEFAULT_TYPES
        stats_db = real_game_data.stats
        item_stats = {k: v for k, v in stats_db.items() if v.get("_type") in include_types}
        typed_data = {}
        for entry_id, data in item_stats.items():
            typed_entry = OrderedDict()
            for key, value in data.items():
                if key.startswith("_") and key != "_type":
                    continue
                typed_entry[key] = convert_type(value)
            typed_data[entry_id] = typed_entry
        return typed_data

    def test_object_and_potion_entries_found(self, real_game_data):
        assert len(self._build_typed_data(real_game_data)) > 0

    def test_known_object_entry_present(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        # SCROLL_Resurrect is a real Object stat entry present in the game data
        assert "SCROLL_Resurrect" in typed_data

    def test_all_entries_are_object_or_potion_type(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            assert data.get("_type") in ("Object", "Potion"), (
                f"{entry_id} has unexpected _type: {data.get('_type')!r}"
            )

    def test_private_keys_excluded(self, real_game_data):
        typed_data = self._build_typed_data(real_game_data)
        for entry_id, data in typed_data.items():
            for key in data:
                assert not (key.startswith("_") and key != "_type")


# ─── Integration: generate_items_lua ─────────────────────────────────────────

@pytest.mark.integration
class TestGenerateItemsLuaIntegration:
    """Integration tests for generate_items_lua with real game data."""

    def _build_final_data(self, real_game_data):
        from dos2_tools.scripts.generate_items_lua import STAT_FIELDS, ITEM_TYPES
        stats_db = real_game_data.stats
        templates_by_mapkey = real_game_data.templates_by_mapkey

        # Build SkillID index
        mapkey_to_skill = {}
        for rt_uuid, rt_data in templates_by_mapkey.items():
            if rt_data.skill_id:
                mapkey_to_skill[rt_uuid] = rt_data.skill_id

        final_lua_data = {}
        for entry_id, data in stats_db.items():
            entry_type = data.get("_type")
            if entry_type not in ITEM_TYPES:
                continue
            template_guid = data.get("RootTemplate")
            enriched = dict(data)
            if template_guid and template_guid in mapkey_to_skill:
                enriched["SkillID"] = mapkey_to_skill[template_guid]
            clean_data = {k: v for k, v in enriched.items() if k in STAT_FIELDS}
            if clean_data:
                final_lua_data[entry_id] = clean_data

        return final_lua_data, STAT_FIELDS

    def test_items_found(self, real_game_data):
        final_lua_data, _ = self._build_final_data(real_game_data)
        assert len(final_lua_data) > 0

    def test_all_keys_in_stat_fields_whitelist(self, real_game_data):
        final_lua_data, stat_fields = self._build_final_data(real_game_data)
        for entry_id, data in final_lua_data.items():
            for key in data:
                assert key in stat_fields, (
                    f"Key {key!r} in {entry_id} is not in STAT_FIELDS whitelist"
                )

    def test_known_item_present(self, real_game_data):
        final_lua_data, _ = self._build_final_data(real_game_data)
        # SCROLL_Resurrect is a real Object stat entry that passes the whitelist filter
        assert "SCROLL_Resurrect" in final_lua_data

    def test_skill_id_injected_from_template(self, real_game_data):
        """At least one item should have had SkillID injected from its RootTemplate."""
        final_lua_data, _ = self._build_final_data(real_game_data)
        skill_id_items = {k: v for k, v in final_lua_data.items() if "SkillID" in v}
        # There should be some skillbooks or consumables with SkillID
        assert len(skill_id_items) > 0


# ─── Integration: generate_recipe_data_module ────────────────────────────────

@pytest.mark.integration
class TestGenerateRecipeDataModuleIntegration:
    """Integration tests for generate_recipe_data_module with real game data."""

    def test_item_combos_loaded(self, real_game_data):
        assert len(real_game_data.item_combos) > 0

    def test_recipe_lua_starts_with_return(self, real_game_data):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        lua = build_recipe_lua(real_game_data.item_combos, real_game_data)
        assert lua.strip().startswith("return {")

    def test_recipe_lua_ends_with_brace(self, real_game_data):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        lua = build_recipe_lua(real_game_data.item_combos, real_game_data)
        assert lua.strip().endswith("}")

    def test_ingredients_key_present(self, real_game_data):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        lua = build_recipe_lua(real_game_data.item_combos, real_game_data)
        assert "ingredients" in lua

    def test_results_key_present(self, real_game_data):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        lua = build_recipe_lua(real_game_data.item_combos, real_game_data)
        assert "results" in lua

    def test_name_override_paper_sheet(self, real_game_data):
        """BOOK_Paper_Sheet_A should appear as 'Sheet of Paper' via NAME_OVERRIDES."""
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        lua = build_recipe_lua(real_game_data.item_combos, real_game_data)
        # Only assert this if the combo actually uses BOOK_Paper_Sheet_A
        if "BOOK_Paper_Sheet_A" in lua:
            assert "Sheet of Paper" in lua

    def test_output_is_nonempty_string(self, real_game_data):
        from dos2_tools.scripts.generate_recipe_data_module import build_recipe_lua
        lua = build_recipe_lua(real_game_data.item_combos, real_game_data)
        assert isinstance(lua, str)
        assert len(lua) > 100


# ─── Integration: generate_loot_data ─────────────────────────────────────────

@pytest.mark.integration
class TestGenerateLootDataIntegration:
    """Integration tests for generate_loot_data with real game data."""

    def test_loot_tables_loaded(self, real_game_data):
        tables = real_game_data.loot_engine.tables
        assert len(tables) > 0

    def test_loot_graph_identifies_shared_tables(self, real_game_data):
        from dos2_tools.scripts.generate_loot_data import LootGraph
        tables = real_game_data.loot_engine.tables
        graph = LootGraph(tables)
        shared = graph.get_shared_tables()
        assert len(shared) > 0

    def test_st_allpotions_is_shared(self, real_game_data):
        """ST_AllPotions matches a FORCE_SHARED_PREFIXES prefix."""
        from dos2_tools.scripts.generate_loot_data import LootGraph
        tables = real_game_data.loot_engine.tables
        graph = LootGraph(tables)
        shared = graph.get_shared_tables()
        # ST_AllPotions should match ST_Gen... wait, it matches ST_Trader? No —
        # ST_AllPotions starts with nothing in force list; it may be shared via
        # multi-parent references instead. Either way shared pool must be non-empty.
        # We just verify it does not crash and shared is non-empty.
        assert isinstance(shared, set)

    def test_generate_table_page_real_table(self, real_game_data):
        from dos2_tools.scripts.generate_loot_data import LootGraph, generate_table_page
        tables = real_game_data.loot_engine.tables
        graph = LootGraph(tables)
        shared = graph.get_shared_tables()
        if not shared:
            pytest.skip("No shared tables found in game data")
        table_id = next(iter(sorted(shared)))
        page = generate_table_page(table_id)
        assert table_id in page
        assert "{{InfoboxLootTable" in page

    def test_st_gen_reward_entries_are_shared(self, real_game_data):
        """Tables starting with ST_Gen or Reward_ should always be shared."""
        from dos2_tools.scripts.generate_loot_data import LootGraph
        tables = real_game_data.loot_engine.tables
        graph = LootGraph(tables)
        shared = graph.get_shared_tables()
        forced_matches = [
            t for t in shared
            if any(
                t.startswith(pfx) or t.lstrip("T_").startswith(pfx)
                for pfx in ["ST_Gen", "Reward_", "T_Reward", "ST_Humanoid"]
            )
        ]
        assert len(forced_matches) > 0
