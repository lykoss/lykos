import random
from collections import defaultdict
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src import events, channels, users
from src.cats import All, Wolf, Killer

@game_mode("random", minp=8, maxp=24, likelihood=0)
class RandomMode(GameMode):
    """Completely random and hidden roles."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = random.choice(("on", "off", "team"))
        self.STATS_TYPE = "disabled" if self.ROLE_REVEAL == "off" else random.choice(("disabled", "team"))
        super().__init__(arg)
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        for role in self.SECONDARY_ROLES:
            self.SECONDARY_ROLES[role] = All

        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 8, "wolf shaman": 1},
            "protection"    : {"shaman": 6, "wolf shaman": 6},
            "silence"       : {"shaman": 4, "wolf shaman": 3},
            "revealing"     : {"shaman": 2, "wolf shaman": 5},
            "desperation"   : {"shaman": 4, "wolf shaman": 7},
            "impatience"    : {"shaman": 7, "wolf shaman": 2},
            "pacifism"      : {"shaman": 7, "wolf shaman": 2},
            "influence"     : {"shaman": 7, "wolf shaman": 2},
            "narcolepsy"    : {"shaman": 4, "wolf shaman": 3},
            "exchange"      : {"shaman": 1, "wolf shaman": 1},
            "lycanthropy"   : {"shaman": 1, "wolf shaman": 3},
            "luck"          : {"shaman": 6, "wolf shaman": 7},
            "pestilence"    : {"shaman": 3, "wolf shaman": 1},
            "retribution"   : {"shaman": 5, "wolf shaman": 6},
            "misdirection"  : {"shaman": 6, "wolf shaman": 4},
            "deceit"        : {"shaman": 3, "wolf shaman": 6},
        }

        self.ROLE_SETS["gunner/sharpshooter"] = {"gunner": 8, "sharpshooter": 4}

        self.set_default_totem_chances()

    def startup(self):
        events.add_listener("role_attribution", self.role_attribution)
        events.add_listener("chk_win", self.lovers_chk_win)

    def teardown(self):
        events.remove_listener("role_attribution", self.role_attribution)
        events.remove_listener("chk_win", self.lovers_chk_win)

    def role_attribution(self, evt, var, chk_win_conditions, villagers):
        lpl = len(villagers) - 1
        addroles = evt.data["addroles"]
        addroles[random.choice(list(Wolf & Killer))] += 1 # make sure there's at least one wolf role
        roles = list(All - self.SECONDARY_ROLES.keys() - {"villager", "cultist", "amnesiac"})
        while lpl:
            addroles[random.choice(roles)] += 1
            lpl -= 1

        addroles["gunner/sharpshooter"] = random.randrange(int(len(villagers) ** 1.2 / 4))
        addroles["assassin"] = random.randrange(max(int(len(villagers) ** 1.2 / 8), 1))

        rolemap = defaultdict(set)
        mainroles = {}
        i = 0
        for role, count in addroles.items():
            if count > 0:
                for j in range(count):
                    u = users.FakeUser.from_nick(str(i + j))
                    rolemap[role].add(u.nick)
                    if role not in self.SECONDARY_ROLES:
                        mainroles[u] = role
                i += count

        if chk_win_conditions(rolemap, mainroles, end_game=False):
            return self.role_attribution(evt, var, chk_win_conditions, villagers)

        evt.prevent_default = True
