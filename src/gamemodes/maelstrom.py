import random
import copy
from datetime import datetime
from collections import defaultdict, Counter
import botconfig
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_players
from src import events, channels, users
from src.cats import All, Team_Switcher, Win_Stealer, Wolf, Killer

@game_mode("maelstrom", minp=8, maxp=24, likelihood=0)
class MaelstromMode(GameMode):
    """Some people just want to watch the world burn."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = "on"
        self.STATS_TYPE = "disabled"
        super().__init__(arg)
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        self.ALWAYS_PM_ROLE = True
        # clone and wild child are pointless in this mode
        # monster and demoniac are nearly impossible to counter and don't add any interesting gameplay
        # succubus keeps around entranced people, who are then unable to win even if there are later no succubi (not very fun)
        self.roles = All - Team_Switcher - Win_Stealer + {"fool", "lycan", "turncoat"} - self.SECONDARY_ROLES.keys()

        self.DEAD_ACCOUNTS = set()
        self.DEAD_HOSTS = set()

    def startup(self):
        events.add_listener("role_attribution", self.role_attribution)
        events.add_listener("transition_night_begin", self.transition_night_begin)
        events.add_listener("del_player", self.on_del_player)
        events.add_listener("join", self.on_join)

    def teardown(self):
        events.remove_listener("role_attribution", self.role_attribution)
        events.remove_listener("transition_night_begin", self.transition_night_begin)
        events.remove_listener("del_player", self.on_del_player)
        events.remove_listener("join", self.on_join)

    def on_del_player(self, evt, var, player, all_roles, death_triggers):
        if player.is_fake:
            return

        if player.account is not None:
            self.DEAD_ACCOUNTS.add(player.lower().account)

        if not var.ACCOUNTS_ONLY:
            self.DEAD_HOSTS.add(player.lower().host)

    def on_join(self, evt, var, wrapper, message, forced=False):
        if var.PHASE != "day" or (wrapper.public and wrapper.target is not channels.Main):
            return
        temp = wrapper.source.lower()
        if (wrapper.source in var.ALL_PLAYERS or
                temp.account in self.DEAD_ACCOUNTS or
                temp.host in self.DEAD_HOSTS):
            wrapper.pm(messages["maelstrom_dead"])
            return
        if not forced and evt.data["join_player"](var, type(wrapper)(wrapper.source, channels.Main), sanity=False):
            self._on_join(var, wrapper)
            evt.prevent_default = True
        elif forced:
            # in fjoin, handle this differently
            jp = evt.data["join_player"]
            evt.data["join_player"] = lambda var, wrapper, who=None, forced=False: jp(var, wrapper, who=who, forced=forced, sanity=False) and self._on_join(var, wrapper)

    def _on_join(self, var, wrapper):
        from src import hooks, channels
        role = random.choice(list(self.roles))
        with copy.deepcopy(var.ROLES) as rolemap, copy.deepcopy(var.MAIN_ROLES) as mainroles:
            rolemap[role].add(wrapper.source)
            mainroles[wrapper.source] = role

            if self.chk_win_conditions(rolemap, mainroles, end_game=False):
                return self._on_join(var, wrapper)

        if not wrapper.source.is_fake or not botconfig.DEBUG_MODE:
            cmodes = [("+v", wrapper.source)]
            for mode in var.AUTO_TOGGLE_MODES & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                var.OLD_MODES[wrapper.source].add(mode)
            channels.Main.mode(*cmodes)
        evt = events.Event("new_role", {"messages": [], "role": role, "in_wolfchat": False}, inherit_from=None)
        # Use "player" as old role, to force wolf event to send "new wolf" messages
        evt.dispatch(var, wrapper.source, "player")
        role = evt.data["role"]

        var.ROLES[role].add(wrapper.source)
        var.ORIGINAL_ROLES[role].add(wrapper.source)
        var.FINAL_ROLES[wrapper.source.nick] = role # FIXME: once FINAL_ROLES stores users
        var.MAIN_ROLES[wrapper.source] = role
        var.ORIGINAL_MAIN_ROLES[wrapper.source] = role
        var.LAST_SAID_TIME[wrapper.source.nick] = datetime.now()
        if wrapper.source.nick in var.USERS:
            var.PLAYERS[wrapper.source.nick] = var.USERS[wrapper.source.nick]

        for message in evt.data["messages"]:
            wrapper.pm(message)

        from src.decorators import COMMANDS
        COMMANDS["myrole"][0].caller(wrapper.source.client, wrapper.source.nick, wrapper.target.name, "") # FIXME: New/old API

    def role_attribution(self, evt, var, chk_win_conditions, villagers):
        self.chk_win_conditions = chk_win_conditions
        evt.data["addroles"].update(self._role_attribution(var, villagers, True))
        evt.prevent_default = True

    def transition_night_begin(self, evt, var):
        # don't do this n1
        if var.NIGHT_COUNT == 1:
            return
        villagers = get_players()
        lpl = len(villagers)
        addroles = self._role_attribution(var, villagers, False)

        # shameless copy/paste of regular role attribution
        for rs in var.ROLES.values():
            rs.clear()
        # prevent wolf.py from sending messages about a new wolf to soon-to-be former wolves
        # (note that None doesn't work, so "player" works fine)
        for player in var.MAIN_ROLES:
            var.MAIN_ROLES[player] = "player"
        new_evt = events.Event("new_role", {"messages": [], "role": None, "in_wolfchat": False}, inherit_from=None)
        for role, count in addroles.items():
            selected = random.sample(villagers, count)
            for x in selected:
                villagers.remove(x)
                new_evt.data["role"] = role
                new_evt.dispatch(var, x, var.ORIGINAL_MAIN_ROLES[x])
                var.ROLES[new_evt.data["role"]].add(x)

        # for end of game stats to show what everyone ended up as on game end
        for role, pl in var.ROLES.items():
            if role in self.SECONDARY_ROLES:
                continue
            for p in pl:
                # discard them from all non-secondary roles, we don't have a reliable
                # means of tracking their previous role (due to traitor turning, exchange
                # totem, etc.), so we need to iterate through everything.
                for r in var.ORIGINAL_ROLES.keys():
                    if r in self.SECONDARY_ROLES:
                        continue
                    var.ORIGINAL_ROLES[r].discard(p)
                var.ORIGINAL_ROLES[role].add(p)
                var.FINAL_ROLES[p.nick] = role # FIXME
                var.MAIN_ROLES[p] = role
                var.ORIGINAL_MAIN_ROLES[p] = role

    def _role_attribution(self, var, villagers, do_templates):
        lpl = len(villagers) - 1
        addroles = Counter()
        addroles[random.choice(list(Wolf & Killer))] += 1 # make sure there's at least one wolf role
        roles = list(self.roles)
        while lpl:
            addroles[random.choice(roles)] += 1
            lpl -= 1

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

        if self.chk_win_conditions(rolemap, mainroles, end_game=False):
            return self._role_attribution(var, villagers, do_templates)

        return addroles
