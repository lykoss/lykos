from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.events import EventListener
from src import channels, users

@game_mode("drunkfire", minp=8, maxp=17)
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
        self.GUN_CHANCES = { # these are *added* on top of the base chances!
            "gunner": {
                "hit": -1/4, # base is 75%, now 50%
                "headshot": 6/10, # base is 20%, now 80%
                "explode": 1/20, # base is 5%, now 10%
            },
            "wolf gunner": {
                "hit": 3/10, # base is 70%, now 100%
                "headshot": 4/10, # base is 60%, now 100%
            },
        }

        self.ROLE_GUIDE = {
            8:  ["wolf gunner", "traitor", "seer", "village drunk", "village drunk(2)", "cursed villager", "gunner", "gunner(2)", "gunner(3)", "sharpshooter", "sharpshooter(2)"],
            10: ["wolf gunner(2)", "village drunk(3)", "gunner(4)"],
            12: ["hag", "village drunk(4)", "crazed shaman", "sharpshooter(3)"],
            14: ["wolf gunner(3)", "seer(2)", "gunner(5)", "assassin"],
            16: ["traitor(2)", "village drunk(5)", "sharpshooter(4)"],
        }
        self.EVENTS = {
            "chk_win": EventListener(self.all_dead_chk_win),
            "gun_chances": EventListener(self.custom_gun_chances)
        }
