from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("drunkfire", minp=8, maxp=17, likelihood=0)
class DrunkFireMode(GameMode):
    """Most players get a gun, quickly shoot all the wolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.NIGHT_TIME_LIMIT = 60
        self.NIGHT_TIME_WARN = 40     #    HIT  MISS  HEADSHOT
        self.GUN_CHANCES              = (  3/7 , 3/7 , 4/5   )
        self.WOLF_GUN_CHANCES         = (  4/7 , 3/7 , 1     )
        self.ROLE_GUIDE = {
            8:  ["wolf", "traitor", "seer", "village drunk", "village drunk(2)", "cursed villager", "gunner", "gunner(2)", "gunner(3)", "sharpshooter", "sharpshooter(2)"],
            10: ["wolf(2)", "village drunk(3)", "gunner(4)"],
            12: ["hag", "village drunk(4)", "crazed shaman", "sharpshooter(3)"],
            14: ["wolf(3)", "seer(2)", "gunner(5)", "assassin"],
            16: ["traitor(2)", "village drunk(5)", "sharpshooter(4)"],
        }

    def startup(self):
        events.add_listener("chk_win", self.all_dead_chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.all_dead_chk_win)
