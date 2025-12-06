import re
from typing import Optional

from src import gamestate
from src.containers import UserSet
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import event_listener, Event
from src.users import User


class GameState(gamestate.GameState):
    def __init__(self):
        self.witch_killed = UserSet()
        self.witch_passed = UserSet()
        self.witch_saved = UserSet()

@command("kill", chan=False, pm=True, playing=True, phases=("witch",), roles=("witch",))
def kill(wrapper: MessageDispatcher, message: str):
    pass

@command("guard", chan=False, pm=True, playing=True, phases=("witch",), roles=("witch",))
def guard(wrapper: MessageDispatcher, message: str):
    pass

@command("pass", chan=False, pm=True, playing=True, phases=("witch",), roles=("witch",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    pass

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    pass

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    pass

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    pass

@event_listener("player_protected")
def on_player_protected(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    pass

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    var.witch_passed.clear()

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    # set up next phase. right now the event doesn't work too well for multiple things setting next phase
    # need to come up with better design for that
    pass

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["witch"] = {"Village", "Safe", "Killer", "Nocturnal"}
