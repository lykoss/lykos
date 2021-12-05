from __future__ import annotations

import time
from collections import Counter
from typing import Optional, Tuple

from src.containers import UserDict, UserSet
from src.functions import get_main_role, get_all_roles, get_reveal_role
from src.messages import messages
from src.gamestate import GameState, PregameState
from src.events import Event, event_listener
from src.users import User
from src import locks, channels

__all__ = ["add_dying", "is_dying", "is_dead", "kill_players", "DEAD"]

DyingEntry = Tuple[str, str, bool]

DYING: UserDict[User, DyingEntry] = UserDict()
DEAD: UserSet = UserSet()

def add_dying(var: GameState, player: User, killer_role: str, reason: str, *, death_triggers: bool = True) -> bool:
    """
    Mark a player as dying.

    :param var: The game state
    :param player: The player to kill off
    :param killer_role: The role which is responsible for killing player; must be an actual role
    :param reason: The reason the player is being killed off, for stats tracking purposes
    :param death_triggers: Whether or not to run role logic that triggers on death; players who die due to quitting or idling out have this set to False
    :returns: True if the player was successfully marked as dying, or False if they are already dying or dead
    """
    t = time.time()

    # ensure that the reaper thread doesn't smash things against the gameplay thread when running this
    # (eventually the reaper thread will just pass messages to the main thread via the asyncio event loop and these locks would therefore be unnecessary)
    with locks.reaper: # FIXME
        if not var or var.game_id > t:
            #  either game ended, or a new game has started
            return False

        if player in DYING or player in DEAD:
            return False

        DYING[player] = (killer_role, reason, death_triggers)
        return True

def is_dying(var: GameState, player: User) -> bool:
    """
    Determine if the player is marked as dying.

    :param var: The game state
    :param player: Player to check
    :returns: True if the player is marked as dying, False otherwise
    """
    return player in DYING

def is_dead(var: GameState, player: User) -> bool:
    """
    Determine if the player is dead.

    :param var: The game state
    :param player: Player to check
    :returns: True if the player is dead, False otherwise (including if the player is not playing)
    """
    return player in DEAD

def kill_players(var: Optional[GameState | PregameState], *, end_game: bool = True) -> bool:
    """
    Kill all players marked as dying.

    This function is not re-entrant; do not call it inside of a del_player or kill_players event listener.
    This function does not print anything to the channel; code which calls add_dying should print things as appropriate.

    :param var: The game state
    :param end_game: Whether or not to check for win conditions and perform state transitions (temporary)
    :returns: True if the game is ending (temporary)
    """
    t = time.time()

    with locks.reaper: # FIXME
        if not var or var.game_id > t:
            #  either game ended, or a new game has started
            return True

        dead: set[User] = set()

        while DYING:
            player, (killer_role, reason, death_triggers) = DYING.popitem()
            if var.in_game:
                main_role = get_main_role(var, player)
                reveal_role = get_reveal_role(var, player)
                all_roles = get_all_roles(var, player)
            else:
                main_role = "player"
                reveal_role = "player"
                all_roles = ["player"]

            if var.in_game:
                # kill them off
                del var.main_roles[player]
                for role in all_roles:
                    var.roles[role].remove(player)
                dead.add(player)
                DEAD.add(player)
            else:
                # left during join phase
                var.players.remove(player)
                channels.Main.mode(("-v", player.nick))

            # notify listeners that the player died for possibility of chained deaths
            evt = Event("del_player", {},
                        killer_role=killer_role,
                        main_role=main_role,
                        reveal_role=reveal_role,
                        reason=reason)
            evt_death_triggers = death_triggers and var.in_game
            evt.dispatch(var, player, all_roles, evt_death_triggers)

        if not var.in_game:
            return False

        # give roles/modes an opportunity to adjust !stats now that all deaths have resolved
        evt = Event("reconfigure_stats", {"new": []})
        newstats = set()
        for rs in var.get_role_stats():
            d = Counter(dict(rs))
            evt.data["new"] = [d]
            evt.dispatch(var, d, "del_player")
            for v in evt.data["new"]:
                if min(v.values()) >= 0:
                    newstats.add(frozenset(v.items()))
        var.set_role_stats(newstats)

        # notify listeners that all deaths have resolved
        # FIXME: end_game is a temporary hack until we move state transitions into the event loop
        # (priority 10 listener sets prevent_default if end_game=True and game is ending; that's another temporary hack)
        # Once hacks are removed, this function will not have any return value and the end_game kwarg will go away
        evt = Event("kill_players", {}, end_game=end_game)
        return not evt.dispatch(var, dead)

@event_listener("transition_day_resolve_end", priority=1)
def kill_off_dying_players(evt: Event, var: GameState, victims: list[User]):
    for victim in DYING:
        if victim not in evt.data["dead"]:
            evt.data["novictmsg"] = False
            evt.data["dead"].append(victim)

            to_send = "death_no_reveal"
            if var.role_reveal in ("on", "team"):
                to_send = "death"
            evt.data["message"][victim].append(messages[to_send].format(victim, get_reveal_role(var, victim)))

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    DEAD.clear()
    DYING.clear()
