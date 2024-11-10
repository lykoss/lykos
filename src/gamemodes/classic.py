from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("classic", minp=4, maxp=21)
class ClassicMode(GameMode):
    """Classic game mode from before all the changes."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.abstain_enabled = False
        self.ROLE_GUIDE = {
            6:  ["wolf", "seer", "cursed villager"],
            8:  ["traitor", "harlot", "village drunk"],
            10: ["wolf(2)", "gunner"],
            12: ["werecrow", "detective"],
            15: ["wolf(3)"],
            17: ["bodyguard"],
            18: ["cursed villager(2)"],
            20: ["wolf(4)"],
        }
