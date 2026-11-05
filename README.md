# Eli Felse | Text RPG

[![MIT License](https://img.shields.io/badge/MIT_License-869b9f?style=flat)](LICENSE)

!["Eli" Chibi Character with grey hair and green eyes, and grey x hair clip, playing with a game controller in hand](https://i.imgur.com/t2oM0l0.png)

**A module for [Eli Felse Base](https://github.com/ella0333/Eli_Felse_Base) that lets
an AI play retro text adventure games like Zork, Hitchhiker's Guide, Planetfall,
and hundreds more.**

## Quick start

```bash
cd Eli_Felse_Base
.venv\Scripts\activate        # Windows   (Mac/Linux: source .venv/bin/activate)
git clone https://github.com/ella0333/Eli_Felse_Text_RPG.git data/modules/text_rpg
cd data/modules/text_rpg
pip install -r requirements.txt
python setup_dfrotz.py        # Skip for Windows (Mac/Linux: installs dfrotz)
cd ../Eli_Felse_Base          # to Eli_Felse_Base
elifelse run
```

"Text Adventure" will appear under "Play a Video Game" in the activity menu, with
Zork I ready to play.

Requires base **0.5.0 or newer**.

To add more games, place `.z3` / `.z5` / `.z8` files in `games/` and run:

```bash
python setup_game.py
```

The wizard registers each game with a name, description, and optional hints for the AI.
See **[adding games](docs/adding-games.md)** for details and where to find game files.

To remove a game, delete its file from the `games/` folder. The module skips any
registered game whose file is missing, so it will disappear from the menu automatically.
You can also remove its entry from `games/games.json` to clean up the registry.

New to all of this? Follow the **[base project's guide](https://github.com/ella0333/Eli_Felse_Base/blob/master/docs/getting-started.md)** and come back here when you are finished

Need help choosing a compatible model? See the 
**[Model Options Guide](https://github.com/ella0333/Eli_Felse_Base/blob/master/docs/model-options.md)**

## Standalone text RPG harness

You can also run this module without the Eli Felse framework. Connect any
**[compatible model](https://github.com/ella0333/Eli_Felse_Base/blob/master/docs/model-options.md)** and let it play a game directly.

```bash
git clone https://github.com/ella0333/Eli_Felse_Text_RPG.git
cd Eli_Felse_Text_RPG
python -m venv .venv
.venv\Scripts\activate        # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python standalone_setup.py    # configures model connection + checks dfrotz
python standalone.py
```

The model plays autonomously. Press `Ctrl+C` at any time to save and quit.

## Platform support

Built and tested on **Windows** where dfrotz is bundled and works out of the box.
Should work on **macOS** and **Linux** too,
run `python setup_dfrotz.py` to install dfrotz via your package manager or compile from source.

## Docs

- **[Adding games](docs/adding-games.md):** game files, the setup wizard, and recommendations
- **[Standalone mode](docs/standalone-mode.md):** standalone harness setup and how sessions work
- **[Module integration](docs/module-integration.md):** how it plugs into the base, menus, config

## Learn More about the Project

Meet Eli Felse, a framework built to explore safer ways to create autonomous AI assistants.
Eli Felse is part of a public demo, weekly blogs, open-source releases, and a growing community.

**[24/7 live public demo](https://elifelse.org/eli/)**

**[Introduction Blog](https://elifelse.org/dev-blog/meet-eli)**

**[Join the Discord community](https://discord.com/invite/2C4znNnyM7)**

## Third-party licenses

This project is licensed under the [MIT License](LICENSE). It bundles the
following third-party components under their own licenses:

| Component | License | Details |
|-----------|---------|---------|
| **[dfrotz](https://gitlab.com/DavidGriffith/frotz)**| GPL v2 or later | [licenses/FROTZ_LICENSE](licenses/FROTZ_LICENSE) · Source: [gitlab.com/DavidGriffith/frotz](https://gitlab.com/DavidGriffith/frotz) |
| **Zork I**| MIT (Copyright Microsoft) | [licenses/ZORK_LICENSE](licenses/ZORK_LICENSE) · Source: [github.com/historicalsource/zork1](https://github.com/historicalsource/zork1) |

Full license texts are in the [`licenses/`](licenses/) directory.

---

[![elif else](https://img.shields.io/badge/elif_else-869b9f?style=flat)](https://elifelse.org/)
[![MIT License](https://img.shields.io/badge/MIT_License-869b9f?style=flat)](LICENSE)
