# Module integration

How the Text RPG module plugs into
[Eli Felse Base](https://github.com/ella0333/Eli_Felse_Base).

If you haven't set up the base yet, follow the
[Getting Started Guide](https://github.com/ella0333/Eli_Felse_Base/blob/main/docs/getting-started.md)
first.

## Installation

```bash
cd Eli_Felse_Base
.venv\Scripts\activate        # Windows   (Mac/Linux: source .venv/bin/activate)
git clone https://github.com/ella0333/Eli_Felse_Text_RPG.git data/modules/text_rpg
cd data/modules/text_rpg
pip install -r requirements.txt
```

On Mac/Linux, also run `python setup_dfrotz.py` to install the Z-machine interpreter.
On Windows, dfrotz is bundled in `bin/windows/` and works out of the box.

Zork I is bundled and pre-registered, so the module is ready to use immediately.
Run `elifelse run` and "Text RPG" will appear in the activity menu.

The base framework auto-discovers modules in `data/modules/`. On next startup it will
find `text_rpg/__init__.py`, read the `ACTIVITIES` list, and register `TextRPGActivity`.

## Menu structure

The module creates a dynamic main-menu entry:

```
Play a Text RPG (Zork, Planetfall, Wishbringer)
```

Up to 3 game names are shown in parentheses. If only one game is installed, it still
appears in the label.

The status shown after the label is the base's "last: X ago" line once the agent has
played; before that it shows how many games are installed.

### Sub-menus

Every sub-menu goes through the base's `ctx.choose(question, options, labels=...)`,
which letters it (`A) ...`) and locks the schema enum to the letters, so the agent
answers `A`/`B`/`C` and never has to reproduce a game key or a save filename.

1. **Game selection** - shown if multiple games are registered. Displays each game's
   name and description.
2. **New game / Restore save** - per-game choice. Only offered if saves exist.
3. **Save selection** - if restoring, lists saves with date, time, and score.
4. **Turn actions** - each turn the agent chooses: `command`, `save`, `restore`, or `quit`.

This mirrors how other Eli activities work: the agent picks from validated options and
never constructs raw menu JSON.

## Config

Add an optional section to your `config.yaml`:

```yaml
activities:
  text_rpg:
    dfrotz_path: ""   # leave empty to auto-detect
```

If `dfrotz_path` is empty, the module searches:
1. `bin/windows/dfrotz.exe` (Windows) or `bin/dfrotz` (Mac/Linux)
2. Module root folder (legacy: `data/modules/text_rpg/dfrotz.exe`)
3. System PATH

## Data storage

Saves go in `data/text_rpg/saves/<game_key>/`. Each save has a `.sav` file and a
`.meta` JSON file recording date, time, score, and moves.

## Context isolation

`isolate_context = True` - the framework snapshots context before the game starts and
restores it after, so game transcripts don't pollute the agent's general memory window.

## Memory extraction

After each session, the framework extracts memories using the module's `memory_rules`:
locations visited, items found, puzzles solved/failed, deaths, strategy, and final score.

## Schema

Commands are validated via `ctx.constrained()` against:
```
[a-zA-Z][a-zA-Z0-9 ,.'\"!\-?/]*
```

This covers all standard interactive fiction parser commands while rejecting dangerous
input (no semicolons, pipes, backticks, or control characters).
