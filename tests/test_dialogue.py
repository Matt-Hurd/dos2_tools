"""
Tests for the dialogue parser module.

Includes both:
  - Unit tests with inline JSON fixtures
  - Integration tests using real extracted game data
"""

import os
import json
import pytest
import tempfile

from dos2_tools.core.dialogue import (
    DialogueNode,
    Dialogue,
    parse_dialogue_file,
    flatten_dialogue_paths,
    render_dialogue_tree,
    format_transcript,
    _extract_text,
    _extract_children,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

MINIMAL_DIALOGUE_JSON = {
    "save": {
        "header": {"version": "2.0.8.2"},
        "regions": {
            "dialog": {
                "UUID": {"type": 22, "value": "test-dialog-uuid"},
                "category": {"type": 23, "value": "Test Dialog"},
                "nodes": [
                    {
                        "RootNodes": [
                            {"RootNodes": {"type": 22, "value": "node-greeting"}}
                        ],
                        "node": [
                            {
                                "UUID": {"type": 22, "value": "node-greeting"},
                                "speaker": {"type": 4, "value": 0},
                                "constructor": {"type": 22, "value": "TagGreeting"},
                                "endnode": {"type": 19, "value": 0},
                                "ShowOnce": {"type": 19, "value": 0},
                                "TaggedTexts": [
                                    {
                                        "TaggedText": [
                                            {
                                                "HasTagRule": {"type": 19, "value": 1},
                                                "RuleGroup": [{"Rules": [{}], "TagCombineOp": {"type": 1, "value": 0}}],
                                                "TagTexts": [
                                                    {
                                                        "TagText": [
                                                            {
                                                                "TagText": {
                                                                    "handle": "h-test-greeting",
                                                                    "type": 28,
                                                                    "value": "Hello there, traveler!"
                                                                },
                                                                "stub": {"type": 19, "value": 1}
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ],
                                "Tags": [{}],
                                "addressedspeaker": {"type": 4, "value": -1},
                                "checkflags": [{}],
                                "children": [
                                    {
                                        "child": [
                                            {"UUID": {"type": 22, "value": "node-player-choice-1"}},
                                            {"UUID": {"type": 22, "value": "node-player-choice-2"}}
                                        ]
                                    }
                                ],
                                "setflags": [{}],
                                "GameData": [{"Emotion": {"type": 23, "value": "Happy"}}],
                                "stub": {"type": 19, "value": 1},
                                "transitionmode": {"type": 1, "value": 0},
                                "waittime": {"type": 6, "value": -1.0},
                                "exclusive": {"type": 19, "value": 0},
                                "optional": {"type": 19, "value": 0}
                            },
                            {
                                "UUID": {"type": 22, "value": "node-player-choice-1"},
                                "speaker": {"type": 4, "value": 1},
                                "constructor": {"type": 22, "value": "TagQuestion"},
                                "endnode": {"type": 19, "value": 0},
                                "ShowOnce": {"type": 19, "value": 0},
                                "TaggedTexts": [
                                    {
                                        "TaggedText": [
                                            {
                                                "HasTagRule": {"type": 19, "value": 1},
                                                "RuleGroup": [{"Rules": [{}], "TagCombineOp": {"type": 1, "value": 0}}],
                                                "TagTexts": [
                                                    {
                                                        "TagText": [
                                                            {
                                                                "TagText": {
                                                                    "handle": "h-test-choice1",
                                                                    "type": 28,
                                                                    "value": "Tell me more."
                                                                },
                                                                "stub": {"type": 19, "value": 1}
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ],
                                "Tags": [{}],
                                "addressedspeaker": {"type": 4, "value": -1},
                                "checkflags": [{}],
                                "children": [
                                    {
                                        "child": [
                                            {"UUID": {"type": 22, "value": "node-npc-reply"}}
                                        ]
                                    }
                                ],
                                "setflags": [{}],
                                "GameData": [{}],
                                "stub": {"type": 19, "value": 1},
                                "transitionmode": {"type": 1, "value": 0},
                                "waittime": {"type": 6, "value": -1.0},
                                "exclusive": {"type": 19, "value": 0},
                                "optional": {"type": 19, "value": 0}
                            },
                            {
                                "UUID": {"type": 22, "value": "node-player-choice-2"},
                                "speaker": {"type": 4, "value": 1},
                                "constructor": {"type": 22, "value": "TagQuestion"},
                                "endnode": {"type": 19, "value": 1},
                                "ShowOnce": {"type": 19, "value": 0},
                                "TaggedTexts": [
                                    {
                                        "TaggedText": [
                                            {
                                                "HasTagRule": {"type": 19, "value": 1},
                                                "RuleGroup": [{"Rules": [{}], "TagCombineOp": {"type": 1, "value": 0}}],
                                                "TagTexts": [
                                                    {
                                                        "TagText": [
                                                            {
                                                                "TagText": {
                                                                    "handle": "h-test-choice2",
                                                                    "type": 28,
                                                                    "value": "Goodbye."
                                                                },
                                                                "stub": {"type": 19, "value": 1}
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ],
                                "Tags": [{}],
                                "addressedspeaker": {"type": 4, "value": -1},
                                "checkflags": [{}],
                                "children": [{}],
                                "setflags": [{}],
                                "GameData": [{}],
                                "stub": {"type": 19, "value": 1},
                                "transitionmode": {"type": 1, "value": 0},
                                "waittime": {"type": 6, "value": -1.0},
                                "exclusive": {"type": 19, "value": 0},
                                "optional": {"type": 19, "value": 0}
                            },
                            {
                                "UUID": {"type": 22, "value": "node-npc-reply"},
                                "speaker": {"type": 4, "value": 0},
                                "constructor": {"type": 22, "value": "TagAnswer"},
                                "endnode": {"type": 19, "value": 1},
                                "ShowOnce": {"type": 19, "value": 0},
                                "TaggedTexts": [
                                    {
                                        "TaggedText": [
                                            {
                                                "HasTagRule": {"type": 19, "value": 1},
                                                "RuleGroup": [{"Rules": [{}], "TagCombineOp": {"type": 1, "value": 0}}],
                                                "TagTexts": [
                                                    {
                                                        "TagText": [
                                                            {
                                                                "TagText": {
                                                                    "handle": "h-test-reply",
                                                                    "type": 28,
                                                                    "value": "It's a long story, friend."
                                                                },
                                                                "stub": {"type": 19, "value": 1}
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ],
                                "Tags": [{}],
                                "addressedspeaker": {"type": 4, "value": -1},
                                "checkflags": [{}],
                                "children": [{}],
                                "setflags": [{}],
                                "GameData": [{"Emotion": {"type": 23, "value": "Default"}}],
                                "stub": {"type": 19, "value": 1},
                                "transitionmode": {"type": 1, "value": 0},
                                "waittime": {"type": 6, "value": -1.0},
                                "exclusive": {"type": 19, "value": 0},
                                "optional": {"type": 19, "value": 0}
                            }
                        ]
                    }
                ],
                "speakerlist": [
                    {
                        "speaker": [
                            {"index": {"type": 22, "value": "0"}, "list": {"type": 23, "value": "npc-uuid-1234"}},
                            {"index": {"type": 22, "value": "1"}, "list": {"type": 23, "value": "player-uuid-5678"}}
                        ]
                    }
                ]
            }
        },
        "editorData": {"needLayout": {"type": 19, "value": 0}, "nextNodeId": {"type": 5, "value": 5}}
    }
}


@pytest.fixture
def minimal_dialogue_file(tmp_path):
    """Write the minimal dialogue JSON to a temp file and return its path."""
    fp = tmp_path / "test_dialogue.lsj"
    fp.write_text(json.dumps(MINIMAL_DIALOGUE_JSON), encoding="utf-8")
    return str(fp)


# ─── Unit Tests: Text Extraction ────────────────────────────────────────────


class TestExtractText:
    def test_basic_extraction(self):
        node = MINIMAL_DIALOGUE_JSON["save"]["regions"]["dialog"]["nodes"][0]["node"][0]
        text, handle = _extract_text(node)
        assert text == "Hello there, traveler!"
        assert handle == "h-test-greeting"

    def test_empty_tagged_texts(self):
        text, handle = _extract_text({"TaggedTexts": [{}]})
        assert text == ""
        assert handle == ""

    def test_missing_tagged_texts(self):
        text, handle = _extract_text({})
        assert text == ""
        assert handle == ""


# ─── Unit Tests: Children Extraction ────────────────────────────────────────


class TestExtractChildren:
    def test_basic_children(self):
        node = MINIMAL_DIALOGUE_JSON["save"]["regions"]["dialog"]["nodes"][0]["node"][0]
        children = _extract_children(node)
        assert len(children) == 2
        assert "node-player-choice-1" in children
        assert "node-player-choice-2" in children

    def test_empty_children(self):
        children = _extract_children({"children": [{}]})
        assert children == []


# ─── Unit Tests: Parsing ────────────────────────────────────────────────────


class TestParseDialogueFile:
    def test_parse_minimal(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        assert d is not None
        assert d.uuid == "test-dialog-uuid"
        assert d.category == "Test Dialog"
        assert len(d.root_node_uuids) == 1
        assert d.root_node_uuids[0] == "node-greeting"

    def test_speakers(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        assert 0 in d.speakers
        assert d.speakers[0] == "npc-uuid-1234"
        assert d.speakers[1] == "player-uuid-5678"

    def test_node_types(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        assert d.nodes["node-greeting"].constructor == "TagGreeting"
        assert d.nodes["node-player-choice-1"].constructor == "TagQuestion"
        assert d.nodes["node-npc-reply"].constructor == "TagAnswer"

    def test_node_text(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        assert d.nodes["node-greeting"].text == "Hello there, traveler!"
        assert d.nodes["node-player-choice-1"].text == "Tell me more."
        assert d.nodes["node-player-choice-2"].text == "Goodbye."
        assert d.nodes["node-npc-reply"].text == "It's a long story, friend."

    def test_end_nodes(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        assert not d.nodes["node-greeting"].is_end
        assert not d.nodes["node-player-choice-1"].is_end
        assert d.nodes["node-player-choice-2"].is_end
        assert d.nodes["node-npc-reply"].is_end

    def test_emotion(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        assert d.nodes["node-greeting"].emotion == "Happy"
        assert d.nodes["node-npc-reply"].emotion == "Default"

    def test_nonexistent_file(self, tmp_path):
        result = parse_dialogue_file(str(tmp_path / "nonexistent.lsj"))
        assert result is None


# ─── Unit Tests: Tree Traversal ─────────────────────────────────────────────


class TestFlattenPaths:
    def test_path_count(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        paths = flatten_dialogue_paths(d)
        # Two paths: greeting -> choice1 -> reply, greeting -> choice2
        assert len(paths) == 2

    def test_path_content(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        paths = flatten_dialogue_paths(d)

        # Path 1: greeting -> tell me more -> long story
        path1 = paths[0]
        assert path1[0].text == "Hello there, traveler!"
        assert path1[1].text == "Tell me more."
        assert path1[2].text == "It's a long story, friend."

        # Path 2: greeting -> goodbye
        path2 = paths[1]
        assert path2[0].text == "Hello there, traveler!"
        assert path2[1].text == "Goodbye."

    def test_empty_dialogue(self):
        d = Dialogue(
            uuid="empty", category="", source_file="",
            root_node_uuids=[], nodes={}, speakers={}
        )
        paths = flatten_dialogue_paths(d)
        assert paths == []

    def test_cycle_detection(self):
        """Ensure cycles don't cause infinite recursion."""
        nodes = {
            "a": DialogueNode(
                uuid="a", speaker_index=0, constructor="TagAnswer",
                text="Node A", text_handle="", children=["b"],
                is_end=False
            ),
            "b": DialogueNode(
                uuid="b", speaker_index=0, constructor="TagAnswer",
                text="Node B", text_handle="", children=["a"],
                is_end=False
            ),
        }
        d = Dialogue(
            uuid="cycle", category="", source_file="",
            root_node_uuids=["a"], nodes=nodes, speakers={}
        )
        paths = flatten_dialogue_paths(d)
        assert len(paths) >= 1
        # Should terminate without hanging


# ─── Unit Tests: Tree Rendering ─────────────────────────────────────────────


class TestRenderTree:
    def test_basic_tree(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        speaker_names = {"npc-uuid-1234": "Test NPC"}
        lines = render_dialogue_tree(d, speaker_names)

        joined = "\n".join(lines)
        assert "Test NPC" in joined
        assert "Hello there, traveler!" in joined
        assert "Player" in joined
        assert "Tell me more." in joined
        assert "Goodbye." in joined
        assert "long story" in joined

    def test_indentation_increases_at_branch(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        lines = render_dialogue_tree(d, {})
        # Greeting is at depth 0 → "* ..."
        # Two choices branch → "** ..."
        assert any(line.startswith("* ") for line in lines)
        assert any(line.startswith("** ") for line in lines)

    def test_linear_chain_same_depth(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        lines = render_dialogue_tree(d, {})
        # choice1 ("Tell me more") → reply ("long story") is linear,
        # so they should be at the same depth (both **)
        choice1_line = [l for l in lines if "Tell me more" in l]
        reply_line = [l for l in lines if "long story" in l]
        assert choice1_line and reply_line
        # Count leading asterisks
        choice1_depth = len(choice1_line[0]) - len(choice1_line[0].lstrip("*"))
        reply_depth = len(reply_line[0]) - len(reply_line[0].lstrip("*"))
        assert choice1_depth == reply_depth

    def test_format_transcript_wrapper(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        result = format_transcript(d, {"npc-uuid-1234": "Test NPC"})
        assert "Test NPC" in result
        assert "Test Dialog" in result  # category in header

    def test_unknown_speaker(self, minimal_dialogue_file):
        d = parse_dialogue_file(minimal_dialogue_file)
        result = format_transcript(d, {})
        # Should still produce output with fallback speaker labels
        assert "Speaker 0" in result


# ─── Integration Tests (real game data) ─────────────────────────────────────


DASHING_JUNE_DIALOGUE = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "exported", "Patch4", "Mods",
    "DivinityOrigins_1301db3d-1f54-4e98-9be5-5094030916e4",
    "Story", "Dialogs", "RC_Driftwood", "RC_DW_CommonerDwarf_05.lsj"
)


@pytest.mark.skipif(
    not os.path.exists(DASHING_JUNE_DIALOGUE),
    reason="Real game data not available"
)
class TestRealDialogue:
    def test_parse_dashing_june(self):
        d = parse_dialogue_file(DASHING_JUNE_DIALOGUE)
        assert d is not None
        assert len(d.nodes) > 0
        assert len(d.root_node_uuids) > 0

    def test_speaker_is_dashing_june(self):
        d = parse_dialogue_file(DASHING_JUNE_DIALOGUE)
        # Speaker 0 should map to Dashing June's MapKey UUID
        assert 0 in d.speakers
        assert d.speakers[0] == "f627dac6-365a-4d8d-b33b-10fc63ffbe30"

    def test_contains_known_line(self):
        d = parse_dialogue_file(DASHING_JUNE_DIALOGUE)
        texts = [node.text for node in d.nodes.values()]
        assert any("Lucian's legs" in t for t in texts)

    def test_tree_rendering(self):
        d = parse_dialogue_file(DASHING_JUNE_DIALOGUE)
        lines = render_dialogue_tree(d, {})
        assert len(lines) > 0
        # Tree should have multiple depth levels
        depths = set()
        for line in lines:
            depth = len(line) - len(line.lstrip("*"))
            depths.add(depth)
        assert len(depths) > 1  # At least root + one branch level

    def test_transcript_generation(self):
        d = parse_dialogue_file(DASHING_JUNE_DIALOGUE)
        speaker_names = {
            "f627dac6-365a-4d8d-b33b-10fc63ffbe30": "Dashing June"
        }
        result = format_transcript(d, speaker_names)
        assert "Dashing June" in result
        assert len(result) > 100  # Should be substantial
