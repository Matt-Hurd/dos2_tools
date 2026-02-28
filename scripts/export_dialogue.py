"""
Export NPC dialogue transcripts from DOS2 game data.

Parses all dialogue .lsj files, resolves speaker names, and writes
per-NPC transcript files as indented dialogue trees.

Usage:
    python -m dos2_tools.scripts.export_dialogue
    python -m dos2_tools.scripts.export_dialogue --npc "Dashing June"
    python -m dos2_tools.scripts.export_dialogue --output-dir dialogue_export/ --format md
"""

import os
import re
import sys
import argparse
from collections import defaultdict

from dos2_tools.core.game_data import GameData
from dos2_tools.core.dialogue import (
    parse_dialogue_file,
    build_speaker_map,
    render_dialogue_tree,
    format_transcript,
)


def sanitize_filename(name):
    """Convert NPC name to a safe filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def format_transcript_md(dialogue, speaker_names):
    """Format a dialogue as a Markdown indented tree."""
    tree_lines = render_dialogue_tree(dialogue, speaker_names)
    if not tree_lines:
        return ""

    lines = []
    source_basename = os.path.basename(dialogue.source_file)
    lines.append(f"=== {source_basename} ===")
    lines.append(f"''Category: {dialogue.category or 'Unknown'}''")
    lines.append("")
    lines.extend(tree_lines)
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Export DOS2 NPC dialogue transcripts."
    )
    parser.add_argument(
        "--output-dir", default="dialogue_export",
        help="Directory to write transcript files (default: dialogue_export/)"
    )
    parser.add_argument(
        "--npc", default=None,
        help="Export only dialogues for a specific NPC (by display name)"
    )
    parser.add_argument(
        "--format", choices=["txt", "md"], default="txt",
        help="Output format (default: txt)"
    )
    parser.add_argument(
        "--single-file", action="store_true",
        help="Write all transcripts to a single file instead of per-NPC"
    )
    parser.add_argument(
        "--list-npcs", action="store_true",
        help="List all NPCs that have dialogue and exit"
    )
    args = parser.parse_args()

    # Load game data
    print("Loading game data...")
    game = GameData()

    # Get all dialogue files
    print("Finding dialogue files...")
    dialogue_entries = game.get_files("dialogue_files")
    print(f"Found {len(dialogue_entries)} dialogue files")

    # Build speaker name map
    print("Building speaker name map from character data...")
    speaker_names = build_speaker_map(game)
    print(f"Resolved {len(speaker_names)} speaker names")

    # Parse all dialogue files
    print("Parsing dialogue files...")
    dialogues = []
    errors = 0
    for i, entry in enumerate(dialogue_entries, 1):
        if i % 100 == 0:
            print(f"  Parsing {i}/{len(dialogue_entries)}...", end="\r")
        path = entry.resolved_path if hasattr(entry, "resolved_path") else entry
        try:
            d = parse_dialogue_file(path)
            if d and d.nodes:
                dialogues.append(d)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Warning: Failed to parse {path}: {e}")
    print(f"Parsed {len(dialogues)} dialogues ({errors} errors)          ")

    # Group dialogues by NPC speaker
    npc_dialogues = defaultdict(list)   # display_name -> [Dialogue]
    for d in dialogues:
        for idx, speaker_uuid in d.speakers.items():
            name = speaker_names.get(speaker_uuid)
            if name:
                npc_dialogues[name].append(d)
                break  # Primary speaker (index 0 usually)
            else:
                # Use the UUID as a fallback key
                npc_dialogues[f"Unknown ({speaker_uuid[:12]}...)"].append(d)
                break

    print(f"Found {len(npc_dialogues)} unique NPC speakers")

    # --list-npcs mode
    if args.list_npcs:
        for name in sorted(npc_dialogues.keys()):
            count = len(npc_dialogues[name])
            print(f"  {name}: {count} dialogue(s)")
        return

    # Filter by NPC name if requested
    if args.npc:
        matches = {k: v for k, v in npc_dialogues.items()
                   if args.npc.lower() in k.lower()}
        if not matches:
            print(f"No dialogues found for NPC matching '{args.npc}'")
            print("Use --list-npcs to see available NPCs")
            sys.exit(1)
        npc_dialogues = matches
        print(f"Filtered to {len(npc_dialogues)} NPC(s) matching '{args.npc}'")

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Export
    ext = f".{args.format}"
    total_files = 0

    if args.single_file:
        outpath = os.path.join(args.output_dir, f"all_dialogue{ext}")
        with open(outpath, "w", encoding="utf-8") as f:
            for name in sorted(npc_dialogues.keys()):
                if args.format == "md":
                    f.write(f"# {name}\n\n")
                else:
                    f.write(f"{'=' * 60}\n")
                    f.write(f"NPC: {name}\n")
                    f.write(f"{'=' * 60}\n\n")

                for d in npc_dialogues[name]:
                    if args.format == "md":
                        f.write(format_transcript_md(d, speaker_names))
                    else:
                        f.write(format_transcript(d, speaker_names))
                    f.write("\n")
        print(f"Wrote {outpath}")
        total_files = 1
    else:
        for name in sorted(npc_dialogues.keys()):
            filename = sanitize_filename(name) + ext
            outpath = os.path.join(args.output_dir, filename)

            with open(outpath, "w", encoding="utf-8") as f:
                if args.format == "md":
                    f.write(f"# {name} — Dialogue Transcript\n\n")
                    for d in npc_dialogues[name]:
                        f.write(format_transcript_md(d, speaker_names))
                        f.write("\n")
                else:
                    for d in npc_dialogues[name]:
                        f.write(format_transcript(d, speaker_names))
                        f.write("\n")

            total_files += 1

    print(f"Exported {total_files} transcript file(s) to {args.output_dir}/")


if __name__ == "__main__":
    main()
