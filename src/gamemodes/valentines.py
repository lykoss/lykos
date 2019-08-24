from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("valentines", minp=8, maxp=24, likelihood=0)
class MatchmakerMode(GameMode):
    """Love is in the air!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.NIGHT_TIME_LIMIT = 150
        self.NIGHT_TIME_WARN = 105
        self.DEFAULT_ROLE = "matchmaker"
        self.ROLE_GUIDE = {
            8:  ["wolf", "wolf(2)"],
            12: ["monster"],
            13: ["wolf(3)"],
            17: ["wolf(4)"],
            18: ["mad scientist"],
            21: ["wolf(5)"],
            24: ["wolf(6)"],
        }

    def startup(self):
        events.add_listener("chk_win", self.lovers_chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.lovers_chk_win)
