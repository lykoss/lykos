from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("foolish", minp=8, maxp=24)
class FoolishMode(GameMode):
    """Contains the fool, be careful not to vote them!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            8:  ["wolf", "traitor", "oracle", "harlot", "fool", "cursed villager"],
            9:  ["hunter"],
            10: ["wolf(2)"],
            11: ["shaman", "clone"],
            12: ["wolf cub", "gunner/sharpshooter"],
            15: ["sorcerer", "augur", "mayor"],
            17: ["wolf(3)", "harlot(2)"],
            20: ["bodyguard"],
            21: ["traitor(2)"],
            22: ["gunner/sharpshooter(2)"],
            24: ["wolf(4)"],
        }
