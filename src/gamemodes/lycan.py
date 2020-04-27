from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("lycan", minp=7, maxp=24, likelihood=5)
class LycanMode(GameMode):
    """Many lycans will turn into wolves. Hunt them down before the wolves overpower the village."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            7:  ["wolf", "seer", "hunter", "lycan", "cursed villager"],
            8:  ["wolf(2)"],
            9:  ["clone"],
            10: ["wolf shaman", "hunter(2)"],
            11: ["bodyguard", "mayor"],
            12: ["lycan(2)", "cursed villager(2)"],
            15: ["tough wolf", "hunter(3)"],
            17: ["lycan(3)", "gunner/sharpshooter"],
            19: ["seer(2)"],
            20: ["lycan(4)"],
            22: ["wolf shaman(2)", "hunter(4)"]
        }
