# Adding games

How to install and register game files for the Text RPG module.

## Bundled games

**Zork I: The Great Underground Empire** is included in the `games/` folder and
pre-registered in `games/games.json`. It's ready to play immediately after cloning.

## Supported formats

Any Z-machine game file works:
- `.z3` - Z-machine version 3 (early Infocom: Zork I, Deadline)
- `.z5` - Z-machine version 5 (later Infocom: Wishbringer, A Mind Forever Voyaging)
- `.z8` - Z-machine version 8 (modern IF)
- `.zblorb` - Blorb-wrapped Z-machine (modern IF with embedded resources)
- `.dat` - some older distributions use this extension

## Recommended games

These work well with AI players. Game files can be found on the
[IF Archive](https://ifarchive.org/indexes/if-archive/games/zcode/) and
[historicalsource](https://github.com/historicalsource) on GitHub.

| Game | Format | Notes |
|------|--------|-------|
| Zork I | .z3 | Bundled. Classic treasure hunt in the Great Underground Empire |
| Zork II | .z3 | Sequel with trickier puzzles and the Wizard of Frobozz |
| Zork III | .z3 | Final chapter, more puzzle-focused than its predecessors |
| Planetfall | .z3 | Sci-fi adventure with a memorable robot companion |
| The Hitchhiker's Guide to the Galaxy | .z5 | Notoriously tricky adaptation of the Douglas Adams novel |
| Curses | .z5 | Explore your family's attic and its connections to history |
| Anchorhead | .z8 | Lovecraftian horror set in a New England coastal town |

## Installation steps

1. **Place the game file** in the `games/` folder:
   ```
   Eli_Felse_Text_RPG/
   └── games/
       ├── zork1.z3          (bundled)
       ├── hitchhiker.z5     (your files)
       └── games.json
   ```

2. **Run the setup wizard**:
   ```bash
   python setup_game.py
   ```

3. **Answer the prompts**:
   - **Game file name** - auto-detected from new files in `games/`
   - **Game name** - display name (e.g. "Zork I: The Great Underground Empire")
   - **Description** - one line shown in the game selection menu
   - **Hints** - optional context for the AI (e.g. "This is a treasure hunt game.
     The goal is to collect all 20 treasures and return them to the trophy case.")

## The games registry

The wizard writes to `games/games.json`:

```json
{
  "games": [
    {
      "key": "zork_i",
      "name": "Zork I: The Great Underground Empire",
      "description": "A treasure hunt in the Great Underground Empire.",
      "file_path": "zork1.z3",
      "hints": "Collect 20 treasures. Return them to the trophy case in the living room."
    }
  ]
}
```

You can also edit this file manually if you prefer.

## Re-running the wizard

The wizard only prompts for files that aren't already registered. Run it again
any time you add new game files - it won't overwrite existing entries.

## Removing a game

Delete its entry from `games/games.json`. Optionally remove the game file from
`games/` and its saves from `data/text_rpg/saves/<key>/` (module mode) or
`saves/<key>/` (standalone mode).
