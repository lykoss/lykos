from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_players
from src import events, channels, users

# original idea by Rossweisse, implemented by Vgr with help from woffle and jacob1
@game_mode("guardian", minp=8, maxp=16, likelihood=1)
class GuardianMode(GameMode):
    """Game mode full of guardian angels, wolves need to pick them apart!"""
    def __init__(self, arg=""):
        self.LIMIT_ABSTAIN = False
        super().__init__(arg)
        self.ROLE_GUIDE = {
            8:  ["wolf", "werekitten", "seer", "guardian angel", "village drunk", "cursed villager"],
            10: ["werecrow", "shaman"],
            12: ["alpha wolf", "guardian angel(2)", "cursed villager(2)"],
            13: ["jester", "gunner"],
            15: ["wolf(2)", "bodyguard"],
        }
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 4},
            "protection"    : {"shaman": 8},
            "silence"       : {"shaman": 2},
            "revealing"     : {"shaman": 0},
            "desperation"   : {"shaman": 0},
            "impatience"    : {"shaman": 0},
            "pacifism"      : {"shaman": 0},
            "influence"     : {"shaman": 0},
            "narcolepsy"    : {"shaman": 0},
            "exchange"      : {"shaman": 0},
            "lycanthropy"   : {"shaman": 0},
            "luck"          : {"shaman": 3},
            "pestilence"    : {"shaman": 0},
            "retribution"   : {"shaman": 6},
            "misdirection"  : {"shaman": 4},
            "deceit"        : {"shaman": 0},
        }

        self.set_default_totem_chances()

    def startup(self):
        events.add_listener("chk_win", self.chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win)

    def chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        lguardians = len(get_players(["guardian angel", "bodyguard"], mainroles=mainroles))

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
