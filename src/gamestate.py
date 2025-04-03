from __future__ import annotations

import copy
import math
import threading
from typing import Any, Optional, Callable, ClassVar, TYPE_CHECKING
import time

from src.containers import UserSet, UserDict, UserList
from src.messages import messages
from src.cats import All
from src import config
from src.users import User
from src import channels, random

if TYPE_CHECKING:
    from src.gamemodes import GameMode

__all__ = ["GameState", "PregameState", "set_gamemode"]

def set_gamemode(var: PregameState, arg: str) -> bool:
    from src.gamemodes import GAME_MODES, InvalidModeException
    modeargs = arg.split("=", 1)

    modeargs = [a.strip() for a in modeargs]
    if modeargs[0] in GAME_MODES:
        md = modeargs.pop(0)
        try:
            gm = GAME_MODES[md][0](*modeargs)
            gm.startup()
            var.current_mode = gm
            return True
        except InvalidModeException as e:
            channels.Main.send(f"Invalid mode: {e}")
            return False

    channels.Main.send(messages["game_mode_not_found"].format(modeargs[0]))
    return False

class PregameState:
    def __init__(self):
        self.players = UserList()
        self.current_phase: str = "join"
        self.game_id: float = time.time()
        self.next_phase: Optional[str] = None
        # Note: current_mode is None for all but the !start machinery
        self.current_mode: Optional[GameMode] = None

    @property
    def in_game(self):
        return False

    def teardown(self):
        if self.current_mode is not None:
            self.current_mode.teardown()

