import random
from collections import defaultdict
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.events import EventListener, Event
from src.trans import chk_win_conditions
from src import users
from src.cats import All, Wolf, Wolf_Objective, Killer

@game_mode("random", minp=8, maxp=24, likelihood=0)
class RandomMode(GameMode):
    """Completely random and hidden roles."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.role_reveal = random.choice(("on", "off", "team"))
        self.CUSTOM_SETTINGS.stats_type = "disabled" if self.CUSTOM_SETTINGS.role_reveal == "off" else random.choice(("disabled", "team"))
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

        self.EVENTS = {
            "role_attribution": EventListener(self.role_attribution),
            "chK_win": EventListener(self.lovers_chk_win, listener_id="lovers_chk_win")
        }

    def role_attribution(self, evt: Event, var: GameState, villagers):
        lpl = len(villagers)
        addroles = evt.data["addroles"]
        addroles[random.choice(list(Wolf & Killer))] += 1 # make sure there's at least one wolf role
        lwolves = 1
        roles = list(All - self.SECONDARY_ROLES.keys() - {"villager", "cultist", "amnesiac"})
        for i in range(1, lpl):
            if lwolves >= (lpl / 2) - 1:
                # Make sure game does not end immediately
                role = random.choice(list(set(roles) - Wolf_Objective))
            else:
                role = random.choice(roles)
            addroles[role] += 1
            if role in Wolf_Objective:
                lwolves += 1
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

        if chk_win_conditions(var, rolemap, mainroles, end_game=False):
            return self.role_attribution(evt, var, villagers)

        evt.prevent_default = True
