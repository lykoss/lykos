from __future__ import annotations

# Imports all gamemode definitions
import os.path
import glob
import importlib
from typing import Dict, Tuple, Optional
from src.messages import messages
from src.gamestate import GameState
from src.events import Event, EventListener
from src.cats import All, Cursed, Wolf, Wolfchat, Innocent, Village, Neutral, Hidden, Team_Switcher, Win_Stealer, Nocturnal, Killer, Spy

__all__ = ["InvalidModeException", "game_mode", "GameMode", "GAME_MODES"]

class InvalidModeException(Exception):
    pass

class CustomSettings:
    def __init__(self):
        self._overridden = set()
        self._abstain_enabled: bool = True
        self._limit_abstain: bool = True
        self.self_lynch_allowed: bool = True
        self.default_role: str = "villager"
        self.hidden_role: str = "villager"
        self.start_with_day: bool = False
        self.always_pm_role: bool = False
        self._role_reveal: str = "on" # on/off/team
        self._stats_type: str = "default" # default/accurate/team/disabled

        self._day_time_limit: Optional[int] = None
        self._day_time_warn: Optional[int] = None
        self._short_day_time_limit: Optional[int] = None
        self._short_day_time_warn: Optional[int] = None
        self._night_time_limit: Optional[int] = None
        self._night_time_warn: Optional[int] = None

    @property
    def abstain_enabled(self) -> bool:
        return self._abstain_enabled

    @abstain_enabled.setter
    def abstain_enabled(self, value: bool):
        if "abstain_enabled" in self._overridden:
            return
        self._abstain_enabled = value

    @property
    def limit_abstain(self) -> bool:
        return self._limit_abstain

    @limit_abstain.setter
    def limit_abstain(self, value: bool):
        if "limit_abstain" in self._overridden:
            return
        self._limit_abstain = value

    @property
    def role_reveal(self) -> str:
        return self._role_reveal

    @role_reveal.setter
    def role_reveal(self, value: str):
        if "role_reveal" in self._overridden:
            return
        self._role_reveal = value

    @property
    def stats_type(self) -> str:
        return self._stats_type

    @stats_type.setter
    def stats_type(self, value: str):
        if "stats_type" in self._overridden:
            return
        self._stats_type = value

    @property
    def day_time_limit(self) -> int:
        if self._day_time_limit is not None:
            return self._day_time_limit
        raise AttributeError("day_time_limit")

    @day_time_limit.setter
    def day_time_limit(self, value: int):
        self._day_time_limit = value

    @property
    def day_time_warn(self) -> int:
        if self._day_time_warn is not None:
            return self._day_time_warn
        raise AttributeError("day_time_warn")

    @day_time_warn.setter
    def day_time_warn(self, value: int):
        self._day_time_warn = value

    @property
    def short_day_time_limit(self) -> int:
        if self._short_day_time_limit is not None:
            return self._short_day_time_limit
        raise AttributeError("short_day_time_limit")

    @short_day_time_limit.setter
    def short_day_time_limit(self, value: int):
        self._short_day_time_limit = value

    @property
    def short_day_time_warn(self) -> int:
        if self._short_day_time_warn is not None:
            return self._short_day_time_warn
        raise AttributeError("short_day_time_warn")

    @short_day_time_warn.setter
    def short_day_time_warn(self, value: int):
        self._short_day_time_warn = value

    @property
    def night_time_limit(self) -> int:
        if self._night_time_limit is not None:
            return self._night_time_limit
        raise AttributeError("night_time_limit")

    @night_time_limit.setter
    def night_time_limit(self, value: int):
        self._night_time_limit = value

    @property
    def night_time_warn(self) -> int:
        if self._night_time_warn is not None:
            return self._night_time_warn
        raise AttributeError("night_time_warn")

    @night_time_warn.setter
    def night_time_warn(self, value: int):
        self._night_time_warn = value