class GameState:
    _init_fns: ClassVar[list[Callable[[GameState], None]]] = []

    def __init__(self, pregame_state: PregameState):
        # Initialize role-specific state
        for fn in GameState._init_fns:
            fn(self)
        self.setup_started: bool = False
        self.setup_completed: bool = False
        self._torndown: bool = False
        self.current_mode: GameMode = pregame_state.current_mode
        self.game_settings: dict[str, Any] = {}
        self.game_id: float = pregame_state.game_id
        self.players = pregame_state.players
        self.roles: UserDict[str, UserSet] = UserDict()
        self._original_roles: UserDict[str, UserSet] = UserDict()
        self.main_roles: UserDict[User, str] = UserDict()
        self._original_main_roles: UserDict[User, str] = UserDict()
        self.final_roles: UserDict[User, str] = UserDict()
        self._rolestats: set[frozenset[tuple[str, int]]] = set()
        self.current_phase: str = pregame_state.current_phase
        self.next_phase: Optional[str] = None
        self.night_count: int = 0
        self.day_count: int = 0
        self.rng_seed: bytes = random.get_seed()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        attrs = cls.__dict__.copy()
        strip = ("__module__", "__dict__", "__doc__")
        for thing in strip:
            if thing in attrs:
                del attrs[thing]

        merge = ("__annotations__",)
        for thing in merge:
            if thing in attrs:
                GameState.__dict__[thing].update(attrs[thing])
                del attrs[thing]

        if "__init__" in attrs:
            GameState._init_fns.append(attrs["__init__"])
            del attrs["__init__"]

        for thing, value in attrs.items():
            if thing.startswith("__") and thing.endswith("__"):
                raise TypeError(f"GameState subclasses cannot define a {thing} member")
            setattr(GameState, thing, value)

    def begin_setup(self):
        if self.setup_completed:
            raise RuntimeError("GameState.setup() called while already setup")
        if self._torndown:
            raise RuntimeError("cannot setup a used-up GameState")
        for role in All:
            self.roles[role] = UserSet()
        self.setup_started = True

    def finish_setup(self):
        if self.setup_completed:
            raise RuntimeError("GameState.setup() called while already setup")
        if self._torndown:
            raise RuntimeError("cannot setup a used-up GameState")
        # both of these containers must be empty before we overwrite them
        assert not self._original_roles and not self._original_main_roles
        self._original_roles = copy.deepcopy(self.roles)
        self._original_main_roles = self.main_roles.copy()
        self.setup_completed = True

    def teardown(self):
        self.roles.clear()
        self._original_roles.clear()
        self._original_main_roles.clear()
        self._rolestats.clear()
        self.current_mode.teardown()
        self._torndown = True

    def _get_value(self, key: str) -> Any:
        # we don't actually need to complete setup before this can be used
        if not self.setup_started or not self.current_mode:
            raise RuntimeError("Current game state has not been setup")
        if self._torndown:
            raise RuntimeError("Current game state is no longer valid")
        if key in self.game_settings:
            return self.game_settings[key]
        return getattr(self.current_mode.CUSTOM_SETTINGS, key)

    @property
    def in_game(self):
        return self.setup_completed and not self._torndown

    def begin_phase_transition(self, phase: str):
        from src.trans import TIMERS
        if self.next_phase is not None:
            raise RuntimeError("already in phase transition")
        self.next_phase = phase
        # this is a bit convoluted, but this lets external code plug in their own phases
        # for grep: var.day_count and var.night_count get incremented here
        attr = f"{self.next_phase}_count"
        setattr(self, attr, getattr(self, attr, 0) + 1)

        if f"{self.current_phase}_limit" in TIMERS:
            TIMERS[f"{self.current_phase}_limit"][0].cancel()
            del TIMERS[f"{self.current_phase}_limit"]
        if f"{self.current_phase}_warn" in TIMERS:
            TIMERS[f"{self.current_phase}_warn"][0].cancel()
            del TIMERS[f"{self.current_phase}_warn"]

    def end_phase_transition(self, time_limit: int = 0, time_warn: int = 0, timer_cb=None, cb_args=()):
        from src.trans import TIMERS
        if self.next_phase is None:
            raise RuntimeError("not in phase transition")

        assert timer_cb is not None
        self.current_phase = self.next_phase
        self.next_phase = None
        if config.Main.get("timers.enabled"):
            if time_limit:
                timer = threading.Timer(time_limit, timer_cb, ("limit",) + tuple(cb_args))
                timer.daemon = True
                timer.start()
                TIMERS[f"{self.current_phase}_limit"] = (timer, time.time(), time_limit)

            if time_warn:
                timer = threading.Timer(time_warn, timer_cb, ("warn",) + tuple(cb_args))
                timer.daemon = True
                timer.start()
                TIMERS[f"{self.current_phase}_warn"] = (timer, time.time(), time_warn)

    def extend_phase_limit(self, minimum: int = 0):
        """Ensure that the phase limit timer has a minimum amount of seconds remaining."""
        from src.trans import TIMERS
        if minimum <= 0:
            return
        if config.Main.get("timers.enabled"):
            (timer, started, limit) = TIMERS[f"{self.current_phase}_limit"]
            elapsed = math.ceil(time.time() - started)
            if elapsed + minimum > limit:
                timer.cancel()
                extended = threading.Timer(minimum, timer.function, timer.args, timer.kwargs)
                extended.daemon = True
                extended.start()
                TIMERS[f"{self.current_phase}_limit"] = (extended, started, elapsed + minimum)

    @property
    def in_phase_transition(self):
        return self.next_phase is not None

    @property
    def original_roles(self):
        # we store the data in a UserDict so it gets dynamically updated
        # but we want to return a regular dict (and a regular underlying set)
        # since this is meant to be used then discarded
        # this is also read-only to prevent code from modifying it
        mapping = self._original_roles
        if not self.setup_completed:
            # if setup is not completed, then this is functionally identical
            mapping = self.roles
        return {name: set(value) for name, value in mapping.items()}

    @property
    def original_main_roles(self):
        mapping = self._original_main_roles
        if not self.setup_completed:
            mapping = self.main_roles
        return dict(mapping)

    @property
    def abstain_enabled(self) -> bool:
        return self._get_value("abstain_enabled")

    @property
    def limit_abstain(self) -> bool:
        return self._get_value("limit_abstain")

    @property
    def self_vote_allowed(self) -> bool:
        return self._get_value("self_vote_allowed")

    @property
    def default_role(self) -> str:
        return self._get_value("default_role")

    @property
    def hidden_role(self) -> str:
        return self._get_value("hidden_role")

    @property
    def start_with_day(self) -> bool:
        return self._get_value("start_with_day")

    @property
    def always_pm_role(self) -> bool:
        return self._get_value("always_pm_role")

    @property
    def role_reveal(self) -> str:
        return self._get_value("role_reveal")

    @property
    def stats_type(self) -> str:
        return self._get_value("stats_type")

    @property
    def day_time_limit(self) -> int:
        try:
            return self._get_value("day_time_limit")
        except AttributeError:
            return config.Main.get("timers.day.limit")

    @property
    def day_time_warn(self) -> int:
        try:
            return self._get_value("day_time_warn")
        except AttributeError:
            return config.Main.get("timers.day.warn")

    @property
    def short_day_time_limit(self) -> int:
        try:
            return self._get_value("short_day_time_limit")
        except AttributeError:
            return config.Main.get("timers.shortday.limit")

    @property
    def short_day_time_warn(self) -> int:
        try:
            return self._get_value("short_day_time_warn")
        except AttributeError:
            return config.Main.get("timers.shortday.warn")

    @property
    def night_time_limit(self) -> int:
        try:
            return self._get_value("night_time_limit")
        except AttributeError:
            return config.Main.get("timers.night.limit")

    @property
    def night_time_warn(self) -> int:
        try:
            return self._get_value("night_time_warn")
        except AttributeError:
            return config.Main.get("timers.night.warn")

    def get_role_stats(self) -> frozenset[frozenset[tuple[str, int]]]:
        return frozenset(self._rolestats)

    def set_role_stats(self, value) -> None:
        self._rolestats.clear()
        self._rolestats.update(value)
