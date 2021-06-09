from src.gamemodes import game_mode, GameMode
from src.messages import messages

@game_mode("kaboom", minp=6, maxp=24, likelihood=0)
class KaboomMode(GameMode):
    """All of these explosions are rather loud..."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            6: ["wolf", "crazed shaman", "mad scientist", "insomniac", "vengeful ghost"],
            7: ["master of teleportation"],
            8: ["wolf"],
            10: ["oracle", "mad scientist"],
            11: ["crazed shaman"],
            13: ["wolf"],
            14: ["detective"],
            15: ["vengeful ghost"],
            16: ["mad scientist"],
            17: ["wolf gunner"],
            19: ["priest"],
            20: ["master of teleportation"],
            21: ["wolf"],
            22: ["mad scientist"],
            23: ["vengeful ghost"]
        }
        self.SECONDARY_ROLES["oracle"] = {"wolf"}
