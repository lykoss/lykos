from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from src.events import Event, event_listener
from src.functions import get_all_players
from src.messages import messages
from src.status import add_lycanthropy, add_lycanthropy_scope, remove_lycanthropy

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.users import User

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    lycans = get_all_players(var, ("lycan",))
    if lycans:
        add_lycanthropy_scope(var, {"lycan"})
    for lycan in lycans:
        if not add_lycanthropy(var, lycan):
            continue
        lycan.send(messages["lycan_notify"])

@event_listener("doctor_immunize")
def on_doctor_immunize(evt: Event, var: GameState, doctor: User, target: User):
    if target in get_all_players(var, ("lycan",)):
        evt.data["message"] = "lycan_cured"

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "lycan" and evt.data["role"] != "lycan":
        remove_lycanthropy(var, player) # FIXME: We might be a lycanthrope from more than just the lycan role

# TODO: We want to remove lycan from someone who was just turned into a wolf if it was a template
# There's no easy way to do this right now and it doesn't really matter, so it's fine for now

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["lycan"] = {"Village", "Team Switcher"}
