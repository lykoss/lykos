import random
from collections import defaultdict
from typing import List, Tuple, Dict
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.functions import get_players, get_all_players, get_main_role
from src.events import EventListener, find_listener
from src.containers import DefaultUserDict
from src.status import add_dying
from src import channels, users

@game_mode("boreal", minp=6, maxp=24, likelihood=1)
class BorealMode(GameMode):
    """Some shamans are working against you. Exile them before you starve!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.LIMIT_ABSTAIN = False
        self.DEFAULT_ROLE = "shaman"
        self.ROLE_GUIDE = {
            6: ["wolf shaman"],
            10: ["wolf shaman(2)"],
            15: ["wolf shaman(3)"],
            20: ["wolf shaman(4)"]
            }
        self.EVENTS = {
            "transition_night_end": EventListener(self.on_transition_night_end, priority=1),
            "wolf_numkills": EventListener(self.on_wolf_numkills),
            "totem_assignment": EventListener(self.on_totem_assignment),
            "transition_day_begin": EventListener(self.on_transition_day_begin, priority=8),
            "transition_day_resolve_end": EventListener(self.on_transition_day_resolve_end, priority=2),
            "del_player": EventListener(self.on_del_player),
            "apply_totem": EventListener(self.on_apply_totem),
            "lynch": EventListener(self.on_lynch),
            "chk_win": EventListener(self.on_chk_win),
            "revealroles_role": EventListener(self.on_revealroles_role)
        }

        self.TOTEM_CHANCES = {totem: {} for totem in self.DEFAULT_TOTEM_CHANCES}
        self.set_default_totem_chances()
        for totem, roles in self.TOTEM_CHANCES.items():
            for role in roles:
                self.TOTEM_CHANCES[totem][role] = 0
        # custom totems
        self.TOTEM_CHANCES["sustenance"] = {"shaman": 10, "wolf shaman": 0, "crazed shaman": 0}
        self.TOTEM_CHANCES["hunger"] = {"shaman": 0, "wolf shaman": 6, "crazed shaman": 0}
        # extra shaman totems
        self.TOTEM_CHANCES["revealing"]["shaman"] = 2
        self.TOTEM_CHANCES["death"]["shaman"] = 1
        self.TOTEM_CHANCES["influence"]["shaman"] = 4
        self.TOTEM_CHANCES["luck"]["shaman"] = 2
        self.TOTEM_CHANCES["silence"]["shaman"] = 1
        # extra WS totems: note that each WS automatically gets a hunger totem in addition to this in phase 1
        self.TOTEM_CHANCES["death"]["wolf shaman"] = 1
        self.TOTEM_CHANCES["misdirection"]["wolf shaman"] = 4
        self.TOTEM_CHANCES["luck"]["wolf shaman"] = 4
        self.TOTEM_CHANCES["silence"]["wolf shaman"] = 1
        self.TOTEM_CHANCES["influence"]["wolf shaman"] = 4

        self.hunger_levels = DefaultUserDict(int)
        self.totem_tracking = defaultdict(int) # no need to make a user container, this is only non-empty a very short time
        self.phase = 1
        self.max_nights = 7
        self.num_retribution = 0
        self.saved_messages = {} # type: Dict[str, str]

    def startup(self):
        super().startup()
        self.phase = 1
        self.hunger_levels.clear()
        self.saved_messages = {
            "wolf_shaman_notify": messages.messages["wolf_shaman_notify"],
            "vengeful_turn": messages.messages["vengeful_turn"],
            "lynch_reveal": messages.messages["lynch_reveal"]
        }

        messages.messages["wolf_shaman_notify"] = "" # don't tell WS they can kill
        messages.messages["vengeful_turn"] = messages.messages["boreal_turn"]
        messages.messages["lynch_reveal"] = messages.messages["boreal_exile"]

    def teardown(self):
        super().teardown()
        self.hunger_levels.clear()
        for key, value in self.saved_messages.items():
            messages.messages[key] = value

    def on_totem_assignment(self, evt, var, role):
        if role == "shaman":
            # In phase 2, we want to hand out as many retribution totems as there are active VGs (if possible)
            if self.num_retribution > 0:
                self.num_retribution -= 1
                evt.data["totems"] = {"retribution": 1}
        elif role == "wolf shaman":
            # In phase 1, wolf shamans get a bonus hunger totem
            if self.phase == 1:
                if "hunger" in evt.data["totems"]:
                    evt.data["totems"]["hunger"] += 1
                else:
                    evt.data["totems"]["hunger"] = 1

    def on_transition_night_end(self, evt, var):
        from src.roles import vengefulghost
        # determine how many retribution totems we need to hand out tonight
        self.num_retribution = sum(1 for p in vengefulghost.GHOSTS if vengefulghost.GHOSTS[p][0] != "!")
        if self.num_retribution > 0:
            self.phase = 2

    def on_wolf_numkills(self, evt, var):
        evt.data["numkills"] = 0

    def on_transition_day_begin(self, evt, var):
        ps = get_players()
        for p in ps:
            if get_main_role(p) == "wolf shaman":
                continue # wolf shamans can't starve

            if self.totem_tracking[p] > 0:
                # if sustenance totem made it through, fully feed player
                self.hunger_levels[p] = 0
            elif self.totem_tracking[p] < 0:
                # if hunger totem made it through, fast-track player to starvation
                self.hunger_levels[p] += 2

            # apply natural hunger
            self.hunger_levels[p] += 1

            if self.hunger_levels[p] >= 5:
                # if they hit 5, they die of starvation
                # if there are less VGs than alive wolf shamans, they become a wendigo as well
                self.maybe_make_wendigo(var, p)
                add_dying(var, p, killer_role="villager", reason="boreal_starvation")
            elif self.hunger_levels[p] >= 3:
                # if they are at 3 or 4, alert them that they are hungry
                p.send(messages["boreal_hungry"])

        self.totem_tracking.clear()

    def on_transition_day_resolve_end(self, evt, var, victims):
        if len(evt.data["dead"]) == 0:
            evt.data["novictmsg"] = False
        remain = self.max_nights - var.NIGHT_COUNT
        evt.data["message"]["*"].append(messages["boreal_day_count"].format(remain, "s" if remain > 1 else ""))

    def maybe_make_wendigo(self, var, player):
        from src.roles import vengefulghost
        num_wendigos = len(vengefulghost.GHOSTS)
        num_wolf_shamans = len(get_players(("wolf shaman",)))
        if num_wendigos < num_wolf_shamans:
            var.ROLES["vengeful ghost"].add(player)

    def on_lynch(self, evt, var, votee, voters):
        if get_main_role(votee) == "shaman":
            # if there are less VGs than alive wolf shamans, they become a wendigo as well
            self.maybe_make_wendigo(var, votee)

    def on_del_player(self, evt, var, player, all_roles, death_triggers):
        for a, b in list(self.hunger_levels.items()):
            if player in (a, b):
                del self.hunger_levels[a]

    def on_apply_totem(self, evt, var, role, totem, shaman, target):
        if totem == "sustenance":
            self.totem_tracking[target] += 1
        elif totem == "hunger":
            self.totem_tracking[target] -= 1

    def on_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if var.NIGHT_COUNT == self.max_nights and var.PHASE == "day":
            # if village survived for N nights without losing, they outlast the storm and win
            if evt.data["winner"] is None:
                evt.data["winner"] = "villagers"
                evt.data["message"] = messages["boreal_time_up"]
        elif evt.data["winner"] == "villagers":
            evt.data["message"] = messages["boreal_village_win"]
        elif evt.data["winner"] == "wolves":
            evt.data["message"] = messages["boreal_wolf_win"]

    def on_revealroles_role(self, evt, var, player, role):
        if player in self.hunger_levels:
            evt.data["special_case"].append(messages["boreal_revealroles"].format(self.hunger_levels[player]))
