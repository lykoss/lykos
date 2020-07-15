from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.events import EventListener
from src import channels, users

# someone let woffle commit while drunk again... tsk tsk
@game_mode("mudkip", minp=5, maxp=17, likelihood=5)
class MudkipMode(GameMode):
    """Why are all the professors named after trees?"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ABSTAIN_ENABLED = False

        # Actual shaman chances are handled in restore_totem_chances (n1 is a guaranteed death totem)
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 1, "wolf shaman": 0, "crazed shaman": 0},
            "protection"    : {"shaman": 0, "wolf shaman": 1, "crazed shaman": 1},
            "silence"       : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "revealing"     : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "desperation"   : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "impatience"    : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "pacifism"      : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "influence"     : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 1},
            "narcolepsy"    : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "exchange"      : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
            "lycanthropy"   : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 1},
            "luck"          : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 1},
            "pestilence"    : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 1},
            "retribution"   : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 1},
            "misdirection"  : {"shaman": 0, "wolf shaman": 1, "crazed shaman": 0},
            "deceit"        : {"shaman": 0, "wolf shaman": 0, "crazed shaman": 0},
        }

        self.set_default_totem_chances()

        self.ROLE_GUIDE = {
            5:  ["wolf", "cult leader", "insomniac", "investigator"],
            6:  ["guardian angel"],
            7:  ["jester"],
            8:  ["shaman"],
            9:  ["doomsayer"],
            10: ["vengeful ghost"],
            11: ["crazed shaman"],
            12: ["priest"],
            13: ["wolf shaman"],
            14: ["amnesiac"],
            15: ["succubus"],
            16: ["assassin"],
            17: ["dullahan"]
        }

        self.EVENTS = {
            "lynch_behaviour": EventListener(self.lynch_behaviour),
            "daylight_warning": EventListener(self.daylight_warning),
            "transition_day_begin": EventListener(self.restore_totem_chances)
        }

    def restore_totem_chances(self, evt, var):
        if var.NIGHT_COUNT == 1: # don't fire unnecessarily every day
            self.TOTEM_CHANCES["pestilence"]["shaman"] = 1

    def lynch_behaviour(self, evt, var):
        evt.data["kill_ties"] = True
        voters = sum(map(len, evt.params.votes.values()))
        if voters == evt.params.players:
            evt.data["force"] = True

    def daylight_warning(self, evt, var):
        evt.data["message"] = "daylight_warning_killtie"
