from __future__ import annotations

import re
import itertools
from typing import Iterable

from src import users
from src.users import User
from src.containers import UserSet, UserDict, DefaultUserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event
from src.events import EventListener
from src.match import match_all
from src.functions import get_players, get_main_role, get_target, change_role
from src.gamemodes import game_mode, GameMode
from src.gamestate import GameState
from src.messages import messages
from src.locations import move_player, get_home, VillageSquare, Graveyard, Forest
from src.roles.helper.wolves import send_wolfchat_message
from src.roles.vampire import send_vampire_chat_message
from src.status import add_dying

@game_mode("pactbreaker", minp=6, maxp=24, likelihood=0)
class PactBreakerMode(GameMode):
    """Help a rogue vigilante take down the terrors of the night or re-establish your pact with the werewolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.CUSTOM_SETTINGS.limit_abstain = False
        self.CUSTOM_SETTINGS.self_lynch_allowed = False
        self.ROLE_GUIDE = {
            6: ["wolf", "vampire", "vigilante"],
            8: ["wolf(2)"],
            10: ["vampire(2)"],
            12: ["vigilante(2)"],
            14: ["wolf(3)"],
            16: ["vampire(3)"],
            18: ["wolf(4)"],
            20: ["vigilante(3)"],
            24: ["wolf(5)", "vampire(4)"],
        }
        self.EVENTS = {
            "wolf_numkills": EventListener(self.on_wolf_numkills),
            "chk_win": EventListener(self.on_chk_win),
            "team_win": EventListener(self.on_team_win),
        }

        self.MESSAGE_OVERRIDES = {
        }

        def dfd():
            return DefaultUserDict(set)

        self.active_players = UserSet()
        self.hobbies: UserDict[User, str] = UserDict()
        # evidence strings: hobby, house, graveyard, forest, hard
        self.collected_evidence: DefaultUserDict[User, DefaultUserDict[User, set]] = DefaultUserDict(dfd)
        kwargs = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.active_players, register=False)
        self.pass_command = command("pass", **kwargs)(self.stay_home)
        self.visit_command = command("visit", **kwargs)(self.visit)

    def startup(self):
        super().startup()
        self.visit_command.register()

    def teardown(self):
        super().teardown()
        self.visit_command.remove()

    def on_wolf_numkills(self, evt: Event, var: GameState, wolf):
        evt.data["numkills"] = 0

    def on_chk_win(self, evt: Event, var: GameState, rolemap, mainroles, lpl, lwolves, lrealwolves, lvampires):
        num_vigilantes = len(get_players(var, ("vigilante",), mainroles=mainroles))

        if evt.data["winner"] == "villagers":
            evt.data["message"] = messages["pactbreaker_vigilante_win"]
        elif evt.data["winner"] in ("wolves", "vampires"):
            # This isn't a win unless all vigilantes are dead
            if num_vigilantes == 0:
                evt.data["winner"] = None
            else:
                # All vigilantes are dead, so this is an actual win
                # Message keys used: pactbreaker_wolves_win pactbreaker_vampires_win
                evt.data["message"] = messages["pactbreaker_{0}_win".format(evt.data["winner"])]
        elif num_vigilantes == 0 and lvampires == 0:
            # wolves (and villagers) win even if there is a minority of wolves as long as
            # the vigilantes and vampires are all dead
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["pactbreaker_wolves_win"]

    def on_team_win(self, evt: Event, var: GameState, player: User, main_role: str, all_roles: Iterable[str], winner: str):
        if winner == "wolves" and main_role == "villager":
            evt.data["team_win"] = True

    def stay_home(self, wrapper: MessageDispatcher, message: str):
        """Stay at home tonight."""
        pass

    def visit(self, wrapper: MessageDispatcher, message: str):
        """Visit a location to collect evidence."""
        var = wrapper.game_state
        prefix = re.split(" +", message)[0]
        graveyard_aliases = messages.raw("_commands", "graveyard")
        forest_aliases = messages.raw("_commands", "forest")
        square_aliases = messages.raw("_commands", "square")
        match_only = None
        if ":" in prefix:
            m = users.complete_match(prefix.split(":", maxsplit=1)[1])
            if m and m.get() is users.Bot:
                match_only = "locations"
            else:
                match_only = "users"

        if match_only == "users":
            player = get_target(wrapper, prefix, allow_self=True)
            if not player:
                return
            target = get_home(var, player)
        elif match_only == "locations":
            m = match_all(prefix, itertools.chain(graveyard_aliases, forest_aliases, square_aliases))
            if m:
                if m.get() in graveyard_aliases:
                    target = Graveyard
                elif m.get() in forest_aliases:
                    target = Forest
                else:
                    target = VillageSquare
            else:
                # ambiguous or no matches; give user suggestions if ambiguous
                return
