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
            6:  ["wolf", "seer", "cursed villager"],
            7:  ["cultist", "shaman"],
            8:  ["harlot", "traitor", "-cultist"],
            9:  ["crazed shaman"],
            10: ["wolf cub"],
            11: ["matchmaker"],
            12: ["-wolf", "werecrow"],
            13: ["detective"],
            14: ["tough wolf"],
            15: ["hunter"],
            16: ["monster"],
            18: ["bodyguard"],
            20: ["sorcerer", "augur", "cursed villager(2)"],
            21: ["wolf", "wolf(2)", "gunner/sharpshooter"],
            23: ["amnesiac", "mayor"],
            24: ["hag"],
        }
