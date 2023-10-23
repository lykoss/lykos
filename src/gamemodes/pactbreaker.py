from __future__ import annotations

import re
import itertools
from typing import Iterable

from src import users
from src.users import User, FakeUser
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
from src.locations import move_player, get_home, Location, VillageSquare, Graveyard, Forest
from src.roles.helper.wolves import send_wolfchat_message, wolf_kill, wolf_retract
from src.roles.vampire import send_vampire_chat_message, vampire_bite, vampire_retract
from src.roles.vigilante import vigilante_kill, vigilante_retract, vigilante_pass
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
            "chk_nightdone": EventListener(self.on_chk_nightdone),
            "chk_win": EventListener(self.on_chk_win),
            "team_win": EventListener(self.on_team_win),
        }

        self.MESSAGE_OVERRIDES = {
        }

        def dfd():
            return DefaultUserDict(set)

        self.visiting: UserDict[User, Location] = UserDict()
        self.active_players = UserSet()
        self.hobbies: UserDict[User, str] = UserDict()
        # evidence strings: hobby, house, graveyard, forest, hard
        self.collected_evidence: DefaultUserDict[User, DefaultUserDict[User, set]] = DefaultUserDict(dfd)
        kwargs = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.active_players, register=False)
        self.pass_command = command("pass", **kwargs)(self.stay_home)
        self.visit_command = command("visit", **kwargs)(self.visit)

    def startup(self):
        super().startup()
        self.active_players.clear()
        self.hobbies.clear()
        self.collected_evidence.clear()
        self.visiting.clear()
        # register !visit and !pass, remove all role commands
        self.visit_command.register()
        self.pass_command.register()
        wolf_kill.remove()
        wolf_retract.remove()
        vampire_bite.remove()
        vampire_retract.remove()
        vigilante_kill.remove()
        vigilante_retract.remove()
        vigilante_pass.remove()

    def teardown(self):
        super().teardown()
        self.visit_command.remove()
        self.pass_command.remove()
        wolf_kill.register()
        wolf_retract.register()
        vampire_bite.register()
        vampire_retract.register()
        vigilante_kill.register()
        vigilante_retract.register()
        vigilante_pass.register()

    def on_chk_nightdone(self, evt: Event, var: GameState):
        evt.data["acted"].clear()
        evt.data["nightroles"].clear()
        evt.data["acted"].extend(self.visiting)
        evt.data["nightroles"].extend(self.active_players)
        evt.stop_processing = True

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
        self.visiting[wrapper.source] = get_home(wrapper.source.game_state, wrapper.source)
        wrapper.pm(messages["pactbreaker_pass"])

    def visit(self, wrapper: MessageDispatcher, message: str):
        """Visit a location to collect evidence."""
        var = wrapper.game_state
        prefix = re.split(" +", message)[0]
        aliases = {
            "graveyard": messages.raw("_commands", "graveyard"),
            "forest": messages.raw("_commands", "forest"),
            "square": messages.raw("_commands", "square"),
        }

        # We do a user match here, but since we also support locations, we make fake users for them
        # it's rather hacky, but the most elegant implementation since it allows for correct disambiguation messages
        # These fakes all use the bot account to ensure they are selectable even when someone has the same nick
        scope = get_players(var)
        scope.extend(FakeUser(None, als, loc, loc, users.Bot.account) for loc, x in aliases.items() for als in x)
        target_player = get_target(var, prefix, allow_self=True, scope=scope)
        if not target_player:
            return

        if target_player.account == users.Bot.account:
            target_location = Location(target_player.host)
            is_special = True
        else:
            target_location = get_home(var, target_player)
            is_special = False

        self.visiting[wrapper.source] = target_location
        if is_special:
            wrapper.pm(messages["pactbreaker_visiting_special"].format(target_location.name))
        elif target_player is wrapper.source:
            wrapper.pm(messages["pactbreaker_pass"])
        else:
            wrapper.pm(messages["pactbreaker_visiting_house"].format(target_location.name))
