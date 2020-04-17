from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.events import EventListener
from src import channels, users

@game_mode("default", minp=4, maxp=24, likelihood=40)
class DefaultMode(GameMode):
    """Default game mode."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            4:  ["wolf", "seer"],
            6:  ["cursed villager"],
            7:  ["cultist", "shaman"],
            8:  ["harlot", "traitor", "-cultist"],
            9:  ["crazed shaman"],
            10: ["wolf cub", "gunner/sharpshooter"],
            11: ["matchmaker"],
            12: ["werecrow", "detective"],
            13: ["assassin"],
            15: ["wolf(2)", "hunter"],
            16: ["monster"],
            18: ["bodyguard"],
            20: ["sorcerer", "augur", "cursed villager(2)"],
            21: ["wolf(3)", "gunner/sharpshooter(2)"],
            23: ["amnesiac", "mayor"],
            24: ["hag"],
        }
