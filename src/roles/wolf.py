import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src.functions import get_players, get_all_players, get_main_role, get_all_roles, get_target
from src import debuglog, errlog, plog, users, channels
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

from src.roles._wolf_helper import CAN_KILL, is_known_wolf_ally, send_wolfchat_message

KILLS = UserDict() # type: Dict[users.User, List[users.User]]
# wolves able to use the !kill command, roles should add to this in their own files via
# from src.roles import wolf
# wolf.CAN_KILL.add("wolf sphere") # or whatever the new wolf role is
# simply modifying var.WOLF_ROLES will *not* update this!
# TODO: Move this into something else
CAN_KILL.update(var.WOLF_ROLES)

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=CAN_KILL)
def wolf_kill(var, wrapper, message):
    """Kills one or more players as a wolf."""
    role = get_main_role(wrapper.source)
    # eventually cub will listen on targeted_command and block kills that way
    if var.DISEASED_WOLVES:
        wrapper.pm(messages["ill_wolves"])
        return

    pieces = re.split(" +", message)
    targets = []
    orig = []

    nevt = Event("wolf_numkills", {"numkills": 1})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]

    if len(pieces) < num_kills:
        wrapper.pm(messages["wolf_must_target_multiple"])
        return

    for targ in pieces:
        target = get_target(var, wrapper, targ, not_self_message="no_suicide")
        if target is None:
            return

        if is_known_wolf_ally(var, wrapper.source, target):
            wrapper.pm(messages["wolf_no_target_wolf"])
            return

        if target in orig:
            wrapper.pm(messages["wolf_must_target_multiple"])
            return

        orig.append(target)

        evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
        if not evt.dispatch(var, wrapper.source, target):
            return

        target = evt.data["target"]
        targets.append(target)

    KILLS[wrapper.source] = UserList(targets)

    if len(orig) > 1:
        # TODO: Expand this so we can support arbitrarily many kills (instead of just one or two)
        wrapper.pm(messages["player_kill_multiple"].format(*orig))
        msg = messages["wolfchat_kill_multiple"].format(wrapper.source, *orig)
        debuglog("{0} ({1}) KILL: {2} ({4}) and {3} ({5})".format(wrapper.source, role, *targets, get_main_role(targets[0]), get_main_role(targets[1])))
    else:
        wrapper.pm(messages["player_kill"].format(orig[0]))
        msg = messages["wolfchat_kill"].format(wrapper.source, orig[0])
        debuglog("{0} ({1}) KILL: {2} ({3})".format(wrapper.source, role, targets[0], get_main_role(targets[0])))

    send_wolfchat_message(var, wrapper.source, msg, var.WOLF_ROLES, role=role, command="kill")

@command("retract", "r", chan=False, pm=True, playing=True, phases=("night",))
def wolf_retract(var, wrapper, message):
    """Removes a wolf's kill selection."""
    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])
        send_wolfchat_message(var, wrapper.source, messages["wolfchat_retracted_kill"].format(wrapper.source), var.WOLF_ROLES, role=get_main_role(wrapper.source), command="retract")

    if wrapper.source in var.ROLES["alpha wolf"] and wrapper.source.nick in var.BITE_PREFERENCES: # FIXME: Split into alpha wolf and convert to users
        del var.BITE_PREFERENCES[wrapper.source.nick]
        var.ALPHA_WOLVES.remove(wrapper.source.nick)
        wrapper.pm(messages["no_bite"])
        send_wolfchat_message(var, wrapper.source, messages["wolfchat_no_bite"].format(wrapper.source), ("alpha wolf",), role="alpha wolf", command="retract")

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if death_triggers:
        # TODO: split into alpha
        if allroles & var.WOLF_ROLES:
            var.ALPHA_ENABLED = True

    for killer, targets in list(KILLS.items()):
        for target in targets:
            if user is target:
                targets.remove(target)
        if user is killer or not targets:
            del KILLS[killer]

@event_listener("night_acted")
def on_acted(evt, var, user, actor):
    if user in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["wolves"].update(get_players(var.WOLFTEAM_ROLES))

@event_listener("transition_day", priority=1)
def on_transition_day(evt, var):
    # figure out wolf target
    found = defaultdict(int)
    nevt = Event("wolf_numkills", {"numkills": 1})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    for v in KILLS.values():
        for p in v:
            if p:
                # kill target starting with ! is invalid
                # right now nothing does this, but monster eventually will
                if p[0] == "!":
                    continue
                found[p] += 1
    for i in range(num_kills):
        maxc = 0
        dups = []
        for v, c in found.items():
            if c > maxc:
                maxc = c
                dups = [v]
            elif c == maxc:
                dups.append(v)
        if maxc and dups:
            target = random.choice(dups)
            evt.data["victims"].append(target)
            evt.data["bywolves"].add(target)
            evt.data["onlybywolves"].add(target)
            # special key to let us know to randomly select a wolf in case of retribution totem
            evt.data["killers"][target].append("@wolves")
            del found[target]

    # this should be moved to an event in kill, where monster prefixes their nick with !
    # and fallen angel subsequently removes the ! prefix
    # TODO: when monster is split off
    if var.ROLES["fallen angel"]:
        for monster in get_all_players(("monster",)):
            if monster in evt.data["victims"]:
                evt.data["victims"].remove(monster)
                evt.data["bywolves"].discard(monster)
                evt.data["onlybywolves"].discard(monster)

