from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users


@game_mode("noreveal", minp=4, maxp=21, likelihood=1)
class NoRevealMode(GameMode):
    """Roles are not revealed when players die."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = "off"
        self.STATS_TYPE = "disabled"
        super().__init__(arg)
        self.ROLE_GUIDE = {
            4:  ["wolf", "seer"],
            6:  ["cursed villager"],
            8:  ["wolf mystic", "mystic"],
            10: ["traitor", "hunter"],
            12: ["wolf(2)", "guardian angel"],
            15: ["werecrow", "detective", "clone"],
            17: ["amnesiac", "lycan", "cursed villager(2)"],
            19: ["wolf(3)"],
        }
