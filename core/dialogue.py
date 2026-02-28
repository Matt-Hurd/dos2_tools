"""
Dialogue parser for DOS2 game data.

Parses .lsj dialogue files into structured dialogue trees and provides
utilities for flattening them into readable transcripts.

Dialogue structure:
  - Each .lsj file represents one conversation
  - Nodes are stored in a flat list with UUID-based parent/child links
  - A speakerlist maps integer indices to character MapKey UUIDs
  - Node types: TagAnswer (NPC speech), TagQuestion (player choice),
    TagGreeting (NPC greeting/initiation)
  - Speaker names are resolved by matching MapKey UUIDs against
    character instances in level Characters/_merged.lsj files
"""

from dataclasses import dataclass, field
from dos2_tools.core.parsers import parse_lsj


# ─── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class DialogueNode:
    """A single node in a dialogue tree."""

    uuid: str
    speaker_index: int
    constructor: str  # TagAnswer, TagQuestion, TagGreeting, etc.
    text: str
    text_handle: str
    children: list  # list of child node UUIDs
    is_end: bool
    check_flags: list = field(default_factory=list)
    set_flags: list = field(default_factory=list)
    emotion: str = "Default"
    show_once: bool = False


@dataclass
class Dialogue:
    """A complete parsed conversation."""

    uuid: str
    category: str
    source_file: str
    root_node_uuids: list  # entry point UUIDs
    nodes: dict  # uuid -> DialogueNode
    speakers: dict  # int index -> character MapKey UUID


# ─── Parsing ────────────────────────────────────────────────────────────────


def _extract_text(node_data):
    """Extract dialogue text and handle from a node's TaggedTexts."""
    tagged_texts = node_data.get("TaggedTexts", [{}])
    if not tagged_texts or tagged_texts == [{}]:
        return "", ""

    for tt_group in tagged_texts:
        for tagged_text in tt_group.get("TaggedText", []):
            tag_texts = tagged_text.get("TagTexts", [{}])
            for tt in tag_texts:
                for tag_text_entry in tt.get("TagText", []):
                    tag_text = tag_text_entry.get("TagText", {})
                    if isinstance(tag_text, dict):
                        text = tag_text.get("value", "")
                        handle = tag_text.get("handle", "")
                        return text, handle
    return "", ""


def _extract_check_flags(node_data):
    """Extract check flags (conditions) from a node."""
    flags = []
    check_flags = node_data.get("checkflags", [{}])
    if check_flags == [{}]:
        return flags
    for flag_group in check_flags:
        for flag in flag_group.get("flagcheck", []):
            flag_info = {
                "flag": flag.get("flag", {}).get("value", ""),
                "value": flag.get("value", {}).get("value", True),
            }
            if flag_info["flag"]:
                flags.append(flag_info)
    return flags


def _extract_set_flags(node_data):
    """Extract set flags (effects) from a node."""
    flags = []
    set_flags = node_data.get("setflags", [{}])
    if set_flags == [{}]:
        return flags
    for flag_group in set_flags:
        for flag in flag_group.get("flagcheck", []):
            flag_info = {
                "flag": flag.get("flag", {}).get("value", ""),
                "value": flag.get("value", {}).get("value", True),
            }
            if flag_info["flag"]:
                flags.append(flag_info)
    return flags


def _extract_children(node_data):
    """Extract child node UUIDs from a node."""
    children = []
    children_data = node_data.get("children", [{}])
    if children_data == [{}]:
        return children
    for child_group in children_data:
        for child in child_group.get("child", []):
            uuid = child.get("UUID", {}).get("value", "")
            if uuid:
                children.append(uuid)
    return children


def _extract_emotion(node_data):
    """Extract emotion from GameData."""
    game_data = node_data.get("GameData", [{}])
    if game_data and game_data != [{}]:
        return game_data[0].get("Emotion", {}).get("value", "Default")
    return "Default"