@event_listener("transition_day", priority=3)
def on_transition_day3(evt, var):
    evt.data["numkills"] = {v: evt.data["victims"].count(v) for v in set(evt.data["victims"])}
    on_transition_day6(evt, var)

@event_listener("transition_day", priority=6)
def on_transition_day6(evt, var):
    wolfteam = get_players(var.WOLFTEAM_ROLES)
    for victim, killers in list(evt.data["killers"].items()):
        k2 = []
        kappend = []
        wolves = False
        for k in killers:
            if k in wolfteam:
                kappend.append(k)
            elif k == "@wolves":
                wolves = True
            else:
                k2.append(k)
        k2.extend(kappend)
        if wolves:
            k2.append("@wolves")
        evt.data["killers"][victim] = k2

@event_listener("retribution_kill")
def on_retribution_kill(evt, var, victim, orig_target):
    if evt.data["target"] == "@wolves":
        wolves = get_players(CAN_KILL)
        evt.data["target"] = random.choice(wolves)

@event_listener("new_role", priority=4)
def on_new_role(evt, var, player, old_role):
    wcroles = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wcroles = var.WOLF_ROLES
        else:
            wcroles = var.WOLF_ROLES | {"traitor"}

    if old_role is None:
        # initial role assignment; don't do all the logic below about notifying other wolves and such
        if evt.data["role"] in wcroles:
            evt.data["in_wolfchat"] = True
        return

    sayrole = evt.data["role"]
    if sayrole in var.HIDDEN_VILLAGERS:
        sayrole = "villager"
    elif sayrole in var.HIDDEN_ROLES:
        sayrole = var.DEFAULT_ROLE
    an = "n" if sayrole.startswith(("a", "e", "i", "o", "u")) else ""

    if player in KILLS:
        del KILLS[player]

    if old_role not in wcroles and evt.data["role"] in wcroles:
        # a new wofl has joined the party, give them tummy rubs and the wolf list
        # and let the other wolves know to break out the confetti and villager steaks
        wofls = get_players(wcroles)
        evt.data["in_wolfchat"] = True
        if wofls:
            new_wolves = []
            for wofl in wofls:
                wofl.queue_message(messages["wolfchat_new_member"].format(player, an, sayrole))
            wofl.send_messages()

        pl = get_players()
        pl.remove(player)
        random.shuffle(pl)
        pt = []
        wevt = Event("wolflist", {"tags": set()})
        for p in pl:
            prole = get_main_role(p)
            wevt.data["tags"].clear()
            wevt.dispatch(var, p, player)
            tags = " ".join(wevt.data["tags"])
            if prole in wcroles:
                if tags:
                    tags += " "
                pt.append("\u0002{0}\u0002 ({1}{2})".format(p, tags, prole))
            elif tags:
                pt.append("{0} ({1})".format(p, tags))
            else:
                pt.append(p.nick)

        evt.data["messages"].append(messages["players_list"].format(", ".join(pt)))

        if var.PHASE == "night":
            # inform the new wolf that they can kill and stuff
            if evt.data["role"] in CAN_KILL and var.DISEASED_WOLVES:
                evt.data["messages"].append(messages["ill_wolves"])
            # FIXME: split when alpha wolf is split
            if var.ALPHA_ENABLED and evt.data["role"] == "alpha wolf" and player.nick not in var.ALPHA_WOLVES:
                evt.data["messages"].append(messages["wolf_bite"])

