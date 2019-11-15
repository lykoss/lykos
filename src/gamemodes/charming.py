from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("charming", minp=6, maxp=24, likelihood=5)
class CharmingMode(GameMode):
    """Charmed players must band together to find the piper in this game mode."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            6:  ["wolf", "seer", "piper", "cursed villager"],
            8:  ["traitor", "harlot"],
            10: ["werekitten", "shaman", "gunner/sharpshooter"],
            11: ["vengeful ghost"],
            12: ["warlock", "detective"],
            14: ["bodyguard", "mayor"],
            16: ["wolf(2)", "assassin"],
            18: ["bodyguard(2)"],
            19: ["sorcerer"],
            22: ["wolf(3)", "shaman(2)"],
            24: ["gunner/sharpshooter(2)"],
        }
        self.ROLE_SETS = {
            "gunner/sharpshooter": {"gunner": 8, "sharpshooter": 2},
        }
