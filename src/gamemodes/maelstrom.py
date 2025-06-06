from collections import defaultdict, Counter

from src.gamemodes import game_mode, GameMode
from src.functions import get_players
from src.gamestate import GameState
from src.events import Event, EventListener
from src.trans import chk_win_conditions
from src import users
from src.cats import All, Team_Switcher, Win_Stealer, Wolf, Wolf_Objective, Vampire_Objective, Killer
from src.random import random

@game_mode("maelstrom", minp=8, maxp=24)
class MaelstromMode(GameMode):
    """Some people just want to watch the world burn."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.role_reveal = "on"
        self.CUSTOM_SETTINGS.stats_type = "disabled"
        self.CUSTOM_SETTINGS.always_pm_role = True
        # clone and wild child are pointless in this mode
        # monster and demoniac are nearly impossible to counter and don't add any interesting gameplay
        # succubus keeps around entranced people, who are then unable to win even if there are later no succubi (not very fun)
        self.roles = All - Team_Switcher - Win_Stealer + {"fool", "lycan", "turncoat"} - self.SECONDARY_ROLES.keys()
        self.EVENTS = {
            "role_attribution": EventListener(self.role_attribution),
            "transition_night_begin": EventListener(self.transition_night_begin)
        }

    def role_attribution(self, evt: Event, var: GameState, villagers):
        evt.data["addroles"].update(self._role_attribution(var, villagers, True))
        evt.prevent_default = True

    def transition_night_begin(self, evt: Event, var: GameState):
        # don't do this n1
        if var.night_count == 0:
            return
        villagers = get_players(var)
        lpl = len(villagers)
        addroles = self._role_attribution(var, villagers, False)

        # shameless copy/paste of regular role attribution
        for role, rs in var.roles.items():
            if role in self.SECONDARY_ROLES:
                continue
            rs.clear()
        # prevent wolf.py from sending messages about a new wolf to soon-to-be former wolves
        # (note that None doesn't work, so "player" works fine)
        for player in var.main_roles:
            var.main_roles[player] = "player"
        new_evt = Event("new_role", {"messages": [], "role": None, "in_wolfchat": False}, inherit_from=None)
        for role, count in addroles.items():
            selected = random.sample(villagers, count)
            for x in selected:
                villagers.remove(x)
                new_evt.data["role"] = role
                new_evt.dispatch(var, x, var.original_main_roles[x])
                var.roles[new_evt.data["role"]].add(x)

        # for end of game stats to show what everyone ended up as on game end
        for role, pl in var.roles.items():
            if role in self.SECONDARY_ROLES:
                continue
            for p in pl:
                if var.setup_completed:
                    # discard them from all non-secondary roles, we don't have a reliable
                    # means of tracking their previous role (due to traitor turning, exchange
                    # totem, etc.), so we need to iterate through everything.
                    # also this touches the underlying _original_[main_]roles mappings... shh
                    for r in var.original_roles:
                        if r in self.SECONDARY_ROLES:
                            continue
                        var._original_roles[r].discard(p)
                    var._original_roles[role].add(p)
                    var._original_main_roles[p] = role
                var.final_roles[p] = role
                var.main_roles[p] = role

    def _role_attribution(self, var, villagers, do_templates):
        lpl = len(villagers)
        addroles = Counter()
        addroles[random.choice(list(Wolf & Killer))] += 1 # make sure there's at least one wolf role
        num_wolves = 1
        num_vampires = 0
        roles = list(self.roles)
        for i in range(1, lpl):
            if num_wolves + num_vampires >= (lpl / 2) - 1:
                # Make sure game does not end immediately
                role = random.choice(list(set(roles) - Wolf_Objective - Vampire_Objective))
            else:
                role = random.choice(roles)
            addroles[role] += 1
            if role in Wolf_Objective:
                num_wolves += 1
            if role in Vampire_Objective:
                num_vampires += 1

        if do_templates:
            addroles["gunner/sharpshooter"] = random.randrange(6)
            addroles["assassin"] = random.randrange(3)
            addroles["cursed villager"] = random.randrange(3)
            addroles["mayor"] = random.randrange(2)
            if random.randrange(100) == 0 and addroles.get("villager", 0) > 0:
                addroles["blessed villager"] = 1

        rolemap = defaultdict(set)
        mainroles = {}
        i = 0
        for role, count in addroles.items():
            if count > 0:
                for j in range(count):
                    u = users.FakeUser.from_nick(str(i + j))
                    rolemap[role].add(u)
                    if role not in self.SECONDARY_ROLES:
                        mainroles[u] = role
                i += count

        if chk_win_conditions(var, rolemap, mainroles, end_game=False):
            return self._role_attribution(var, villagers, do_templates)

        return addroles