class GameMode:
    def __init__(self, arg=""):
        # Default values for the role sets and secondary roles restrictions
        self.ROLE_SETS = {
            "gunner/sharpshooter": {"gunner": 4, "sharpshooter": 1},
        }
        self.SECONDARY_ROLES = {
            "cursed villager"   : All - Cursed - Wolf - Innocent - {"seer", "oracle"},
            "gunner"            : Village + Neutral + Hidden - Innocent - Team_Switcher,
            "sharpshooter"      : Village + Neutral + Hidden - Innocent - Team_Switcher,
            "mayor"             : All - Innocent - Win_Stealer,
            "assassin"          : All - Nocturnal + Killer - Spy + Wolfchat - Wolf - Innocent - Team_Switcher - {"traitor"},
        }
        self.DEFAULT_TOTEM_CHANCES = self.TOTEM_CHANCES = {}
        self.NUM_TOTEMS = {}

        self.EVENTS = {}

        self.CUSTOM_SETTINGS = CustomSettings()

        # Support all shamans and totems
        # Listeners should add their custom totems with non-zero chances, and custom roles in evt.data["shaman_roles"]
        # Totems (both the default and custom ones) get filled with every shaman role at a chance of 0
        # Add totems with a priority of 1 and shamans with a priority of 3
        # Listeners at priority 5 can make use of this information freely
        evt = Event("default_totems", {"shaman_roles": set()})
        evt.dispatch(self.TOTEM_CHANCES)

        shamans = evt.data["shaman_roles"]
        for chances in self.TOTEM_CHANCES.values():
            if chances.keys() != shamans:
                for role in shamans:
                    if role not in chances:
                        chances[role] = 0 # default to 0 for new totems/shamans

        for role in shamans:
            if role not in self.NUM_TOTEMS:
                self.NUM_TOTEMS[role] = 1 # shamans get 1 totem per night by default

        if not arg:
            return

        arg = arg.replace("=", ":").replace(";", ",")

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.lower().replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise InvalidModeException(messages["invalid_mode_args"].format(arg))

            key, val = change
            if key == "role reveal":
                if val not in ("on", "off", "team"):
                    raise InvalidModeException(messages["invalid_reveal"].format(val))
                self.CUSTOM_SETTINGS.role_reveal = val
                self.CUSTOM_SETTINGS._overridden.add("role_reveal")
                if val == "off":
                    self.CUSTOM_SETTINGS.stats_type = "disabled"
                elif val == "team":
                    self.CUSTOM_SETTINGS.stats_type = "team"
            elif key == "stats":
                if val not in ("default", "accurate", "team", "disabled"):
                    raise InvalidModeException(messages["invalid_stats"].format(val))
                self.CUSTOM_SETTINGS.stats_type = val
                self.CUSTOM_SETTINGS._overridden.add("stats_type")
            elif key == "abstain":
                if val == "enabled":
                    self.CUSTOM_SETTINGS.abstain_enabled = True
                    self.CUSTOM_SETTINGS.limit_abstain = False
                elif val == "restricted":
                    self.CUSTOM_SETTINGS.abstain_enabled = True
                    self.CUSTOM_SETTINGS.limit_abstain = True
                elif val == "disabled":
                    self.CUSTOM_SETTINGS.abstain_enabled = False
                else:
                    raise InvalidModeException(messages["invalid_abstain"].format(val))
                self.CUSTOM_SETTINGS._overridden.update(("abstain_enabled", "limit_abstain"))

    def startup(self):
        for event, listeners in self.EVENTS.items():
            if isinstance(listeners, EventListener):
                listeners.install(event)
            else:
                for listener in listeners:
                    listener.install(event)

    def teardown(self):
        for event, listeners in self.EVENTS.items():
            if isinstance(listeners, EventListener):
                listeners.remove(event)
            else:
                for listener in listeners:
                    listener.remove(event)

    def can_vote_bot(self, var):
        return False

    def set_default_totem_chances(self):
        if self.TOTEM_CHANCES is self.DEFAULT_TOTEM_CHANCES:
            return # nothing more we can do
        for totem, chances in self.TOTEM_CHANCES.items():
            if totem not in self.DEFAULT_TOTEM_CHANCES or self.DEFAULT_TOTEM_CHANCES[totem].keys() == chances.keys():
                continue
            for role, value in self.DEFAULT_TOTEM_CHANCES[totem].items():
                if role not in chances:
                    chances[role] = value

    # Here so any game mode can use it
    def lovers_chk_win(self, evt: Event, var: GameState, rolemap, mainroles, lpl, lwolves, lrealwolves):
        winner = evt.data["winner"]
        if winner in Win_Stealer:
            return # fool won, lovers can't win even if they would
        from src.roles.matchmaker import get_lovers
        all_lovers = get_lovers(var)
        if len(all_lovers) != 1:
            return # we need exactly one cluster alive for this to trigger

        lovers = all_lovers[0]

        if len(lovers) == lpl:
            evt.data["winner"] = "lovers"
            evt.data["message"] = messages["lovers_win"]

    def all_dead_chk_win(self, evt: Event, var: GameState, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if evt.data["winner"] == "no_team_wins":
            evt.data["winner"] = "everyone"
            evt.data["message"] = messages["everyone_died_won"]

GAME_MODES: Dict[str, Tuple[GameMode, int, int, int]] = {}

def game_mode(name: str, minp: int, maxp: int, likelihood: int = 0):
    def decor(c: GameMode):
        c.name = name
        GAME_MODES[name] = (c, minp, maxp, likelihood)
        return c
    return decor

path = os.path.dirname(os.path.abspath(__file__))
search = os.path.join(path, "*.py")

for f in glob.iglob(search):
    f = os.path.basename(f)
    n, _ = os.path.splitext(f)
    if f.startswith("_"):
        continue
    importlib.import_module("." + n, package="src.gamemodes")
