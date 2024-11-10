from src.events import EventListener
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState


@game_mode("kaboom", minp=6, maxp=24)
class KaboomMode(GameMode):
    """All of these explosions are rather loud..."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            6: ["wolf", "crazed shaman", "mad scientist", "insomniac", "vengeful ghost", "blessed villager"],
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
        self.SECONDARY_ROLES["blessed villager"] = {"wolf"}
        self.SECONDARY_ROLES["oracle"] = {"wolf"}
        self.EVENTS = {
            "role_attribution_end": EventListener(self.on_role_attribution_end)
        }

    def on_role_attribution_end(self, evt, var: GameState, main_roles, roles):
        # ensure the blessed wolf and the wolf oracle aren't the same wolf
        if not roles.get("oracle", None):
            return
        blessed = list(roles["blessed villager"])[0]
        oracle = list(roles["oracle"])[0]
        if blessed is oracle:
            evt.data["actions"].append(("remove", oracle, "oracle"))
            other = list(roles["wolf"] - {oracle})[0]
            evt.data["actions"].append(("add", other, "oracle"))
