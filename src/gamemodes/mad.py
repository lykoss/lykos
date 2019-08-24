from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users


@game_mode("mad", minp=7, maxp=22, likelihood=5)
class MadMode(GameMode):
    """This game mode has mad scientist and many things that may kill you."""
    def __init__(self, arg=""):
        super().__init__(arg)
        # gunner and sharpshooter always get 1 bullet
        self.SHOTS_MULTIPLIER = 0.0001
        self.SHARPSHOOTER_MULTIPLIER = 0.0001
        self.ROLE_GUIDE = {
            7:  ["seer", "mad scientist", "wolf", "cultist"],
            8:  ["traitor", "-cultist", "gunner/sharpshooter"],
            10: ["werecrow", "cursed villager"],
            12: ["detective", "cultist"],
            14: ["wolf(2)", "vengeful ghost"],
            15: ["harlot"],
            17: ["wolf cub", "jester", "assassin"],
            18: ["hunter"],
            20: ["wolf cub(2)"],
        }
