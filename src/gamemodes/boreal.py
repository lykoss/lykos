import random
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
            "del_player": EventListener(self.on_del_player),
            "apply_totem": EventListener(self.on_apply_totem),
            "lynch": EventListener(self.on_lynch),
            "chk_win": EventListener(self.on_chk_win)
        }

        self.TOTEM_CHANCES = {totem: {} for totem in self.DEFAULT_TOTEM_CHANCES}
        self.set_default_totem_chances()
        for totem, roles in self.TOTEM_CHANCES.items():
            for role in roles:
                self.TOTEM_CHANCES[totem][role] = 0
        self.TOTEM_CHANCES["sustenance"] = {"shaman": 1, "wolf shaman": 1, "crazed shaman": 0}
        self.TOTEM_CHANCES["hunger"] = {"shaman": 0, "wolf shaman": 2, "crazed shaman": 0}

        self.hunger_levels = DefaultUserDict(int)
        self.phase = 1
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
            else:
                evt.data["totems"] = {"sustenance": 1}
        elif role == "wolf shaman":
            if self.phase == 1:
                evt.data["totems"] = {"sustenance": 1, "hunger": 2}
            else:
                evt.data["totems"] = {"hunger": 1}

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
            # cap player sustenance at +1, then apply natural hunger
            self.hunger_levels[p] = min(self.hunger_levels[p], 1)
            self.hunger_levels[p] -= 1

            if self.hunger_levels[p] <= -5:
                # if they hit -5, they die of starvation and become a wendigo
                var.ROLES["vengeful ghost"].add(p)
                add_dying(var, p, killer_role="villager", reason="boreal_starvation")
            elif self.hunger_levels[p] <= -3:
                # if they are at -3 or -4, alert them that they are hungry
                p.send(messages["boreal_hungry"])

    def on_lynch(self, evt, var, votee, voters):
        if get_main_role(votee) == "shaman":
            var.ROLES["vengeful ghost"].add(votee)

    def on_del_player(self, evt, var, player, all_roles, death_triggers):
        for a, b in list(self.hunger_levels.items()):
            if player in (a, b):
                del self.hunger_levels[a]

    def on_apply_totem(self, evt, var, role, totem, shaman, target):
        if totem == "sustenance":
            self.hunger_levels[target] += 1
        elif totem == "hunger":
            self.hunger_levels[target] -= 1

    def on_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if var.NIGHT_COUNT == 10 and var.PHASE == "day":
            if evt.data["winner"] is None:
                evt.data["winner"] = "villagers"
                evt.data["message"] = messages["boreal_time_up"]
        elif evt.data["winner"] == "villagers":
            evt.data["message"] = messages["boreal_village_win"]
        elif evt.data["winner"] == "wolves":
            evt.data["message"] = messages["boreal_wolf_win"]
