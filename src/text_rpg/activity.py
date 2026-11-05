"""Text RPG Activity - the Eli Felse module interface.

Registers as a drop-in activity. Provides:
- Dynamic main-menu label showing installed game count
- Sub-menu for game selection (with descriptions)
- New game / restore save menu per game
- Single-step game loop with command interception for save/restore
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .engine import TextRPGEngine, _find_dfrotz
from .games import load_games_registry, GameInfo

if TYPE_CHECKING:
    from elifelse.activities.ctx import ActivityContext
    from elifelse.persona import Persona

try:
    from elifelse.activities.base import Activity
except ImportError:
    # Standalone mode - provide a stub
    class Activity:
        key = ""
        menu_label = ""
        menu_group = ""
        requires = []
        requires_base = ""
        schemas = {}
        isolate_context = False
        memory_rules = ""
        survey = None

        def get_menu_label(self, ctx): return self.menu_label
        def get_status(self, ctx): return ""
        def get_prompt(self, persona): return ""
        def available(self, ctx): return True
        async def startup(self, ctx): pass
        async def run(self, ctx): pass


# Pattern for valid interactive fiction commands
_IF_COMMAND_PATTERN = re.compile(
    r"^[a-zA-Z][a-zA-Z0-9 ,.'\"!\-?/]*$"
)

MODULE_ROOT = Path(__file__).resolve().parent.parent.parent

# Schema key in the base registry
_GAME_COMMAND_SCHEMA = "game_command"


def _build_recent_steps_recap(
    context_since_last_save: list[dict[str, str]],
    max_steps: int = 8,
) -> str:
    """Build a condensed recap of the last N command/response pairs."""
    pairs: list[str] = []
    i = 0
    while i + 1 < len(context_since_last_save):
        cmd_entry = context_since_last_save[i]
        output_entry = context_since_last_save[i + 1]
        if cmd_entry.get("role") == "assistant" and output_entry.get("role") == "user":
            cmd = cmd_entry.get("content", "").strip()
            output = output_entry.get("content", "").strip()
            first_line = output.split("\n")[0][:120]
            pairs.append(f"> {cmd} → {first_line}")
        i += 2
    recent = pairs[-max_steps:]
    return "\n".join(recent)


def _save_label(save: dict[str, Any]) -> str:
    """One save-file menu line: filename, when it was made, score if known."""
    score_str = f" (Score: {save['score']})" if save["score"] else ""
    return f"{save['filename']} - {save['date']} {save['time']}{score_str}"


def _extract_save_filename(save_result: str) -> str:
    """Pull the filename from engine.save_game() output like '[Game saved: zork_20250720_143000.sav]'."""
    m = re.search(r"\[Game saved:\s*(.+?)\]", save_result)
    return m.group(1).strip() if m else ""


class TextRPGActivity(Activity):
    key = "text_rpg"
    menu_label = "Text Adventure"
    menu_group = "Play a Video Game"
    requires_base = ">=0.5,<1"
    isolate_context = True
    memory_mode = "game_batch"  # 3-msg merge extraction, no classifier
    memory_rules = (
        "Extract what happened in the game: locations visited, items found, "
        "puzzles solved or failed, deaths, and the agent's strategy or feelings "
        "about the game. Include the game name and final score if available."
    )
    survey = None

    def get_prompt(self, persona: Persona) -> str:
        """Return empty so the base identity prompt stays until run() sets
        the full system prompt (base identity + RPG guidance + menu)."""
        return ""

    def _rpg_guidance(self) -> str:
        """RPG-specific guidance block (appended to base identity prompt)."""
        return (
            "You are currently playing a text-based RPG. "
            "This is a fictional game you are playing. These are not real actions "
            "happening to you but to the game character you are playing as.\n\n"
            "Important: React to what happened. Before deciding your next command, "
            "briefly acknowledge what just happened in the game. If your previous "
            "action failed, note why. If something unexpected occurred, react to it. "
            "If you died, express frustration or surprise. If you discovered something, "
            "show curiosity. Don't just announce your next action; show that you "
            "understood and processed the game's response.\n\n"
            "*** Saving your game ***\n"
            "To save: type SAVE as your entire command by itself, not combined with "
            "any other command. It does not count as an in-game move, and the game "
            "continues right where you left off afterward.\n"
            "Important: Never append SAVE to another command. Always send SAVE as a "
            "completely separate, standalone command on its own turn.\n"
            "When you quit (return_to_menu: true), the game auto-saves, so there "
            "is no need to save right before quitting.\n\n"
            "To restore a previous save: type RESTORE as your entire command."
        )

    def get_menu_label(self, ctx: ActivityContext) -> str:
        games = load_games_registry(MODULE_ROOT / "games")
        names = [g.name for g in games[:3]]
        if names:
            listing = ", ".join(names)
            return f"Text Adventure ({listing})"
        return "Text Adventure"

    def get_status(self, ctx: ActivityContext) -> str:
        games = load_games_registry(MODULE_ROOT / "games")
        total = len(games)
        if total == 0:
            return "no games installed"
        # Once it has played, the base's "last: X ago" line is the useful one;
        # before that, show what's installed.
        last_played = super().get_status(ctx)
        if last_played:
            return last_played
        return f"{total} game{'s' if total != 1 else ''} available"

    def available(self, ctx: ActivityContext) -> bool:
        games = load_games_registry(MODULE_ROOT / "games")
        return len(games) > 0

    def _build_menu_preview(self, ctx: ActivityContext) -> str:
        try:
            entries = ctx.app.registry.menu_entries()
        except Exception:
            return ""
        if not entries:
            return ""
        lines = [
            "Available menu options (for reference only \u2014 not available "
            "during this activity, listed so you know what to do after "
            "returning to menu):"
        ]
        for i, entry in enumerate(entries):
            letter = chr(ord("A") + i)
            status = f" ({entry['status']})" if entry.get("status") else ""
            lines.append(f"{letter}) {entry['label']}{status}")
        lines.append(
            "\nYou must return to menu if you want to choose another menu "
            "option. If you would like to stop the current task and go do "
            "another task from the menu, you must set return_to_menu to true."
        )
        return "\n".join(lines)

    async def run(self, ctx: ActivityContext) -> str:
        games = load_games_registry(MODULE_ROOT / "games")
        if not games:
            return "No games installed."

        # Build full system prompt: base identity + RPG guidance + menu preview
        parts = [ctx.app.base_prompt(), self._rpg_guidance()]
        menu_preview = self._build_menu_preview(ctx)
        if menu_preview:
            parts.append(menu_preview)
        ctx.app.provider.set_system_prompt("\n\n".join(parts))

        # ── Game selection sub-menu ───────────────────────────────────────
        if len(games) == 1:
            selected = games[0]
        else:
            choice = await ctx.choose(
                "Which text adventure would you like to play?",
                options=[g.key for g in games],
                labels=[f"{g.name} - {g.description}" for g in games],
            )
            selected = next(g for g in games if g.key == choice)

        # ── New game or restore save ─────────────────────────────────────
        dfrotz_path = _find_dfrotz(
            MODULE_ROOT, ctx.config.get("dfrotz_path")
        )
        save_dir = ctx.data_dir / "saves" / selected.key
        engine = TextRPGEngine(selected.file_path, save_dir, dfrotz_path)

        start_choice = "new_game"
        if engine.has_save_files():
            start_choice = await ctx.choose(
                f"Starting {selected.name}. New game or restore a save?",
                options=["new_game", "restore_save"],
                labels=["Start a new game", "Restore a previous save"],
            )

        restore_file = None
        active_save_filename = ""
        if start_choice == "restore_save":
            saves = engine.get_save_files()[:10]
            restore_file = await ctx.choose(
                "Which save?",
                options=[s["filename"] for s in saves],
                labels=[_save_label(s) for s in saves],
            )
            active_save_filename = restore_file

        # ── Start the game ────────────────────────────────────────────────
        ctx.set_status(f"Playing {selected.name}")
        output = await engine.start(restore_filename=restore_file)

        # ── State tracking ────────────────────────────────────────────────
        turn_count = 0
        last_output = output
        context_since_last_save: list[dict[str, str]] = []

        # Fetch the game_command schema from the base registry
        game_schema = ctx.schemas.get(_GAME_COMMAND_SCHEMA)

        # Build first-turn game context
        hints = f"\nHints: {selected.hints}" if selected.hints else ""
        game_context = (
            f"You are playing '{selected.name}', a text adventure game.\n"
            f"Description: {selected.description}{hints}\n\n"
            "Send parser commands like: go north, take lamp, open mailbox, "
            "examine room, inventory, look, etc.\n\n"
            f"Current game output:\n{output}"
        )

        # ── Game loop ─────────────────────────────────────────────────────
        while True:
            result = await ctx.generate(game_context, schema=game_schema)

            if result.get("thinking"):
                print(f"\nThinking: {result['thinking']}")

            # Check return_to_menu
            if result.get("return_to_menu"):
                await engine.save_and_quit(selected.key)
                score_str = f" Score: {engine.last_score}" if engine.last_score else ""
                return f"Played {selected.name} for {turn_count} turns.{score_str}"

            command = str(result.get("command", "look")).strip()
            print(f"Command: {command}")
            command_lower = command.lower()

            # ── Intercept save ────────────────────────────────────────────
            if command_lower == "save":
                save_result = await engine.save_game(selected.key)
                fn = _extract_save_filename(save_result)
                if fn:
                    active_save_filename = fn
                context_since_last_save = []
                print(f"\n{save_result}")
                game_context = (
                    f"{save_result}\n\nGame saved! What's your next command?\n"
                    f"[Reminder: set return_to_menu: true to save and exit the game]\n\n"
                    f"Current game output:\n{last_output}"
                )
                continue

            # ── Intercept restore ─────────────────────────────────────────
            if command_lower == "restore":
                saves = engine.get_save_files()
                if not saves:
                    game_context = (
                        "[No save files available to restore]\n\n"
                        f"Current game output:\n{last_output}"
                    )
                    continue
                saves = saves[:10]
                restore_choice = await ctx.choose(
                    "Which save to restore?",
                    options=[s["filename"] for s in saves],
                    labels=[_save_label(s) for s in saves],
                )
                restore_result = await engine.restore_game(restore_choice)
                active_save_filename = restore_choice
                context_since_last_save = []
                last_output = restore_result
                print(f"\n{restore_result}")
                game_context = (
                    f"Restored save: {restore_choice}\n\n"
                    f"Current game output:\n{restore_result}\n\n"
                    "What's your next command?"
                )
                continue

            # ── Normal command ────────────────────────────────────────────
            response = await engine.send_command(command)
            engine.parse_score_from_output(response)
            turn_count += 1
            last_output = response
            print(f"\nGame:\n{response}")

            # Track context for recent steps recap
            context_since_last_save.append({"role": "assistant", "content": command})
            context_since_last_save.append({"role": "user", "content": response})

            # Push command + output to game memory (3-msg merge) with save state
            current_save = active_save_filename or "unsaved"
            ctx.remember_game("assistant", command, subject=selected.key, save_state=current_save)
            ctx.remember_game("user", response, subject=selected.key, save_state=current_save)

            # Recall past gameplay memories for richer context
            recall_query = f"{command}\n{response}"
            recalled = await ctx.recall(recall_query, source=selected.key)
            if recalled:
                memory_lines = "\n".join(f"- {m}" for m in recalled)
                memory_note = f"\n\n[Relevant past gameplay memories:\n{memory_lines}]"
            else:
                memory_note = ""

            # Check for game over signals
            response_lower = response.lower()
            if any(phrase in response_lower for phrase in [
                "would you like to restart",
                "restart, restore",
                "restart or restore",
                "you have died", "you are dead", "game over",
                "*** you have won ***", "you have lost",
            ]):
                engine.parse_score_from_output(response)
                await engine.quit_no_save()
                score_str = f" Final score: {engine.last_score}" if engine.last_score else ""
                return (
                    f"Finished {selected.name} after {turn_count} turns.{score_str}"
                )

            # Build recent steps recap
            recent_steps = _build_recent_steps_recap(context_since_last_save)
            recent_steps_block = ""
            if recent_steps:
                recent_steps_block = (
                    "\n\nRecent steps (what happened since your last save / "
                    "since you started, do not repeat actions listed here):\n"
                    f"{recent_steps}"
                )

            game_context = (
                f"You sent: {command}\n\n"
                f"Game response:\n{response}{memory_note}"
                f"{recent_steps_block}\n\n"
                "What's your next command?"
            )
