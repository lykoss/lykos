from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.events import EventListener
from src import channels, users

@game_mode("rapidfire", minp=6, maxp=24, likelihood=0)
class RapidFireMode(GameMode):
    """Many roles that lead to multiple chain deaths."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0
        self.ROLE_GUIDE = {
            6:  ["wolf", "seer", "mad scientist", "cursed villager"],
            8:  ["wolf cub", "hunter", "assassin"],
            10: ["traitor", "matchmaker", "time lord", "sharpshooter"],
            12: ["wolf(2)", "vengeful ghost"],
            15: ["wolf cub(2)", "augur", "amnesiac", "assassin(2)"],
            18: ["wolf(3)", "hunter(2)", "mad scientist(2)", "time lord(2)", "cursed villager(2)"],
            22: ["wolf(4)", "matchmaker(2)", "vengeful ghost(2)"],
        }
        self.EVENTS = {
            "chk_win": EventListener(self.all_dead_chk_win)
        }
