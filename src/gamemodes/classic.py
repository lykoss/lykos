from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("classic", minp=4, maxp=21, likelihood=0)
class ClassicMode(GameMode):
    """Classic game mode from before all the changes."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ABSTAIN_ENABLED = False
        self.ROLE_GUIDE = {
            4:  ["wolf", "seer"],
            6:  ["cursed villager"],
            8:  ["traitor", "harlot", "village drunk"],
            10: ["wolf(2)", "gunner"],
            12: ["werecrow", "detective"],
            15: ["wolf(3)"],
            17: ["bodyguard"],
            18: ["cursed villager(2)"],
            20: ["wolf(4)"],
        }
