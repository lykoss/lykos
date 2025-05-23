from __future__ import annotations

import re
from collections import defaultdict

from src import config, users
from src.cats import Wolfteam, Village
from src.containers import DefaultUserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event
from src.events import EventListener
from src.functions import get_players, get_main_role, change_role, match_totem
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.messages import messages
from src.roles.helper.wolves import send_wolfchat_message
from src.status import add_dying

@game_mode("boreal", minp=6, maxp=24)
class BorealMode(GameMode):
    """Some shamans are working against you. Exile them before you starve!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.limit_abstain = False
        self.CUSTOM_SETTINGS.self_vote_allowed = False
        self.CUSTOM_SETTINGS.default_role = "shaman"

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
            "transition_day_resolve": EventListener(self.on_transition_day_resolve),
            "del_player": EventListener(self.on_del_player),
            "apply_totem": EventListener(self.on_apply_totem),
            "day_vote": EventListener(self.on_day_vote),
            "chk_win": EventListener(self.on_chk_win),
            "revealroles_role": EventListener(self.on_revealroles_role),
            "update_stats": EventListener(self.on_update_stats),
            "begin_night": EventListener(self.on_begin_night),
            "num_totems": EventListener(self.on_num_totems)
        }

        self.MESSAGE_OVERRIDES = {
            # suppress the "you can !kill" line; wolf shamans get most of their info from shaman_notify
            # and wolves can't kill in this mode
            "wolf_shaman_notify": None
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
        self.max_nights = config.Main.get("gameplay.modes.boreal.nights")
        self.village_hunger = 0
        self.village_hunger_percent_base = config.Main.get("gameplay.modes.boreal.tribe.base")
        self.village_hunger_percent_adj = config.Main.get("gameplay.modes.boreal.tribe.adjust")
        self.ws_num_totem_percent = 0.5
        self.ws_extra_totem = 0
        self.village_starve = 0
        self.max_village_starve = config.Main.get("gameplay.modes.boreal.tribe.starve")
        self.num_retribution = 0
        self.saved_messages: dict[str, str] = {}
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
            "day_vote_reveal": messages.messages["day_vote_reveal"]
        }

        messages.messages["wolf_shaman_notify"] = "" # don't tell WS they can kill
        messages.messages["vengeful_turn"] = messages.messages["boreal_turn"]
        messages.messages["day_vote_reveal"] = messages.messages["boreal_exile"]
        self.feed_command.register()

    def teardown(self):
        super().teardown()
        self.hunger_levels.clear()
        for key, value in self.saved_messages.items():
            messages.messages[key] = value
        self.feed_command.remove()

    def on_totem_assignment(self, evt: Event, var: GameState, player, role):
        if role == "shaman":
            # In phase 2, we want to hand out as many retribution totems as there are active VGs (if possible)
            if self.num_retribution > 0:
                self.num_retribution -= 1
                evt.data["totems"] = {"retribution": 1}

    def on_transition_night_begin(self, evt: Event, var: GameState):
        num_s = len(get_players(var, ("shaman",), mainroles=var.original_main_roles))
        num_ws = len(get_players(var, ("wolf shaman",)))
        # as wolf shamans die, we want to pass some extras onto the remaining ones; each ws caps at 2 totems though
        self.ws_extra_totem = int(num_s * self.ws_num_totem_percent) - num_ws

    def on_transition_night_end(self, evt: Event, var: GameState):
        from src.roles import vengefulghost
        # determine how many retribution totems we need to hand out tonight
        self.num_retribution = sum(1 for p in vengefulghost.GHOSTS if vengefulghost.GHOSTS[p][0] != "!")
        if self.num_retribution > 0:
            self.phase = 2
        # determine how many tribe members need to be fed. It's a percentage of remaining shamans
        # Each alive WS reduces the percentage needed; the number is rounded off (.5 rounding to even)
        percent = self.village_hunger_percent_base - self.village_hunger_percent_adj * len(get_players(var, ("wolf shaman",)))
        self.village_hunger = round(len(get_players(var, ("shaman",))) * percent)

    def on_wolf_numkills(self, evt: Event, var: GameState, wolf):
        evt.data["numkills"] = 0

    def on_num_totems(self, evt: Event, var: GameState, player, role):
        if role == "wolf shaman" and self.ws_extra_totem > 0:
            self.ws_extra_totem -= 1
            evt.data["num"] = 2

    def on_transition_day_begin(self, evt: Event, var: GameState):
        from src.roles import vengefulghost
        num_wendigos = len(vengefulghost.GHOSTS)
        num_wolf_shamans = len(get_players(var, ("wolf shaman",)))
        ps = get_players(var)
        for p in ps:
            if get_main_role(var, p) in Wolfteam:
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
                    change_role(var, p, get_main_role(var, p), "vengeful ghost", message=None)
                add_dying(var, p, killer_role="villager", reason="boreal_starvation")
            elif self.hunger_levels[p] >= 3:
                # if they are at 3 or 4, alert them that they are hungry
                p.send(messages["boreal_hungry"])

        self.totem_tracking.clear()

    def on_transition_day_resolve(self, evt: Event, var: GameState, dead, killers):
        # never play the "no victims" message
        evt.data["novictmsg"] = False
        # say if the village went hungry last night (and apply those effects if it did)
        if self.village_hunger > 0:
            self.village_starve += 1
            evt.data["message"]["*"].append(messages["boreal_village_hungry"])
        # say how many days remaining
        remain = self.max_nights - var.night_count
        if remain > 0:
            evt.data["message"]["*"].append(messages["boreal_day_count"].format(remain))

    def on_day_vote(self, evt: Event, var: GameState, votee, voters):
        if get_main_role(var, votee) not in Wolfteam:
            # if there are less VGs than alive wolf shamans, they become a wendigo as well
            from src.roles import vengefulghost
            num_wendigos = len(vengefulghost.GHOSTS)
            num_wolf_shamans = len(get_players(var, ("wolf shaman",)))
            if num_wendigos < num_wolf_shamans:
                change_role(var, votee, get_main_role(var, votee), "vengeful ghost", message=None)

    def on_del_player(self, evt: Event, var: GameState, player, all_roles, death_triggers):
        for a, b in list(self.hunger_levels.items()):
            if player in (a, b):
                del self.hunger_levels[a]

    def on_apply_totem(self, evt: Event, var: GameState, role, totem, shaman, target):
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

    def on_chk_win(self, evt: Event, var: GameState, rolemap, mainroles, lpl, lwolves, lrealwolves, lvampires):
        if self.village_starve == self.max_village_starve and var.current_phase == "day":
            # if village didn't feed the NPCs enough nights, the starving tribe members destroy themselves from within
            # this overrides built-in win conds (such as all wolves being dead)
            evt.data["winner"] = Wolfteam
            evt.data["message"] = messages["boreal_village_starve"]
        elif var.night_count == self.max_nights and var.current_phase == "day":
            # if village survived for N nights without losing, they outlast the storm and win
            # this overrides built-in win conds (such as same number of wolves as villagers)
            evt.data["winner"] = Village
            evt.data["message"] = messages["boreal_time_up"]
        elif evt.data["winner"] is Village:
            evt.data["message"] = messages["boreal_village_win"]
        elif evt.data["winner"] is Wolfteam:
            evt.data["message"] = messages["boreal_wolf_win"]

    def on_revealroles_role(self, evt: Event, var: GameState, player, role):
        if player in self.hunger_levels:
            evt.data["special_case"].append(messages["boreal_revealroles"].format(self.hunger_levels[player]))

    def on_update_stats(self, evt: Event, var: GameState, player, main_role, reveal_role, all_roles):
        if main_role == "vengeful ghost":
            evt.data["possible"].add("shaman")

    def on_begin_night(self, evt: Event, var: GameState):
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
            given = match_totem(pieces[0], scope=totem_types)
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
