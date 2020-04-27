from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users

# Credits to Metacity for designing and current name
# Blame arkiwitect for the original name of KrabbyPatty
@game_mode("aleatoire", minp=8, maxp=24, likelihood=5)
class AleatoireMode(GameMode):
    """Game mode created by Metacity and balanced by woffle."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 4},
            "protection"    : {"shaman": 8},
            "silence"       : {"shaman": 2},
            "revealing"     : {"shaman": 0},
            "desperation"   : {"shaman": 1},
            "impatience"    : {"shaman": 0},
            "pacifism"      : {"shaman": 0},
            "influence"     : {"shaman": 0},
            "narcolepsy"    : {"shaman": 0},
            "exchange"      : {"shaman": 0},
            "lycanthropy"   : {"shaman": 0},
            "luck"          : {"shaman": 0},
            "pestilence"    : {"shaman": 1},
            "retribution"   : {"shaman": 4},
            "misdirection"  : {"shaman": 0},
            "deceit"        : {"shaman": 0},
        }

        self.set_default_totem_chances()

        self.ROLE_GUIDE = {
            8:  ["wolf", "traitor", "seer", "shaman", "cursed villager", "cursed villager(2)"],
            10: ["wolf(2)", "vengeful ghost", "gunner"],
            12: ["hag", "guardian angel", "amnesiac"],
            13: ["assassin"],
            14: ["turncoat"],
            15: ["werecrow", "augur", "mayor"],
            17: ["wolf(3)", "hunter"],
            18: ["vengeful ghost(2)"],
            20: ["wolf cub", "time lord"],
            22: ["sorcerer", "assassin(2)"]
        }
