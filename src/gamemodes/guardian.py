from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_players
from src.events import EventListener
from src import channels, users

# original idea by Rossweisse, implemented by Vgr with help from woffle and jacob1
@game_mode("guardian", minp=7, maxp=24, likelihood=5)
class GuardianMode(GameMode):
    """Game mode full of guardian angels, wolves need to pick them apart!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.limit_abstain = False
        self.ROLE_GUIDE = {
            7:  ["werekitten", "seer", "guardian angel", "cursed villager", "cursed villager(2)"],
            8:  ["wolf", "village drunk"],
            10: ["werecrow", "shaman"],
            12: ["alpha wolf", "guardian angel(2)", "cursed villager(3)"],
            13: ["jester", "gunner"],
            15: ["wolf(2)", "bodyguard"],
            17: ["amnesiac", "demoniac"],
            19: ["wolf gunner", "investigator"],
            21: ["amnesiac(2)"],
            22: ["minion"],
            23: ["vigilante"]
        }
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 10},
            "protection"    : {"shaman": 0},
            "silence"       : {"shaman": 10},
            "revealing"     : {"shaman": 20},
            "desperation"   : {"shaman": 0},
            "impatience"    : {"shaman": 0},
            "pacifism"      : {"shaman": 0},
            "influence"     : {"shaman": 20},
            "narcolepsy"    : {"shaman": 0},
            "exchange"      : {"shaman": 0},
            "lycanthropy"   : {"shaman": 0},
            "luck"          : {"shaman": 10},
            "pestilence"    : {"shaman": 0},
            "retribution"   : {"shaman": 10},
            "misdirection"  : {"shaman": 20},
            "deceit"        : {"shaman": 0},
        }
        self.set_default_totem_chances()
        self.EVENTS = {
            "chk_win": EventListener(self.chk_win)
        }

    def chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        lguardians = len(get_players(var, ["guardian angel", "bodyguard"], mainroles=mainroles))

        if lpl < 1:
            # handled by default win cond checking
            return
        elif not lguardians and lwolves > lpl / 2:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["guardian_wolf_win"]
        elif not lguardians and lwolves == lpl / 2:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["guardian_wolf_tie_no_guards"]
        elif not lrealwolves and lguardians:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["guardian_villager_win"]
        elif not lrealwolves and not lguardians:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["guardian_lose_no_guards"]
        elif lwolves == lguardians and lpl - lwolves - lguardians == 0:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["guardian_lose_with_guards"]
        else:
            evt.data["winner"] = None
