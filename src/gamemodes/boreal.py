from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import List, Tuple, Dict, TYPE_CHECKING
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.roles.helper.wolves import send_wolfchat_message
from src.messages import messages
from src.functions import get_players, get_all_players, get_main_role, change_role, match_totem
from src.events import EventListener, find_listener
from src.containers import DefaultUserDict
from src.status import add_dying
from src.cats import Wolfteam
from src.decorators import command
from src import channels, users

if TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

@game_mode("boreal", minp=6, maxp=24, likelihood=5)
class BorealMode(GameMode):
    """Some shamans are working against you. Exile them before you starve!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.LIMIT_ABSTAIN = False
        self.SELF_LYNCH_ALLOWED = False
        self.DEFAULT_ROLE = "shaman"
        # If you add non-wolfteam, non-shaman roles, be sure to update update_stats to account for it!
        # otherwise !stats will break if they turn into VG.
        self.ROLE_GUIDE = {
            6: ["wolf shaman", "wolf shaman(2)"],
            10: ["wolf shaman(3)"],
            15: ["wolf shaman(4)"],
            20: ["wolf shaman(5)"]
            }
        self.EVENTS = {
            "transition_night_begin": EventListener(self.on_transition_night_begin),
            "transition_night_end": EventListener(self.on_transition_night_end, priority=1),
            "wolf_numkills": EventListener(self.on_wolf_numkills),
            "totem_assignment": EventListener(self.on_totem_assignment),
            "transition_day_begin": EventListener(self.on_transition_day_begin, priority=8),
            "transition_day_resolve_end": EventListener(self.on_transition_day_resolve_end, priority=2),
            "del_player": EventListener(self.on_del_player),
            "apply_totem": EventListener(self.on_apply_totem),
            "lynch": EventListener(self.on_lynch),
            "chk_win": EventListener(self.on_chk_win),
            "revealroles_role": EventListener(self.on_revealroles_role),
            "update_stats": EventListener(self.on_update_stats),
            "begin_night": EventListener(self.on_begin_night),
            "num_totems": EventListener(self.on_num_totems)
        }

        self.TOTEM_CHANCES = {totem: {} for totem in self.DEFAULT_TOTEM_CHANCES}
        self.set_default_totem_chances()
        for totem, roles in self.TOTEM_CHANCES.items():
            for role in roles:
                self.TOTEM_CHANCES[totem][role] = 0
        # custom totems
        self.TOTEM_CHANCES["sustenance"] = {"shaman": 60, "wolf shaman": 10, "crazed shaman": 0}
        self.TOTEM_CHANCES["hunger"] = {"shaman": 0, "wolf shaman": 40, "crazed shaman": 0}
        # extra shaman totems
        self.TOTEM_CHANCES["revealing"]["shaman"] = 10
        self.TOTEM_CHANCES["death"]["shaman"] = 10
        self.TOTEM_CHANCES["pacifism"]["shaman"] = 10
        self.TOTEM_CHANCES["silence"]["shaman"] = 10
        # extra WS totems
        self.TOTEM_CHANCES["death"]["wolf shaman"] = 10
        self.TOTEM_CHANCES["revealing"]["wolf shaman"] = 10
        self.TOTEM_CHANCES["luck"]["wolf shaman"] = 10
        self.TOTEM_CHANCES["silence"]["wolf shaman"] = 10
        self.TOTEM_CHANCES["pacifism"]["wolf shaman"] = 10

        self.hunger_levels = DefaultUserDict(int)
        self.totem_tracking = defaultdict(int) # no need to make a user container, this is only non-empty a very short time
        self.phase = 1
        self.max_nights = 7
        self.village_hunger = 0
        self.village_hunger_percent_base = 0.4
        self.village_hunger_percent_adj = 0.03
        self.ws_num_totem_percent = 0.5
        self.ws_extra_totem = 0
        self.village_starve = 0
        self.max_village_starve = 3
        self.num_retribution = 0
        self.saved_messages = {} # type: Dict[str, str]
        kwargs = dict(chan=False, pm=True, playing=True, silenced=True, phases=("night",),
                      roles=("shaman", "wolf shaman"), register=False)
        self.feed_command = command("feed", **kwargs)(self.feed)

    def startup(self):
        super().startup()
        self.phase = 1
        self.village_starve = 0
        self.hunger_levels.clear()
        self.saved_messages = {
            "wolf_shaman_notify": messages.messages["wolf_shaman_notify"],
            "vengeful_turn": messages.messages["vengeful_turn"],
            "lynch_reveal": messages.messages["lynch_reveal"]
        }

        messages.messages["wolf_shaman_notify"] = "" # don't tell WS they can kill
        messages.messages["vengeful_turn"] = messages.messages["boreal_turn"]
        messages.messages["lynch_reveal"] = messages.messages["boreal_exile"]
        self.feed_command.register()

    def teardown(self):
        super().teardown()
        self.hunger_levels.clear()
        for key, value in self.saved_messages.items():
            messages.messages[key] = value
        self.feed_command.remove()

    def on_totem_assignment(self, evt, var, player, role):
        if role == "shaman":
            # In phase 2, we want to hand out as many retribution totems as there are active VGs (if possible)
            if self.num_retribution > 0:
                self.num_retribution -= 1
                evt.data["totems"] = {"retribution": 1}

    def on_transition_night_begin(self, evt, var):
        num_s = len(get_players(var, ("shaman",), mainroles=var.ORIGINAL_MAIN_ROLES))
        num_ws = len(get_players(var, ("wolf shaman",)))
        # as wolf shamans die, we want to pass some extras onto the remaining ones; each ws caps at 2 totems though
        self.ws_extra_totem = int(num_s * self.ws_num_totem_percent) - num_ws

    def on_transition_night_end(self, evt, var):
        from src.roles import vengefulghost
        # determine how many retribution totems we need to hand out tonight
        self.num_retribution = sum(1 for p in vengefulghost.GHOSTS if vengefulghost.GHOSTS[p][0] != "!")
        if self.num_retribution > 0:
            self.phase = 2
        # determine how many tribe members need to be fed. It's a percentage of remaining shamans
        # Each alive WS reduces the percentage needed; the number is rounded off (.5 rounding to even)
        percent = self.village_hunger_percent_base - self.village_hunger_percent_adj * len(get_players(var, ("wolf shaman",)))
        self.village_hunger = round(len(get_players(var, ("shaman",))) * percent)

    def on_wolf_numkills(self, evt, var, wolf):
        evt.data["numkills"] = 0

    def on_num_totems(self, evt, var, player, role):
        if role == "wolf shaman" and self.ws_extra_totem > 0:
            self.ws_extra_totem -= 1
            evt.data["num"] = 2

    def on_transition_day_begin(self, evt, var):
        from src.roles import vengefulghost
        num_wendigos = len(vengefulghost.GHOSTS)
        num_wolf_shamans = len(get_players(var, ("wolf shaman",)))
        ps = get_players(var)
        for p in ps:
            if get_main_role(p) in Wolfteam:
                continue # wolf shamans can't starve

            if self.totem_tracking[p] > 0:
                # if sustenance totem made it through, fully feed player
                self.hunger_levels[p] = 0
            elif self.totem_tracking[p] < 0:
                # if hunger totem made it through, fast-track player to starvation
                if self.hunger_levels[p] < 3:
                    self.hunger_levels[p] = 3

            # apply natural hunger
            self.hunger_levels[p] += 1

            if self.hunger_levels[p] >= 5:
                # if they hit 5, they die of starvation
                # if there are less VGs than alive wolf shamans, they become a wendigo as well
                if num_wendigos < num_wolf_shamans:
                    num_wendigos += 1
                    change_role(var, p, get_main_role(p), "vengeful ghost", message=None)
                add_dying(var, p, killer_role="villager", reason="boreal_starvation")
            elif self.hunger_levels[p] >= 3:
                # if they are at 3 or 4, alert them that they are hungry
                p.send(messages["boreal_hungry"])

        self.totem_tracking.clear()

    def on_transition_day_resolve_end(self, evt, var, victims):
        if len(evt.data["dead"]) == 0:
            evt.data["novictmsg"] = False
        # say if the village went hungry last night (and apply those effects if it did)
        if self.village_hunger > 0:
            self.village_starve += 1
            evt.data["message"]["*"].append(messages["boreal_village_hungry"])
        # say how many days remaining
        remain = self.max_nights - var.NIGHT_COUNT
        if remain > 0:
            evt.data["message"]["*"].append(messages["boreal_day_count"].format(remain))

    def on_lynch(self, evt, var, votee, voters):
        if get_main_role(votee) not in Wolfteam:
            # if there are less VGs than alive wolf shamans, they become a wendigo as well
            from src.roles import vengefulghost
            num_wendigos = len(vengefulghost.GHOSTS)
            num_wolf_shamans = len(get_players(var, ("wolf shaman",)))
            if num_wendigos < num_wolf_shamans:
                change_role(var, votee, get_main_role(votee), "vengeful ghost", message=None)

    def on_del_player(self, evt, var, player, all_roles, death_triggers):
        for a, b in list(self.hunger_levels.items()):
            if player in (a, b):
                del self.hunger_levels[a]

    def on_apply_totem(self, evt, var, role, totem, shaman, target):
        if totem == "sustenance":
            if target is users.Bot:
                # fed the village
                self.village_hunger -= 1
            else:
                # gave to a player
                self.totem_tracking[target] += 1
        elif totem == "hunger":
            if target is users.Bot:
                # tried to starve the village
                self.village_hunger += 1
            else:
                # gave to a player
                self.totem_tracking[target] -= 1

    def on_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if self.village_starve == self.max_village_starve and var.PHASE == "day":
            # if village didn't feed the NPCs enough nights, the starving tribe members destroy themselves from within
            # this overrides built-in win conds (such as all wolves being dead)
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["boreal_village_starve"]
        elif var.NIGHT_COUNT == self.max_nights and var.PHASE == "day":
            # if village survived for N nights without losing, they outlast the storm and win
            # this overrides built-in win conds (such as same number of wolves as villagers)
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["boreal_time_up"]
        elif evt.data["winner"] == "villagers":
            evt.data["message"] = messages["boreal_village_win"]
        elif evt.data["winner"] == "wolves":
            evt.data["message"] = messages["boreal_wolf_win"]

    def on_revealroles_role(self, evt, var, player, role):
        if player in self.hunger_levels:
            evt.data["special_case"].append(messages["boreal_revealroles"].format(self.hunger_levels[player]))

    def on_update_stats(self, evt, var, player, main_role, reveal_role, all_roles):
        if main_role == "vengeful ghost":
            evt.data["possible"].add("shaman")

    def on_begin_night(self, evt, var):
        evt.data["messages"].append(messages["boreal_night_reminder"].format(self.village_hunger, self.village_starve))

    def feed(self, wrapper: MessageDispatcher, message: str):
        """Give your totem to the tribe members."""
        from src.roles.shaman import TOTEMS as s_totems, SHAMANS as s_shamans
        from src.roles.wolfshaman import TOTEMS as ws_totems, SHAMANS as ws_shamans

        var = wrapper.game_state

        pieces = re.split(" +", message)
        valid = {"sustenance", "hunger"}
        state_vars = ((s_totems, s_shamans), (ws_totems, ws_shamans))
        for TOTEMS, SHAMANS in state_vars:
            if wrapper.source not in TOTEMS:
                continue

            totem_types = set(TOTEMS[wrapper.source].keys()) & valid
            given = match_totem(var, pieces[0], scope=totem_types)
            if not given and TOTEMS[wrapper.source].get("sustenance", 0) + TOTEMS[wrapper.source].get("hunger", 0) > 1:
                wrapper.send(messages["boreal_ambiguous_feed"])
                return

            for totem in valid:
                if (given and totem != given.get().key) or TOTEMS[wrapper.source].get(totem, 0) == 0:
                    continue # doesn't have a totem that can be used to feed tribe

                SHAMANS[wrapper.source][totem].append(users.Bot)
                if len(SHAMANS[wrapper.source][totem]) > TOTEMS[wrapper.source][totem]:
                    SHAMANS[wrapper.source][totem].pop(0)

                wrapper.pm(messages["boreal_feed_success"].format(totem))
                # send_wolfchat_message already takes care of checking whether the player has access to wolfchat,
                # so this will only be sent for wolf shamans
                send_wolfchat_message(var, wrapper.source, messages["boreal_wolfchat_feed"].format(wrapper.source),
                                      {"wolf shaman"}, role="wolf shaman", command="feed")
                return
