"""Standalone text RPG player - run a single game session with an LLM.

The LLM plays the game autonomously until it wins, loses, or the user presses
Ctrl+C to quit. No Eli Felse Base required.

Usage:
    python standalone_setup.py   (once, to configure your model)
    python setup_game.py         (once per game, to register game files)
    python standalone.py         (play)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from dotenv import load_dotenv

from src.text_rpg.engine import TextRPGEngine, _find_dfrotz
from src.text_rpg.games import load_games_registry

MODULE_ROOT = Path(__file__).resolve().parent
GAMES_DIR = MODULE_ROOT / "games"
CONFIG_PATH = MODULE_ROOT / "standalone_config.yaml"
SAVES_DIR = MODULE_ROOT / "saves"

DEFAULT_SYSTEM_PROMPT = """\
You are playing a text adventure game. You will receive game output and must \
respond with parser commands to interact with the world.

Guidelines:
- Send one command at a time (e.g. "go north", "take lamp", "examine table")
- Pay attention to your surroundings and inventory
- Try different approaches if you get stuck
- Remember locations you've visited and items you've seen
- Common commands: look, inventory, examine [thing], go [direction], take [thing], \
open [thing], read [thing], use [thing] with [thing]

You must respond in JSON with this exact structure:
{"thinking": "<your reasoning about what to do>", "command": "<game command>", "return_to_menu": false}

Set return_to_menu to true only if you want to stop playing entirely."""

# Game-over detection phrases
GAME_OVER_PHRASES = [
    "you have died", "you are dead", "game over",
    "*** you have won ***", "you have lost", "the end",
    "*** you have died ***",
]

# The game_command JSON schema - matches the base registry's schema exactly.
GAME_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "thinking": {"type": "string"},
        "command": {"type": "string"},
        "return_to_menu": {"type": "boolean"},
    },
    "required": ["thinking", "command", "return_to_menu"],
    "additionalProperties": False,
}

# Hosts that speak the Anthropic Messages API instead of OpenAI chat completions.
_ANTHROPIC_HOSTS = {"api.anthropic.com"}

# Regexes to extract the offending parameter from provider error messages.
_BAD_PARAM_RE = re.compile(
    r"[Uu]n(?:known|supported) (?:parameter|value):?\s*'?\"?(\w+)"
)
_BACKTICK_PARAM_RE = re.compile(r"`(\w+)`")

# Parameters that have a known alternate name on certain providers.
_PARAM_ALIASES: dict[str, str] = {
    "max_tokens": "max_completion_tokens",
}

# Never remove these from the payload, even on error.
_ESSENTIAL_PARAMS = {"model", "messages", "stream"}

# Maximum number of parameter-fix retries per call.
_MAX_PARAM_RETRIES = 6

# Regex to extract a JSON object from potentially wrapped text.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Harmony-style channel tags some models leak into output.
_HARMONY_RE = re.compile(r"<\|[^|]*\|>")

# Placeholder content pattern.
_PLACEHOLDER_RE = re.compile(r"^[\[\(]?[.\u2026]{2,}[\]\)]?\.?$")


def _print_system(text: str) -> None:
    """Print a framework status line, ASCII-safe."""
    line = f"[system] {text}"
    try:
        print(line)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(line.encode(enc, errors="replace").decode(enc))


def _strip_harmony_tags(text: str) -> str:
    return _HARMONY_RE.sub("", text).strip()


def _is_placeholder(text: str) -> bool:
    return not text.strip() or bool(_PLACEHOLDER_RE.match(text.strip()))


def _clean_thinking(text: str) -> str:
    """Strip mimicked '[Thinking: ...]' wrappers."""
    t = text.strip()
    nest = 0
    while t.startswith("[Thinking:"):
        t = t[len("[Thinking:"):].strip()
        nest += 1
    for _ in range(nest):
        if t.endswith("]"):
            t = t[:-1].strip()
    return t


def _parse_json(content: str) -> dict | None:
    """Parse JSON from model output, with regex fallback for chatty models."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT_RE.search(content)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _validate_response(content: str) -> dict | None:
    """Parse and validate model output against the game_command schema.

    Returns the parsed dict with cleaned fields, or None if invalid.
    """
    parsed = _parse_json(content)
    if parsed is None:
        return None

    # Strip leaked formatting tags from all string fields.
    for key, val in list(parsed.items()):
        if isinstance(val, str):
            parsed[key] = _strip_harmony_tags(val)

    # Check required fields.
    for field in ("thinking", "command", "return_to_menu"):
        if field not in parsed:
            return None

    # Command must be substantive.
    if _is_placeholder(str(parsed.get("command", ""))):
        return None

    # Clean thinking field.
    if isinstance(parsed.get("thinking"), str):
        parsed["thinking"] = _clean_thinking(parsed["thinking"])

    return parsed


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("Error: standalone_config.yaml not found.")
        print("Run 'python standalone_setup.py' first.")
        sys.exit(1)

    # Load .env for API key resolution (matches base pattern).
    env_path = MODULE_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _resolve_api_key(provider: dict) -> str:
    """Resolve the API key from an env var name (base pattern) or direct value (legacy)."""
    # Base pattern: api_key_env holds the NAME of the env var.
    env_name = provider.get("api_key_env", "")
    if env_name:
        val = os.environ.get(env_name, "")
        if not val:
            print(f"Warning: api_key_env '{env_name}' is set but the environment "
                  f"variable is empty. Add it to your .env file.")
        return val

    # Legacy fallback: direct api_key in config (old standalone_config format).
    return provider.get("api_key", "")


