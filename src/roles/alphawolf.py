import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_all_roles, get_target, get_main_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf
from src.roles._wolf_helper import is_known_wolf_ally, send_wolfchat_message, get_wolfchat_roles

ENABLED = False
ALPHAS = UserSet() # type: UserSet[users.User]
BITTEN = UserDict() # type: UserDict[users.User, users.User]

@command("bite", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("alpha wolf",))
def observe(var, wrapper, message):
    """Turn a player into a wolf!"""
    if not ENABLED:
        wrapper.pm(messages["alpha_no_bite"])
        return
    if wrapper.source in ALPHAS and wrapper.source not in BITTEN:
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
    ALPHAS.add(wrapper.source)
    wrapper.pm(messages["alpha_bite_target"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["alpha_bite_wolfchat"].format(wrapper.source, target), {"alpha wolf"}, role="alpha wolf", command="bite")
    debuglog("{0} (alpha wolf) BITE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=("alpha wolf",))
def retract(var, wrapper, message):
    """Retract your bite."""
    if wrapper.source in BITTEN:
        del BITTEN[wrapper.source]
        ALPHAS.remove(wrapper.source)
        wrapper.pm(messages["no_bite"])
        send_wolfchat_message(var, wrapper.source, messages["wolfchat_no_bite"].format(wrapper.source), {"alpha wolf"}, role="alpha wolf", command="retract")
        debuglog("{0} (alpha wolf) RETRACT BITE".format(wrapper.source))

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    global ENABLED
    if death_triggers and mainrole in Wolf:
        ENABLED = True

@event_listener("transition_day", priority=5)
def on_transition_day(evt, var):
    if not ENABLED:
        return

    for alpha, target in list(BITTEN.items()):
        # bite is now separate but some people may try to double up still, if bitten person is
        # also being killed by wolves, make the kill not apply
        # note that we cannot bite visiting harlots unless they are visiting a wolf,
        # and lycans/immunized people turn/die instead of being bitten, so keep the kills valid on those
        bite_evt = Event("bite", {
            "can_bite": True,
            "kill": target in get_all_players(("lycan",)) or target.nick in var.LYCANTHROPES or target.nick in var.IMMUNIZED
            },
            victims=victims,
            killers=killers,
            bywolves=bywolves,
            onlybywolves=onlybywolves,
            protected=protected,
            numkills=numkills)
        bite_evt.dispatch(var, alpha, target)
        if bite_evt.data["kill"]:
            # target immunized or a lycan, kill them instead and refund the bite
            ALPHAS.remove(alpha)
            del BITTEN[alpha]
            if var.ACTIVE_PROTECTIONS[target.nick]:
                # target was protected
                evt.data["protected"][target] = var.ACTIVE_PROTECTIONS[target.nick].pop(0)
            elif target in evt.data["protected"]:
                del evt.data["protected"][target]
            # add them as a kill even if protected so that protection message plays
            if target not in evt.data["victims"]:
                evt.data["onlybywolves"].add(target)
            evt.data["killers"][target].append(alpha)
            evt.data["victims"].append(target)
            evt.data["bywolves"].add(target)
        elif not bite_evt.data["can_bite"]:
            # bite failed due to some other reason (namely harlot)
            ALPHAS.remove(alpha)
            del BITTEN[alpha]

        to_send = "alpha_bite_failure"
        if alpha in ALPHAS:
            to_send = "alpha_bite_success"
        alpha.send(messages[to_send].format(target))

@event_listener("transition_day_resolve_end", priority=2)
def on_transition_day_resolve_end(evt, var, victims):
    global ENABLED
    # FIXME: split into lycan (moved here because it needs to be priority 2)
    for victim in victims:
        if (victim in var.ROLES["lycan"] or victim.nick in var.LYCANTHROPES) and victim in evt.data["onlybywolves"] and victim.nick not in var.IMMUNIZED:
            vrole = get_main_role(victim)
            if vrole not in Wolf:
                change_role(var, victim, vrole, "wolf", message="lycan_turn")
                var.ROLES["lycan"].discard(victim) # in the event lycan was a template, we want to ensure it gets purged
                evt.data["howl"] += 1
                evt.data["novictmsg"] = False

    # turn all bitten people into wolves
    for target in list(BITTEN.values()):
        if target in evt.data["bywolves"]:
            evt.data["victims"].remove(target)
            evt.data["bywolves"].discard(target)
            evt.data["onlybywolves"].discard(target)
            evt.data["killers"][target].remove("@wolves")

        if target in evt.data["victims"]:
            # bite was unsuccessful due to someone else killing them
            ALPHAS.remove(alpha)
            del BITTEN[alpha]
            continue

        # short-circuit if they are already a wolf or are dying
        targetrole = get_main_role(target)
        if target in evt.data["dead"] or targetrole in Wolf:
            continue

        # get rid of extraneous messages (i.e. harlot visiting wolf)
        evt.data["message"].pop(target, None)

        newrole = "wolf"
        to_send = "bitten_turn"
        # FIXME: move this into a config maybe so that other things that cause people to turn wolfteam
        # can make use of it?
        # account for shamans
        sham_evt = Event("default_totems", {"shaman_roles": set()})
        sham_evt.dispatch(var, {})
        if targetrole == "guardian angel":
            to_send = "fallen_angel_turn"
            # fallen angels also automatically gain the assassin template if they don't already have it
            newrole = "fallen angel"
            var.ROLES["assassin"].add(target)
            debuglog("{0} (guardian angel) TURNED FALLEN ANGEL".format(target))
        elif targetrole in ("seer", "oracle", "augur"):
            to_send = "seer_turn"
            newrole = "doomsayer"
            debuglog("{0} ({1}) TURNED DOOMSAYER".format(target, targetrole))
        elif targetrole in sham_evt.data["shaman_roles"]:
            to_send = "shaman_turn"
            newrole = "wolf shaman"
            debuglog("{0} ({1}) TURNED WOLF SHAMAN".format(target, targetrole))
        elif targetrole == "harlot":
            to_send = "harlot_turn"
            debuglog("{0} (harlot) TURNED WOLF".format(target))
        else:
            debuglog("{0} ({1}) TURNED WOLF".format(target, targetrole))
        change_role(var, target, targetrole, newrole, message=to_send)
        evt.data["howl"] += 1
        evt.data["novictmsg"] = False

    # reset ENABLED here instead of begin_day so that night deaths can enable alpha wolf the next night
    ENABLED = False

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, var, roleset, reason):
    # only reconfigure in response to a chilling howl message
    if reason != "howl":
        return

    # FIXME: split into lycan
    if roleset.get("lycan", 0) > 0:
        if roleset in evt.data["new"]:
            evt.data["new"].remove(roleset)
        newset = dict(roleset)
        newset["lycan"] -= 1
        newset["wolf"] = newset.get("wolf", 0) + 1
        evt.data["new"].append(newset)

    # ensure that in the case of multiple howls in one night, that we don't adjust stats
    # more times than there are alpha wolves; make use of a private dict key in this case
    # as the data dict is preserved across multiple disparate howl events
    if "alphawolf-counter" not in evt.data:
        evt.data["alphawolf-counter"] = 0

    # "or not BITTEN" is technically revealing info that alpha wolf did successfully bite
    # as opposed to some other role that did it, but given how messy it makes !stats this is
    # probably fine? Can revisit in the future and try a better way to figure out whether
    # or not it was possible that an alpha wolf was able to bite or not
    # (test case 1: in a game with 2 lycans + alpha, if alpha is enabled every night, we still
    # only run the below logic once as opposed to 3 times)
    # (test case 2: in a game with lycan + alpha, if lycan turns and alpha bites the same night,
    # we still only run the below logic once as opposed to twice)
    if not ENABLED or not BITTEN or evt.data["alphawolf-counter"] == len(BITTEN):
        return

    sham_evt = Event("default_totems", {"shaman_roles": set()})
    sham_evt.dispatch(var, {})
    evt.data["alphawolf-counter"] += 1
    evt.data["new"].discard(roleset)
    wolfchat = get_wolfchat_roles(var)
    for role in roleset:
        if role in wolfchat or roleset[role] == 0:
            continue
        newset = dict(roleset)
        newset[role] -= 1
        if role == "guardian angel":
            newset["fallen angel"] = newset.get("fallen angel", 0) + 1
        elif role in ("seer", "augur", "oracle"):
            newset["doomsayer"] = newset.get("doomsayer", 0) + 1
        elif role in sham_evt.data["shaman_roles"]:
            newset["wolf shaman"] = newset.get("wolf shaman", 0) + 1
        else:
            newset["wolf"] = newset.get("wolf", 0) + 1
        evt.data["new"].add(newset)

@event_listener("begin_day")
def on_begin_day(evt, var):
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
