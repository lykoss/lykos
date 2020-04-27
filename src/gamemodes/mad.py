from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

@game_mode("mad", minp=7, maxp=24, likelihood=5)
class MadMode(GameMode):
    """This game mode has mad scientist and many things that may kill you."""
    def __init__(self, arg=""):
        super().__init__(arg)
        # gunner and sharpshooter always get 1 bullet
        self.SHOTS_MULTIPLIER = {
            "gunner": 0.0001,
            "sharpshooter": 0.0001,
            "wolf gunner": 0.0001
        }
        del self.SECONDARY_ROLES["gunner"]
        del self.SECONDARY_ROLES["sharpshooter"]
        self.ROLE_GUIDE = {
            7:  ["seer", "mad scientist", "wolf", "cultist"],
            8:  ["traitor", "-cultist", "gunner/sharpshooter"],
            10: ["werecrow", "cursed villager"],
            12: ["detective", "cultist"],
            14: ["wolf(2)", "vengeful ghost"],
            15: ["harlot"],
            17: ["wolf cub", "jester", "assassin"],
            18: ["hunter"],
            20: ["wolf gunner"],
            21: ["blessed villager"],
            22: ["time lord", "cursed villager(2)"]
        }
