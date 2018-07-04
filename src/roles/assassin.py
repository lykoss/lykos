import re
import random
import itertools
import math
from collections import defaultdict, deque

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

TARGETED = UserDict() # type: Dict[users.User, users.User]
PREV_ACTED = UserSet()

@command("target", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("assassin",))
def target(var, wrapper, message):
    """Pick a player as your target, killing them if you die."""
    if wrapper.source in PREV_ACTED:
        wrapper.send(messages["assassin_already_targeted"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return
    target = evt.data["target"]

    TARGETED[wrapper.source] = target

    wrapper.send(messages["assassin_target_success"].format(target))

    debuglog("{0} (assassin) TARGET: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["nightroles"].extend(get_all_players(("assassin",)) - PREV_ACTED)
    evt.data["actedcount"] += len(TARGETED) - len(PREV_ACTED)

@event_listener("transition_day", priority=8)
def on_transition_day_resolve(evt, var):
    # Select a random target for assassin that isn't already going to die if they didn't target
    pl = get_players()
    for ass in get_all_players(("assassin",)):
        if ass not in TARGETED and ass.nick not in var.SILENCED:
            ps = pl[:]
            ps.remove(ass)
            for victim in set(evt.data["victims"]):
                if victim in ps:
                    ps.remove(victim)
            if len(ps) > 0:
                target = random.choice(ps)
                TARGETED[ass] = target
                ass.send(messages["assassin_random"].format(target))
    PREV_ACTED.update(TARGETED.keys())

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for ass in get_all_players(("assassin",)):
        if ass in TARGETED:
            continue # someone already targeted

        pl = get_players()
        random.shuffle(pl)
        pl.remove(ass)

        if ass in get_all_players(("village drunk",)): # FIXME: Make into an event when village drunk is split
            TARGETED[ass] = random.choice(pl)
            PREV_ACTED.add(ass)
            message = messages["drunken_assassin_notification"].format(TARGETED[ass])
            if not ass.prefers_simple():
                message += messages["assassin_info"]
            ass.send(message)

        else:
            if ass.prefers_simple():
                ass.send(messages["assassin_simple"])
            else:
                ass.send(messages["assassin_notify"])
            ass.send(messages["players_list"].format(", ".join(p.nick for p in pl)))

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    if player in TARGETED.values():
        for x, y in list(TARGETED.items()):
            if y is player:
                del TARGETED[x]
                PREV_ACTED.discard(x)

    if death_triggers and "assassin" in allroles and player in TARGETED:
        target = TARGETED[player]
        del TARGETED[player]
        PREV_ACTED.discard(player)
        if target in evt.data["pl"]:
            prots = deque(var.ACTIVE_PROTECTIONS[target.nick])
            aevt = Event("assassinate", {"pl": evt.data["pl"], "target": target},
                del_player=evt.params.del_player,
                deadlist=evt.params.deadlist,
                original=evt.params.original,
                refresh_pl=evt.params.refresh_pl,
                message_prefix="assassin_fail_",
                source="assassin",
                killer=player,
                killer_mainrole=mainrole,
                killer_allroles=allroles,
                prots=prots)

            while len(prots) > 0:
                # an event can read the current active protection and cancel the assassination
                # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                # so that it cannot be used again (if the protection is meant to be usable once-only)
                if not aevt.dispatch(var, player, target, prots[0]):
                    pl = aevt.data["pl"]
                    if target is not aevt.data["target"]:
                        target = aevt.data["target"]
                        prots = deque(var.ACTIVE_PROTECTIONS[target.nick])
                        aevt.params.prots = prots
                        continue
                    break
                prots.popleft()

            if not prots:
                if var.ROLE_REVEAL in ("on", "team"):
                    role = get_reveal_role(target)
                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                    message = messages["assassin_success"].format(player, target, an, role)
                else:
                    message = messages["assassin_success_no_reveal"].format(player, target)
                channels.Main.send(message)
                debuglog("{0} (assassin) ASSASSINATE: {1} ({2})".format(player, target, get_main_role(target)))
                evt.params.del_player(target, end_game=False, killer_role=mainrole, deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
                evt.data["pl"] = evt.params.refresh_pl(aevt.data["pl"])

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in get_all_players(("assassin",)):
        msg = ""
        if user in TARGETED:
            msg = messages["assassin_targeting"].format(TARGETED[user])
        user.send(messages["assassin_role_info"].format(msg))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "assassin" and user in TARGETED:
        evt.data["special_case"].append("targeting {0}".format(TARGETED[user]))

@event_listener("reset")
def on_reset(evt, var):
    TARGETED.clear()
    PREV_ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "cats":
        evt.data["assassin"] = {"village"}

# vim: set sw=4 expandtab:
