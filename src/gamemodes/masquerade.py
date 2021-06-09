from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_players
from src.events import EventListener
from src import channels, users

@game_mode("masquerade", minp=6, maxp=24, likelihood=5)
class MasqueradeMode(GameMode):
    """Trouble is afoot at a masquerade ball when an attendee is found torn to shreds!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            6: ["augur", "wolf", "wild child"],
            7: ["guardian angel/vigilante"],
            8: ["wolf(2)"],
            9: ["amnesiac"],
            10: ["seer/village drunk", "wild child(2)"],
            11: ["gunner"],
            12: ["werekitten"],
            13: ["guardian angel/vigilante(2)"],
            15: ["sorcerer"],
            16: ["shaman/wolf shaman"],
            18: ["detective", "wolf(3)", "amnesiac(2)"],
            20: ["gunner(2)", "fallen angel"],
            21: ["crazed shaman"],
            24: ["priest", "vengeful ghost", "wild child(3)"]
        }
        self.ROLE_SETS.update({
            "guardian angel/vigilante": {"guardian angel": 1, "vigilante": 1},
            "seer/village drunk": {"seer": 1, "village drunk": 1},
            "shaman/wolf shaman": {"shaman": 1, "wolf shaman": 1}
        })
