from __future__ import annotations

from typing import Optional

from src.cats import Wolf, Vampire, Category
from src.events import Event, event_listener
from src.functions import get_all_players
from src.gamestate import GameState
from src.messages import messages
from src.status import add_protection
from src.users import User

Monsters = Category("Monsters")

@event_listener("chk_win", priority=4)
def on_chk_win(evt: Event, var: GameState, rolemap: dict[str, set[User]], mainroles: dict[User, str], lpl: int, lwolves: int, lrealwolves: int, lvampires: int):
    monsters = rolemap.get("monster", ())
    lm = len(monsters)

    if not monsters:
        return

    if not lrealwolves:
        evt.data["message"] = messages["monster_win"].format(lm)
        evt.data["winner"] = Monsters
    elif lwolves >= lpl / 2 and not lvampires:
        evt.data["message"] = messages["monster_wolf_win"].format(lm)
        evt.data["winner"] = Monsters
    elif lvampires >= lpl / 2 and not lwolves:
        evt.data["message"] = messages["monster_vampire_win"].format(lm)
        evt.data["winner"] = Monsters

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for monster in get_all_players(var, ("monster",)):
        add_protection(var, monster, protector=None, protector_role="monster", scope=Wolf | Vampire, priority=10)
        monster.send(messages["monster_notify"])

@event_listener("remove_protection")
def on_remove_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if attacker_role == "fallen angel" and protector_role == "monster":
        evt.data["remove"] = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["monster"] = {"Neutral", "Win Stealer", "Cursed", "Monsters"}