def parse_dialogue_file(filepath):
    """
    Parse a .lsj dialogue file into a Dialogue object.

    Args:
        filepath: Path to the .lsj dialogue file

    Returns:
        Dialogue or None if parsing fails
    """
    data = parse_lsj(filepath)
    if not data:
        return None

    dialog = data.get("save", {}).get("regions", {}).get("dialog", {})
    if not dialog:
        return None

    # Extract dialogue metadata
    dialogue_uuid = dialog.get("UUID", {}).get("value", "")
    category = dialog.get("category", {}).get("value", "")

    # Extract root node UUIDs
    root_nodes = []
    nodes_section = dialog.get("nodes", [])
    if nodes_section:
        root_entries = nodes_section[0].get("RootNodes", [])
        if isinstance(root_entries, list):
            for entry in root_entries:
                uuid = entry.get("RootNodes", {}).get("value", "")
                if uuid:
                    root_nodes.append(uuid)

    # Extract speakerlist
    speakers = {}
    speaker_section = dialog.get("speakerlist", [])
    if speaker_section:
        for speaker_group in speaker_section:
            for speaker in speaker_group.get("speaker", []):
                index_str = speaker.get("index", {}).get("value", "")
                mapkey = speaker.get("list", {}).get("value", "")
                if index_str != "" and mapkey:
                    speakers[int(index_str)] = mapkey

    # Parse all nodes
    parsed_nodes = {}
    if nodes_section:
        node_list = nodes_section[0].get("node", [])
        for node_data in node_list:
            uuid = node_data.get("UUID", {}).get("value", "")
            if not uuid:
                continue

            text, handle = _extract_text(node_data)
            speaker_index = node_data.get("speaker", {}).get("value", -1)
            constructor = node_data.get("constructor", {}).get("value", "")
            is_end = node_data.get("endnode", {}).get("value", 0) == 1
            show_once = node_data.get("ShowOnce", {}).get("value", 0) == 1

            parsed_nodes[uuid] = DialogueNode(
                uuid=uuid,
                speaker_index=speaker_index,
                constructor=constructor,
                text=text,
                text_handle=handle,
                children=_extract_children(node_data),
                is_end=is_end,
                check_flags=_extract_check_flags(node_data),
                set_flags=_extract_set_flags(node_data),
                emotion=_extract_emotion(node_data),
                show_once=show_once,
            )

    return Dialogue(
        uuid=dialogue_uuid,
        category=category,
        source_file=filepath,
        root_node_uuids=root_nodes,
        nodes=parsed_nodes,
        speakers=speakers,
    )


# ─── Speaker Resolution ────────────────────────────────────────────────────


def build_speaker_map(game_data):
    """
    Build a MapKey UUID → display name map from all character data.

    Uses the level_characters file pattern from GameData to find all
    Characters/_merged.lsj files and extract MapKey → DisplayName mappings.

    Args:
        game_data: GameData instance (provides file_index, localization, config)

    Returns:
        dict[str, str]: MapKey UUID → display name
    """
    speaker_map = {}

    char_files = game_data.get_files("level_characters")
    for entry in char_files:
        path = entry.resolved_path if hasattr(entry, "resolved_path") else entry
        data = parse_lsj(path)
        if not data:
            continue

        # Navigate to character nodes — handles both save formats
        regions = data.get("save", {}).get("regions", {})

        # Try Templates.GameObjects format
        game_objects = (
            regions.get("Templates", {}).get("GameObjects", [])
        )
        if not game_objects:
            # Try region.node.children.node format
            region = regions.get("region", {})
            if isinstance(region, dict):
                game_objects = (
                    region.get("node", {})
                    .get("children", {})
                    .get("node", [])
                )

        if not isinstance(game_objects, list):
            game_objects = [game_objects]

        for go in game_objects:
            if not isinstance(go, dict):
                continue

            map_key = go.get("MapKey", {}).get("value", "")
            display_name_node = go.get("DisplayName", {})

            if not map_key:
                continue

            # Get display name — try value first, then resolve handle
            name = ""
            if isinstance(display_name_node, dict):
                name = display_name_node.get("value", "")
                if not name or name.startswith("|"):
                    handle = display_name_node.get("handle", "")
                    if handle and game_data.localization:
                        resolved = game_data.localization.get_handle_text(handle)
                        if resolved:
                            name = resolved

            if map_key and name and not name.startswith("|"):
                speaker_map[map_key] = name

    return speaker_map


# ─── Tree Traversal ─────────────────────────────────────────────────────────


