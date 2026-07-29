# Standalone mode

Run a text adventure with an LLM without the full Eli Felse framework.

## Setup

```bash
git clone https://github.com/ella0333/Eli_Felse_Text_RPG.git
cd Eli_Felse_Text_RPG
python -m venv .venv
.venv\Scripts\activate        # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python standalone_setup.py
```

The standalone setup wizard checks that dfrotz is available (bundled on Windows,
auto-installed on Mac/Linux via `setup_dfrotz.py`) and then configures your model
connection.

Zork I is bundled and pre-registered, so you can play immediately after setup.

To add more games:
```bash
python setup_game.py
```

### standalone_setup.py

Configures your LLM connection. Creates `standalone_config.yaml` with:

- **Provider**: LM Studio, Ollama, OpenRouter, OpenAI, or custom URL
- **API key**: required for cloud providers, usually empty for local
- **Model name**: the exact model ID your backend serves
- **Max context tokens**: how much history to keep (default 36000)
- **System prompt**: instructions for how the LLM plays (default provided)

The same model requirements apply as
[Eli Felse Base](https://github.com/ella0333/Eli_Felse_Base) - any model that supports
OpenAI-compatible chat completions will work. See the
[Model Options Guide](https://github.com/ella0333/Eli_Felse_Base/blob/main/docs/model-options.md)
for recommendations. Recommended: 8B+ parameter models with good instruction following.

### setup_game.py

Run each time you add a new game file to `games/`. Registers the game with a
name, description, and optional hints. Bundled games (Zork I) are already
registered.

## Playing

```bash
python standalone.py
```

The LLM plays autonomously:
1. Receives game output
2. Decides on a command
3. Sends it to dfrotz
4. Repeats until win, loss, or Ctrl+C

Press **Ctrl+C** at any time to save and quit. The save is preserved and you'll
be offered to restore it next time.

## How it ends

The session ends when:
- The game prints a game-over message (death, win, or loss)
- You press Ctrl+C (game is saved automatically)
- The LLM returns empty responses repeatedly (fallback: sends "look")

## Config format

```yaml
provider:
  base_url: "http://127.0.0.1:1234/v1"
  api_key: ""
  model: "qwen3-8b"
  max_context_tokens: 36000
  request_timeout: 300

model_params:
  temperature: 0.7
  top_p: 0.95
  max_tokens: 3000

system_prompt: ""  # empty = use default
```

## Context management

The standalone player keeps a rolling conversation history. When it exceeds
approximately `max_context_tokens * 2` characters (rough estimate at 3 chars/token),
older exchanges are trimmed from the front while keeping the system prompt and
most recent turns.
