"""Setup wizard for adding games to the Text RPG module.

Run this each time you add a new game file to the games/ folder.
It registers the game with a name, description, and optional hints
so the agent knows what it's playing.
"""

import re
import sys
from pathlib import Path

from src.text_rpg.games import load_games_registry, save_games_registry, GameInfo

MODULE_ROOT = Path(__file__).resolve().parent
GAMES_DIR = MODULE_ROOT / "games"

# Supported Z-machine extensions
Z_EXTENSIONS = {".z1", ".z2", ".z3", ".z4", ".z5", ".z6", ".z7", ".z8", ".zblorb", ".dat"}


def _find_game_files() -> list[Path]:
    """Find all Z-machine game files in games/ not yet registered."""
    existing = load_games_registry(GAMES_DIR)
    registered_files = {Path(g.file_path).name for g in existing}
    found = []
    for f in sorted(GAMES_DIR.iterdir()):
        if f.suffix.lower() in Z_EXTENSIONS and f.name not in registered_files:
            found.append(f)
    return found


def _make_key(name: str) -> str:
    """Generate a short key from the game name."""
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return key[:20]


def main():
    print("\n╔══════════════════════════════════════╗")
    print("║   Text RPG - Add Game Wizard         ║")
    print("╚══════════════════════════════════════╝\n")

    unregistered = _find_game_files()

    if not unregistered:
        print("No new game files found in games/ folder.")
        print(f"Place .z3/.z5/.z8/.zblorb files in: {GAMES_DIR}")
        print("\nAlready registered games:")
        existing = load_games_registry(GAMES_DIR)
        if existing:
            for g in existing:
                print(f"  - {g.name} ({g.key})")
        else:
            print("  (none)")
        return

    print(f"Found {len(unregistered)} new game file(s):\n")
    for i, f in enumerate(unregistered, 1):
        print(f"  {i}. {f.name}")

    print()

    for game_file in unregistered:
        print(f"─── Setting up: {game_file.name} ───\n")

        # Game name
        default_name = game_file.stem.replace("_", " ").replace("-", " ").title()
        name = input(f"  Game name [{default_name}]: ").strip()
        if not name:
            name = default_name

        # Description
        description = input("  Game description (shown in selection menu): ").strip()
        while not description:
            description = input("  Description cannot be empty: ").strip()

        # Hints
        hints = input("  Additional hints for the AI (optional, press Enter to skip): ").strip()

        # Key
        key = _make_key(name)
        print(f"\n  Key: {key}")
        print(f"  Name: {name}")
        print(f"  Description: {description}")
        if hints:
            print(f"  Hints: {hints}")

        confirm = input("\n  Save this game? [Y/n]: ").strip().lower()
        if confirm and confirm != "y":
            print("  Skipped.\n")
            continue

        # Save
        existing = load_games_registry(GAMES_DIR)
        existing.append(GameInfo(
            key=key,
            name=name,
            description=description,
            file_path=game_file.name,  # relative to games/
            hints=hints,
        ))
        save_games_registry(GAMES_DIR, existing)
        print(f"  Added '{name}' to registry.\n")

    print("Done. Games are ready to play.")


if __name__ == "__main__":
    main()
