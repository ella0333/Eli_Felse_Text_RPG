"""Eli Felse Text RPG - drop-in module entry point.

When installed at data/modules/text_rpg/, the base framework auto-discovers
this file and reads the ACTIVITIES list to register the activity.
"""

from .src.text_rpg.activity import TextRPGActivity

ACTIVITIES = [TextRPGActivity]