def _is_anthropic_host(base_url: str) -> bool:
    """Auto-detect Anthropic API by hostname."""
    host = (urlparse(base_url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _ANTHROPIC_HOSTS)


def _get_model_params(config: dict, model: str) -> dict:
    """Get model params, falling back to 'default' entry (matches base pattern)."""
    params = config.get("model_params", {})
    if isinstance(params, dict):
        # New format: keyed by model name with "default" fallback.
        if model in params:
            return params[model]
        if "default" in params:
            return params["default"]
        # Legacy format: flat dict of params (no model key nesting).
        if "temperature" in params:
            return params
    return {"temperature": 0.7, "top_p": 0.95, "max_tokens": 3000}


def _build_openai_payload(
    model: str, messages: list, params: dict, schema: dict,
    blocked_params: set, param_renames: dict,
) -> dict:
    """Build an OpenAI-compatible chat completions payload."""
    candidates = {
        "temperature": params.get("temperature", 0.7),
        "top_p": params.get("top_p", 0.95),
        "max_tokens": params.get("max_tokens", 3000),
    }
    if params.get("repeat_penalty"):
        candidates["repeat_penalty"] = params["repeat_penalty"]
    if params.get("top_k"):
        candidates["top_k"] = params["top_k"]

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    for key, value in candidates.items():
        if key not in blocked_params:
            payload[key] = value

    # JSON schema for structured output.
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": "response", "strict": True, "schema": schema},
    }

    # Apply any param renames learned from previous errors.
    for old, new in param_renames.items():
        if old in payload:
            payload[new] = payload.pop(old)

    return payload