def flatten_dialogue_paths(dialogue, max_depth=50):
    """
    Walk the dialogue tree from roots to all leaves.

    Produces a list of conversation paths, where each path is an ordered
    list of DialogueNodes from root to leaf.

    Args:
        dialogue: Dialogue object
        max_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        list[list[DialogueNode]]: All possible conversation paths
    """
    paths = []

    def _walk(node_uuid, current_path, visited, depth):
        if depth > max_depth:
            paths.append(list(current_path))
            return

        if node_uuid in visited:
            # Cycle detected — end this path
            paths.append(list(current_path))
            return

        node = dialogue.nodes.get(node_uuid)
        if not node:
            # Dangling reference — end this path
            if current_path:
                paths.append(list(current_path))
            return

        current_path.append(node)
        visited.add(node_uuid)

        if node.is_end or not node.children:
            paths.append(list(current_path))
        else:
            for child_uuid in node.children:
                _walk(child_uuid, current_path, visited, depth + 1)

        current_path.pop()
        visited.discard(node_uuid)

    for root_uuid in dialogue.root_node_uuids:
        _walk(root_uuid, [], set(), 0)

    return paths


# ─── Tree-Format Rendering ──────────────────────────────────────────────────


def _resolve_speaker_label(node, dialogue, speaker_names):
    """Resolve a human-readable speaker label for a node."""
    if node.constructor == "TagQuestion":
        return "Player"

    if node.speaker_index in (-1, -666):
        return "Narrator"

    speaker_uuid = dialogue.speakers.get(node.speaker_index, "")
    if speaker_uuid and speaker_uuid in speaker_names:
        return speaker_names[speaker_uuid]

    if speaker_uuid:
        return f"Speaker {node.speaker_index} ({speaker_uuid[:8]}...)"
    return f"Speaker {node.speaker_index}"


def _is_branching(node, dialogue):
    """Check if a node is a branching point (has multiple valid children)."""
    valid_children = [c for c in node.children if c in dialogue.nodes]
    return len(valid_children) > 1


def render_dialogue_tree(dialogue, speaker_names=None, max_depth=50):
    """
    Render a dialogue as an indented tree.

    Branches increase indentation; linear chains stay at the same depth.
    This mirrors the OSRS wiki transcript style with nested bullet points.

    Args:
        dialogue: Dialogue object
        speaker_names: dict of MapKey UUID → display name
        max_depth: Maximum recursion depth

    Returns:
        list[str]: Lines of the rendered tree
    """
    if speaker_names is None:
        speaker_names = {}

    lines = []

    def _render_node(node_uuid, depth, visited):
        if depth > max_depth or node_uuid in visited:
            return

        node = dialogue.nodes.get(node_uuid)
        if not node:
            return

        visited.add(node_uuid)
        indent = "*" * (depth + 1)

        # Emit the node's text — player choices use distinct formatting
        if node.text:
            speaker = _resolve_speaker_label(node, dialogue, speaker_names)
            if node.constructor == "TagQuestion":
                lines.append(f"{indent} '''{speaker}:''' ''{node.text}''")
            else:
                lines.append(f"{indent} '''{speaker}:''' {node.text}")

        # Annotate condition flags
        if node.check_flags:
            flag_strs = [f.get("flag", "?") for f in node.check_flags]
            lines.append(f"{indent} ''(requires: {', '.join(flag_strs)})''")

        # Process children
        valid_children = [c for c in node.children if c in dialogue.nodes]

        if len(valid_children) == 1:
            # Linear chain — same depth
            _render_node(valid_children[0], depth, visited)
        elif len(valid_children) > 1:
            # Branching point — each child gets increased depth
            for child_uuid in valid_children:
                _render_node(child_uuid, depth + 1, visited)

        visited.discard(node_uuid)

    for i, root_uuid in enumerate(dialogue.root_node_uuids):
        if i > 0:
            lines.append("")
        _render_node(root_uuid, 0, set())

    return lines


def format_transcript(dialogue, speaker_names=None):
    """
    Format a dialogue into a readable tree-format transcript.

    Args:
        dialogue: Dialogue object
        speaker_names: dict of MapKey UUID → display name

    Returns:
        str: Formatted transcript text
    """
    if speaker_names is None:
        speaker_names = {}

    tree_lines = render_dialogue_tree(dialogue, speaker_names)
    if not tree_lines:
        return ""

    header = []
    header.append(f"=== {dialogue.category or 'Dialogue'} ===")
    header.append(f"Source: {dialogue.source_file}")
    header.append("")

    return "\n".join(header + tree_lines) + "\n"


def get_dialogues_for_speaker(dialogues, speaker_uuid):
    """
    Filter dialogues to only those involving a specific speaker.

    Args:
        dialogues: list of Dialogue objects
        speaker_uuid: MapKey UUID of the speaker to filter for

    Returns:
        list[Dialogue]: Dialogues that include this speaker
    """
    result = []
    for d in dialogues:
        if speaker_uuid in d.speakers.values():
            result.append(d)
    return result

