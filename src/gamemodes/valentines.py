from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.events import EventListener
from src import channels, users

@game_mode("valentines", minp=8, maxp=24, likelihood=0)
class MatchmakerMode(GameMode):
    """Love is in the air!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.night_time_limit = 150
        self.CUSTOM_SETTINGS.night_time_warn = 105
        self.CUSTOM_SETTINGS.default_role = "matchmaker"
        self.ROLE_GUIDE = {
            8:  ["wolf", "wolf(2)"],
            12: ["monster"],
            13: ["wolf(3)"],
            17: ["wolf(4)"],
            18: ["mad scientist"],
            21: ["wolf(5)"],
            24: ["wolf(6)"],
        }
        self.EVENTS = {
            "chk_win": EventListener(self.lovers_chk_win)
        }
