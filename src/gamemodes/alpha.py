from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("alpha", minp=10, maxp=24)
class AlphaMode(GameMode):
    """Features the alpha wolf who can turn other people into wolves, be careful whom you trust!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            10: ["alpha wolf", "traitor", "oracle", "harlot", "doctor", "amnesiac", "lycan", "lycan(2)", "cursed villager"],
            12: ["werecrow", "guardian angel"],
            13: ["vigilante", "mayor", "cursed villager(2)"],
            14: ["wolf"],
            16: ["crazed shaman", "matchmaker"],
            17: ["augur"],
            18: ["wolf(2)"],
            19: ["assassin"],
            20: ["clone", "lycan(3)"],
            21: ["vengeful ghost"],
            22: ["wolf(3)", "cursed villager(3)"],
            24: ["wolf(4)", "guardian angel(2)"],
        }
