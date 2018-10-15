import re
import random

from src.utilities import *
from src import users, channels, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_all_roles, get_target, get_main_role, change_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf, All
from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, get_wolfchat_roles, register_killer

register_killer("alpha wolf")

ENABLED = False
ALPHAS = UserSet() # type: UserSet[users.User]
BITTEN = UserDict() # type: UserDict[users.User, users.User]

@command("bite", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("alpha wolf",))
def observe(var, wrapper, message):
    """Turn a player into a wolf!"""
    if not ENABLED:
        wrapper.pm(messages["alpha_no_bite"])
        return
    if wrapper.source in ALPHAS:
        wrapper.pm(messages["alpha_already_bit"])
        return
    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["alpha_no_bite_wolf"])
        return

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, wrapper.source, target)
    if evt.prevent_default:
        return

    target = evt.data["target"]
    BITTEN[wrapper.source] = target
    wrapper.pm(messages["alpha_bite_target"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["alpha_bite_wolfchat"].format(wrapper.source, target), {"alpha wolf"}, role="alpha wolf", command="bite")
    debuglog("{0} (alpha wolf) BITE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("alpha wolf",))
def retract(var, wrapper, message):
    """Retract your bite."""
    if wrapper.source in BITTEN:
        del BITTEN[wrapper.source]
        wrapper.pm(messages["no_bite"])
        send_wolfchat_message(var, wrapper.source, messages["wolfchat_no_bite"].format(wrapper.source), {"alpha wolf"}, role="alpha wolf", command="retract")
        debuglog("{0} (alpha wolf) RETRACT BITE".format(wrapper.source))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    global ENABLED
    if death_triggers and evt.params.main_role in Wolf:
        ENABLED = True

@event_listener("transition_day", priority=5)
def on_transition_day(evt, var):
    global ENABLED
    for alpha, target in BITTEN.items():
        # bite is now separate but some people may try to double up still
        # The implementation of bite is merely lycanthropy + kill, which lets us
        # simplify a lot of the code by offloading it to relevant pieces
        status.add_lycanthropy(var, target, "bitten")
        status.add_lycanthropy_scope(var, All)
        evt.data["killers"][target].append("@wolves")
        evt.data["victims"].append(target)

    # reset ENABLED here instead of begin_day so that night deaths can enable alpha wolf the next night
    ENABLED = False

@event_listener("begin_day")
def on_begin_day(evt, var):
    # Refund failed bites
    for alpha, target in BITTEN.items():
        if alpha in get_players() and target not in get_players(Wolf):
            alpha.send(messages["alpha_bite_failure"].format(target))
        else:
            alpha.send(messages["alpha_bite_success"].format(target))
            ALPHAS.add(alpha)
    BITTEN.clear()

@event_listener("reset")
def on_reset(evt, var):
    global ENABLED
    ENABLED = False
    BITTEN.clear()
    ALPHAS.clear()

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    if not ENABLED:
        return
    can_act = get_all_players(("alpha wolf",)) - ALPHAS
    evt.data["actedcount"] += len(BITTEN)
    evt.data["nightroles"].extend(can_act)

@event_listener("new_role")
def on_new_role(evt, var, player, oldrole):
    if oldrole == "alpha wolf" and evt.data["role"] != "alpha wolf":
        BITTEN.pop(player, None)
        ALPHAS.discard(player)
    elif evt.data["role"] == "alpha wolf" and ENABLED and var.PHASE == "night":
        evt.data["messages"].append(messages["wolf_bite"])

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    if not ENABLED:
        return
    can_bite = get_all_players(("alpha wolf",)) - ALPHAS
    if can_bite:
        for alpha in can_bite:
            alpha.queue_message(messages["wolf_bite"])
        alpha.send_messages()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills" and ENABLED:
        # biting someone has a chance of killing them instead of turning
        # and it can be guarded against, so it's close enough to a kill by that measure
        can_bite = get_all_players(("alpha wolf",)) - ALPHAS
        evt.data["alpha wolf"] = len(can_bite)
    elif kind == "role_categories":
        evt.data["alpha wolf"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal"}

# vim: set sw=4 expandtab:
