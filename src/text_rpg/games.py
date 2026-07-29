"""Game registry - reads games.json from the games/ folder.

Each game entry has: key, name, description, file_path, and optional hints.
The setup wizard writes to this file when adding new games.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class GameInfo:
    key: str
    name: str
    description: str
    file_path: str
    hints: str = ""


def load_games_registry(games_dir: Path) -> List[GameInfo]:
    """Load all registered games from games/games.json."""
    registry_path = games_dir / "games.json"
    if not registry_path.exists():
        return []
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        games = []
        for entry in data.get("games", []):
            # Resolve file path relative to games dir
            file_path = entry.get("file_path", "")
            if not Path(file_path).is_absolute():
                file_path = str(games_dir / file_path)
            if not Path(file_path).exists():
                continue  # Skip games whose files are missing
            games.append(GameInfo(
                key=entry["key"],
                name=entry["name"],
                description=entry["description"],
                file_path=file_path,
                hints=entry.get("hints", ""),
            ))
        return games
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def save_games_registry(games_dir: Path, games: List[GameInfo]) -> None:
    """Write the games registry back to games/games.json."""
    games_dir.mkdir(parents=True, exist_ok=True)
    registry_path = games_dir / "games.json"
    data = {
        "games": [
            {
                "key": g.key,
                "name": g.name,
                "description": g.description,
                "file_path": g.file_path,
                "hints": g.hints,
            }
            for g in games
        ]
    }
    registry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