@event_listener("chk_nightdone", priority=3)
def on_chk_nightdone(evt, var):
    nevt = Event("wolf_numkills", {"numkills": 1})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    wofls = [x for x in get_players(CAN_KILL) if x.nick not in var.SILENCED]
    if var.DISEASED_WOLVES or num_kills == 0 or len(wofls) == 0:
        return

    evt.data["nightroles"].extend(wofls)
    evt.data["actedcount"] += len(KILLS)
    evt.data["nightroles"].append(users.FakeUser.from_nick("@WolvesAgree@"))
    # check if wolves are actually agreeing or not;
    # only add to count if they actually agree
    # (this is *slighty* less hacky than deducting 1 from actedcount as we did previously)
    kills = set()
    for ls in KILLS.values():
        kills.update(ls)
    # check if wolves are actually agreeing
    if len(kills) == num_kills:
        evt.data["actedcount"] += 1

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    wolves = get_players(var.WOLFCHAT_ROLES)
    # roles in wolfchat (including those that can only listen in but not speak)
    wcroles = var.WOLFCHAT_ROLES
    # roles allowed to talk in wolfchat
    talkroles = var.WOLFCHAT_ROLES
    # condition imposed on talking in wolfchat (only during day/night, or None if talking is disabled)
    wccond = ""

    if var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
        if var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wccond = None
        else:
            wccond = " during day"
    elif var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
        wccond = " during night"

    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wcroles = var.WOLF_ROLES
            talkroles = var.WOLF_ROLES
        else:
            wcroles = var.WOLF_ROLES | {"traitor"}
            talkroles = var.WOLF_ROLES | {"traitor"}
    elif var.RESTRICT_WOLFCHAT & var.RW_WOLVES_ONLY_CHAT:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            talkroles = var.WOLF_ROLES
        else:
            talkroles = var.WOLF_ROLES | {"traitor"}

    for wolf in wolves:
        normal_notify = not wolf.prefers_simple()
        role = get_main_role(wolf)
        wevt = Event("wolflist", {"tags": set()})
        tags = ""
        if role in wcroles:
            wevt.dispatch(var, wolf, wolf)
            tags = " ".join(wevt.data["tags"])
            if tags:
                tags += " "

        if normal_notify:
            msg = "{0}_notify".format(role.replace(" ", "_"))
            cmsg = "cursed_" + msg
            if "cursed" in wevt.data["tags"]:
                try:
                    tags2 = " ".join(wevt.data["tags"] - {"cursed"})
                    if tags2:
                        tags2 += " "
                    wolf.send(messages[cmsg].format(tags2))
                except KeyError:
                    wolf.send(messages[msg].format(tags))
            else:
                wolf.send(messages[msg].format(tags))

            if len(wolves) > 1 and wccond is not None and role in talkroles:
                wolf.send(messages["wolfchat_notify"].format(wccond))
        else:
            an = ""
            if tags:
                if tags.startswith(("a", "e", "i", "o", "u")):
                    an = "n"
            elif role.startswith(("a", "e", "i", "o", "u")):
                an = "n"
            wolf.send(messages["wolf_simple"].format(an, tags, role))  # !simple


        if var.FIRST_NIGHT:
            minions = len(get_all_players(("minion",)))
            if minions > 0:
                wolf.send(messages["has_minions"].format(minions, plural("minion", minions)))

        pl = ps[:]
        random.shuffle(pl)
        pl.remove(wolf)  # remove self from list
        players = []
        if role in wcroles:
            for player in pl:
                prole = get_main_role(player)
                wevt.data["tags"] = set()
                wevt.dispatch(var, player, wolf)
                tags = " ".join(wevt.data["tags"])
                if prole in wcroles:
                    if tags:
                        tags += " "
                    players.append("\u0002{0}\u0002 ({1}{2})".format(player, tags, prole))
                elif tags:
                    players.append("{0} ({1})".format(player, tags))
                else:
                    players.append(player.nick)
        elif role == "warlock":
            # warlock specifically only sees cursed if they're not in wolfchat
            for player in pl:
                if player in var.ROLES["cursed villager"]:
                    players.append(player.nick + " (cursed)")
                else:
                    players.append(player.nick)

        wolf.send(messages["players_list"].format(", ".join(players)))
        if role in CAN_KILL and var.DISEASED_WOLVES:
            wolf.send(messages["ill_wolves"])
        # TODO: split the following out into their own files (alpha)
        if var.ALPHA_ENABLED and role == "alpha wolf" and wolf.nick not in var.ALPHA_WOLVES: # FIXME: Fix once var.ALPHA_WOLVES holds User instances
            wolf.send(messages["wolf_bite"])

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        nevt = Event("wolf_numkills", {"numkills": 1})
        nevt.dispatch(var)
        evt.data["wolf"] = nevt.data["numkills"]
        # TODO: split into alpha
        if var.ALPHA_ENABLED:
            # alpha wolf gives an extra kill; note that we consider someone being
            # bitten a "kill" for this metadata kind as well
            # rolled into wolf instead of as a separate alpha wolf key for ease of implementing
            # special logic for wolf kills vs non-wolf kills (as when alpha kills it is treated
            # as any other wolf kill).
            evt.data["wolf"] += 1

@event_listener("wolf_numkills", priority=10)
def on_wolf_numkills(evt, var):
    if var.DISEASED_WOLVES:
        evt.data["numkills"] = 0
        evt.stop_processing = True

# vim: set sw=4 expandtab:
