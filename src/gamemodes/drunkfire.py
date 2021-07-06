from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.events import EventListener
from src import channels, users

@game_mode("drunkfire", minp=8, maxp=17, likelihood=0)
class DrunkFireMode(GameMode):
    """Most players get a gun, quickly shoot all the wolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.day_time_limit = 480
        self.CUSTOM_SETTINGS.day_time_warn = 360
        self.CUSTOM_SETTINGS.short_day_time_limit = 240
        self.CUSTOM_SETTINGS.short_day_time_warn = 180
        self.CUSTOM_SETTINGS.night_time_limit = 60
        self.CUSTOM_SETTINGS.night_time_warn = 40
        self.GUN_CHANCES = {
            "gunner": (10/20, 8/20, 16/20), # 50% hit, 40% miss, 10% explode, 80% headshot
            "wolf gunner": (12/20, 8/20, 1), # 60% hit, 40% miss, 0% explode, 100% headshot
            "sharpshooter": (1, 0, 1) # 100% hit, 0% miss, 0% explode, 100% headshot
        }
        self.ROLE_GUIDE = {
            8:  ["wolf gunner", "traitor", "seer", "village drunk", "village drunk(2)", "cursed villager", "gunner", "gunner(2)", "gunner(3)", "sharpshooter", "sharpshooter(2)"],
            10: ["wolf gunner(2)", "village drunk(3)", "gunner(4)"],
            12: ["hag", "village drunk(4)", "crazed shaman", "sharpshooter(3)"],
            14: ["wolf gunner(3)", "seer(2)", "gunner(5)", "assassin"],
            16: ["traitor(2)", "village drunk(5)", "sharpshooter(4)"],
        }
        self.EVENTS = {
            "chk_win": EventListener(self.all_dead_chk_win)
        }
