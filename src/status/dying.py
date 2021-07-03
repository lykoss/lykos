import time
from collections import Counter
from typing import Tuple

from src.containers import UserDict
from src.functions import get_players, get_main_role, get_all_roles, get_reveal_role
from src.messages import messages
from src.events import Event, event_listener
from src.users import User

__all__ = ["add_dying", "is_dying", "kill_players"]

DyingEntry = Tuple[str, str, bool]

DYING = UserDict() # type: UserDict[User, DyingEntry]

def add_dying(var, player: User, killer_role: str, reason: str, *, death_triggers: bool = True) -> bool:
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
    with var.GRAVEYARD_LOCK: # FIXME
        if not var.GAME_ID or var.GAME_ID > t:
            #  either game ended, or a new game has started
            return False

        if player in DYING or player not in get_players(var):
            return False

        DYING[player] = (killer_role, reason, death_triggers)
        return True

def is_dying(var, player: User) -> bool:
    """
    Determine if the player is marked as dying.

    :param var: The game state
    :param player: Player to check
    :returns: True if the player is marked as dying, False otherwise
    """
    return player in DYING

def kill_players(var, *, end_game: bool = True) -> bool:
    """
    Kill all players marked as dying.

    This function is not re-entrant; do not call it inside of a del_player or kill_players event listener.
    This function does not print anything to the channel; code which calls add_dying should print things as appropriate.

    :param var: The game state
    :param end_game: Whether or not to check for win conditions and perform state transitions (temporary)
    :returns: True if the game is ending (temporary)
    """
    t = time.time()

    with var.GRAVEYARD_LOCK: # FIXME
        if not var.GAME_ID or var.GAME_ID > t:
            #  either game ended, or a new game has started
            return True

        dead = set()

        while DYING:
            player, (killer_role, reason, death_triggers) = DYING.popitem()
            main_role = get_main_role(var, player)
            reveal_role = get_reveal_role(var, player)
            all_roles = get_all_roles(var, player)
            # kill them off
            del var.MAIN_ROLES[player]
            for role in all_roles:
                var.ROLES[role].remove(player)
            dead.add(player)
            # Don't track players that quit before the game started
            if var.PHASE != "join":
                var.DEAD.add(player)
            # notify listeners that the player died for possibility of chained deaths
            evt = Event("del_player", {},
                        killer_role=killer_role,
                        main_role=main_role,
                        reveal_role=reveal_role,
                        reason=reason)
            evt_death_triggers = death_triggers and var.PHASE in var.GAME_PHASES
            evt.dispatch(var, player, all_roles, evt_death_triggers)

        # give roles/modes an opportunity to adjust !stats now that all deaths have resolved
        evt = Event("reconfigure_stats", {"new": []})
        newstats = set()
        for rs in var.ROLE_STATS:
            d = Counter(dict(rs))
            evt.data["new"] = [d]
            evt.dispatch(var, d, "del_player")
            for v in evt.data["new"]:
                if min(v.values()) >= 0:
                    newstats.add(frozenset(v.items()))
        var.ROLE_STATS = newstats

        # notify listeners that all deaths have resolved
        # FIXME: end_game is a temporary hack until we move state transitions into the event loop
        # (priority 10 listener sets prevent_default if end_game=True and game is ending; that's another temporary hack)
        # Once hacks are removed, this function will not have any return value and the end_game kwarg will go away
        evt = Event("kill_players", {}, end_game=end_game)
        return not evt.dispatch(var, dead)

@event_listener("transition_day_resolve_end", priority=1)
def kill_off_dying_players(evt, var, victims):
    for victim in DYING:
        if victim not in evt.data["dead"]:
            evt.data["novictmsg"] = False
            evt.data["dead"].append(victim)

            to_send = "death_no_reveal"
            if var.ROLE_REVEAL in ("on", "team"):
                to_send = "death"
            evt.data["message"][victim].append(messages[to_send].format(victim, get_reveal_role(var, victim)))