def _build_anthropic_payload(
    model: str, messages: list, params: dict, schema: dict,
    blocked_params: set,
) -> dict:
    """Build an Anthropic Messages API payload with forced tool_use for structured output."""
    # Separate system messages from chat messages.
    system_parts: list[str] = []
    chat_msgs: list[dict] = []
    for msg in messages:
        if msg["role"] == "system":
            content = msg["content"]
            if isinstance(content, str):
                system_parts.append(content)
        else:
            chat_msgs.append({"role": msg["role"], "content": msg["content"]})

    # Merge consecutive same-role messages (Anthropic requires alternation).
    merged: list[dict] = []
    for msg in chat_msgs:
        if merged and merged[-1]["role"] == msg["role"]:
            prev = merged[-1]["content"]
            cur = msg["content"]
            if isinstance(prev, str) and isinstance(cur, str):
                merged[-1]["content"] = prev + "\n\n" + cur
            else:
                merged[-1]["content"] = str(prev) + "\n\n" + str(cur)
        else:
            merged.append(dict(msg))

    # Anthropic requires messages to start with 'user'.
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(continue)"})
    if not merged:
        merged.append({"role": "user", "content": "(continue)"})

    payload = {
        "model": model,
        "messages": merged,
        "max_tokens": params.get("max_tokens", 3000),
        "stream": False,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    if "temperature" not in blocked_params:
        payload["temperature"] = params.get("temperature", 0.7)
    if "top_p" not in blocked_params and params.get("top_p"):
        payload["top_p"] = params["top_p"]
    if "top_k" not in blocked_params and params.get("top_k"):
        payload["top_k"] = params["top_k"]

    # Structured output via forced tool use.
    payload["tools"] = [{
        "name": "response",
        "description": "Respond with the required structured data.",
        "input_schema": schema,
    }]
    payload["tool_choice"] = {"type": "tool", "name": "response"}

    return payload


def _parse_openai_response(data: dict) -> str | None:
    """Extract content text from an OpenAI chat completions response."""
    try:
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        # Qwen thinking mode: actual answer may land in reasoning_content.
        if not content and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return content
    except (KeyError, IndexError, TypeError):
        return None


def _parse_anthropic_response(data: dict) -> str | None:
    """Extract content from an Anthropic Messages API response."""
    # Check for error envelope.
    if isinstance(data, dict) and data.get("type") == "error":
        return None
    for block in data.get("content", []):
        if block.get("type") == "tool_use":
            return json.dumps(block.get("input", {}))
        if block.get("type") == "text":
            return block.get("text", "")
    return None


def _strip_model_prefix(model: str) -> str | None:
    """Strip publisher prefix (e.g. 'openai/gpt-4o' -> 'gpt-4o')."""
    if "/" not in model:
        return None
    stripped = model.split("/", 1)[1]
    return stripped if stripped != model else None


def _try_fix_param(
    error_text: str, payload: dict,
    blocked_params: set, param_renames: dict,
) -> bool:
    """Attempt to fix a parameter error in-place. Returns True if fixed."""
    m = _BAD_PARAM_RE.search(error_text)
    if not m:
        m = _BACKTICK_PARAM_RE.search(error_text)
    if not m:
        return False
    bad_param = m.group(1)
    if bad_param in _ESSENTIAL_PARAMS:
        return False

    # Try renaming to a known alias first.
    alias = _PARAM_ALIASES.get(bad_param)
    if alias and bad_param not in param_renames:
        param_renames[bad_param] = alias
        if bad_param in payload:
            payload[alias] = payload.pop(bad_param)
        _print_system(f"Parameter '{bad_param}' not supported; using '{alias}' instead")
        return True

    # Otherwise remove it entirely.
    if bad_param not in blocked_params:
        blocked_params.add(bad_param)
        payload.pop(bad_param, None)
        for orig, renamed in param_renames.items():
            if orig == bad_param:
                payload.pop(renamed, None)
        _print_system(f"Parameter '{bad_param}' not supported; removed")
        return True

    return False


async def llm_command(
    client: httpx.AsyncClient,
    config: dict,
    messages: list,
    *,
    is_anthropic: bool,
    blocked_params: set,
    param_renames: dict,
    model_stripped: dict,
) -> dict | None:
    """Send messages to the LLM and get back a validated game_command dict.

    Returns the parsed dict with 'thinking', 'command', and 'return_to_menu',
    or None on failure.
    """
    provider = config["provider"]
    model = provider["model"]
    params = _get_model_params(config, model)
    api_key = _resolve_api_key(provider)

    # Use a previously resolved stripped model name if available.
    effective_model = model_stripped.get(model, model)

    if is_anthropic:
        base_url = provider["base_url"].rstrip("/")
        url = f"{base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if api_key:
            headers["x-api-key"] = api_key
        payload = _build_anthropic_payload(
            effective_model, messages, params, GAME_COMMAND_SCHEMA, blocked_params,
        )
    else:
        base_url = provider["base_url"].rstrip("/")
        # Normalize: ensure the URL ends with /v1.
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = _build_openai_payload(
            effective_model, messages, params, GAME_COMMAND_SCHEMA,
            blocked_params, param_renames,
        )

    timeout = provider.get("request_timeout", 300)

    for _attempt in range(_MAX_PARAM_RETRIES):
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.HTTPError as e:
            _print_system(f"Connection error: {e}")
            return None

        # Check for errors that we can auto-fix.
        if resp.status_code in (400, 404):
            error_text = resp.text[:500]
            error_lower = error_text.lower()

            # Auto-fix: invalid model ID - strip publisher prefix.
            if ("invalid model" in error_lower
                    or "not_found" in error_lower
                    or "could not resolve" in error_lower):
                stripped = _strip_model_prefix(payload.get("model", ""))
                if stripped:
                    _print_system(
                        f"Model '{payload['model']}' rejected; retrying as '{stripped}'"
                    )
                    model_stripped[model] = stripped
                    payload["model"] = stripped
                    continue
                break

            # Auto-fix: rejected parameter.
            if ("unknown parameter" in error_lower
                    or "unsupported parameter" in error_lower
                    or "unsupported value" in error_lower
                    or "deprecated" in error_lower
                    or "not supported" in error_lower):
                if _try_fix_param(error_text, payload, blocked_params, param_renames):
                    continue
                break

            break

        if resp.status_code != 200:
            _print_system(f"LLM error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()

        # Check for error in response body.
        if isinstance(data, dict) and "error" in data and "choices" not in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            _print_system(f"LLM error: {msg[:200]}")
            return None

        # Parse response based on provider type.
        if is_anthropic:
            content = _parse_anthropic_response(data)
        else:
            content = _parse_openai_response(data)

        if content is None:
            _print_system("Unexpected response shape")
            return None

        # Validate against schema.
        result = _validate_response(content)
        if result is not None:
            return result

        _print_system("Response rejected (malformed/missing fields), retrying...")
        # Rebuild payload for retry (same params).
        if is_anthropic:
            payload = _build_anthropic_payload(
                effective_model, messages, params, GAME_COMMAND_SCHEMA, blocked_params,
            )
        else:
            payload = _build_openai_payload(
                effective_model, messages, params, GAME_COMMAND_SCHEMA,
                blocked_params, param_renames,
            )

    return None


def select_game(games: list) -> int:
    """Let the user pick which game to play."""
    if len(games) == 1:
        print(f"\n  Game: {games[0].name}")
        print(f"  {games[0].description}\n")
        return 0

    print("\n  Available games:\n")
    for i, g in enumerate(games, 1):
        print(f"  {i}. {g.name} - {g.description}")
    print()

    while True:
        choice = input(f"  Select game (1-{len(games)}): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(games):
                return idx
        except ValueError:
            pass
        print("  Invalid selection.")


async def play(config: dict, game_idx: int):
    """Main game loop - LLM plays until game over or Ctrl+C."""
    games = load_games_registry(GAMES_DIR)
    game = games[game_idx]

    dfrotz_path = _find_dfrotz(MODULE_ROOT, config.get("dfrotz_path"))
    save_dir = SAVES_DIR / game.key
    engine = TextRPGEngine(game.file_path, save_dir, dfrotz_path)

    # Detect provider type.
    provider = config["provider"]
    base_url = provider["base_url"]
    is_anthropic = _is_anthropic_host(base_url)

    # Auto-enable /no_think for Qwen models (matches base behavior).
    quirks = provider.get("quirks", {})
    no_think_suffix = quirks.get("no_think_suffix", False)
    if "qwen" in provider.get("model", "").lower() and not no_think_suffix:
        no_think_suffix = True
        _print_system("Qwen model detected, auto-enabled /no_think suffix")

    # Shared state for param auto-fix across calls (matches base pattern).
    blocked_params: set[str] = set()
    param_renames: dict[str, str] = {}
    model_stripped: dict[str, str] = {}

    # Check for existing saves
    restore_file = None
    if engine.has_save_files():
        saves = engine.get_save_files()
        print(f"\n  Found {len(saves)} save(s) for {game.name}:")
        for i, s in enumerate(saves[:5], 1):
            score_str = f" (Score: {s['score']})" if s["score"] else ""
            print(f"    {i}. {s['filename']} - {s['date']} {s['time']}{score_str}")
        print(f"    {len(saves[:5]) + 1}. Start new game")
        print()
        while True:
            choice = input(f"  Select (1-{len(saves[:5]) + 1}): ").strip()
            try:
                idx = int(choice) - 1
                if idx == len(saves[:5]):
                    break  # new game
                if 0 <= idx < len(saves[:5]):
                    restore_file = saves[idx]["filename"]
                    break
            except ValueError:
                pass

    print(f"\n  Starting {game.name}...")
    print("  Press Ctrl+C at any time to save and quit.\n")
    print("  " + "\u2500" * 60 + "\n")

    output = await engine.start(restore_filename=restore_file)
    print(f"  {output}\n")

    # Build message history for the LLM
    system_prompt = config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    if game.hints:
        system_prompt += f"\n\nGame-specific hints: {game.hints}"

    first_user_content = f"Game: {game.name}\n\n{output}"
    if no_think_suffix:
        first_user_content += " /no_think"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": first_user_content},
    ]

    turn_count = 0
    async with httpx.AsyncClient() as client:
        try:
            while True:
                # Get command from LLM
                result = await llm_command(
                    client, config, messages,
                    is_anthropic=is_anthropic,
                    blocked_params=blocked_params,
                    param_renames=param_renames,
                    model_stripped=model_stripped,
                )

                if result is None:
                    _print_system("LLM returned no valid response - retrying with 'look'")
                    command = "look"
                else:
                    # Display thinking if present
                    if result.get("thinking"):
                        print(f"\n  Thinking: {result['thinking']}")

                    # Check return_to_menu
                    if result.get("return_to_menu"):
                        print("\n  LLM decided to stop playing.")
                        await engine.save_and_quit(game.key)
                        score_str = f" Score: {engine.last_score}" if engine.last_score else ""
                        print(f"  Saved and quit after {turn_count} turns.{score_str}")
                        return

                    command = str(result.get("command", "look")).strip()

                print(f"  > {command}")
                turn_count += 1

                # Send to game
                response = await engine.send_command(command)
                engine.parse_score_from_output(response)
                print(f"  {response}\n")

                # Check for game over
                response_lower = response.lower()
                if any(phrase in response_lower for phrase in GAME_OVER_PHRASES):
                    score_str = f" Final score: {engine.last_score}" if engine.last_score else ""
                    print(f"  {'\u2500' * 60}")
                    print(f"  Game ended after {turn_count} turns.{score_str}")
                    await engine.quit_no_save()
                    return

                # Update conversation history
                # Store the command as the assistant message (not the full JSON).
                messages.append({"role": "assistant", "content": command})
                user_content = response
                if no_think_suffix:
                    user_content += " /no_think"
                messages.append({"role": "user", "content": user_content})

                # Trim history if too long (keep system + last N exchanges)
                max_context = provider.get("max_context_tokens", 36000)
                # Rough estimate: 3 chars per token
                total_chars = sum(len(m["content"]) for m in messages)
                while total_chars > max_context * 2 and len(messages) > 5:
                    messages.pop(1)
                    messages.pop(1)
                    total_chars = sum(len(m["content"]) for m in messages)

        except KeyboardInterrupt:
            print(f"\n\n  Interrupted - saving game...")
            await engine.save_and_quit(game.key)
            score_str = f" Score: {engine.last_score}" if engine.last_score else ""
            print(f"  Saved and quit after {turn_count} turns.{score_str}")


def main():
    config = load_config()
    games = load_games_registry(GAMES_DIR)

    if not games:
        print("\nNo games registered. Run 'python setup_game.py' first.")
        print(f"Place game files (.z3/.z5/.z8/.zblorb) in: {GAMES_DIR}")
        sys.exit(1)

    print("\n\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557")
    print("\u2551   Text RPG - Standalone Player      \u2551")
    print("\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d")

    game_idx = select_game(games)
    asyncio.run(play(config, game_idx))


if __name__ == "__main__":
    main()
