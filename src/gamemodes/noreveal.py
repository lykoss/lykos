from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("noreveal", minp=6, maxp=21)
class NoRevealMode(GameMode):
    """Roles are not revealed when players die."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.role_reveal = "off"
        self.CUSTOM_SETTINGS.stats_type = "disabled"
        self.ROLE_GUIDE = {
            6:  ["wolf", "seer", "cursed villager"],
            8:  ["wolf mystic", "mystic"],
            10: ["traitor", "hunter"],
            12: ["wolf(2)", "guardian angel"],
            15: ["werecrow", "detective", "clone"],
            17: ["amnesiac", "lycan", "cursed villager(2)"],
            19: ["wolf(3)"],
        }
