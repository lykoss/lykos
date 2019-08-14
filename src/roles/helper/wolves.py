import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src.functions import get_main_role, get_players, get_all_roles, get_all_players, get_target
from src.decorators import event_listener, command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, is_silent
from src.events import Event
from src.cats import Wolf, Wolfchat, Wolfteam, Killer, Hidden
from src import debuglog, users

KILLS = UserDict() # type: Dict[users.User, List[users.User]]
KNOWS_MINIONS = UserSet() # type: Set[users.User]

def register_killer(rolename):
    @command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=(rolename,))
    def wolf_kill(var, wrapper, message):
        """Kill one or more players as a wolf."""
        pieces = re.split(" +", message)
        targets = []
        orig = []

        nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
        nevt.dispatch(var)
        num_kills = nevt.data["numkills"]

        if not num_kills:
            if nevt.data["message"]:
                wrapper.pm(messages[nevt.data["message"]])
            return

        if len(pieces) < num_kills:
            wrapper.pm(messages["wolf_must_target_multiple"])
            return

        for targ in pieces[:num_kills]:
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
            target = try_misdirection(var, wrapper.source, target)
            if try_exchange(var, wrapper.source, target):
                return

            targets.append(target)

        KILLS[wrapper.source] = UserList(targets)

        if len(orig) > 1:
            # TODO: Expand this so we can support arbitrarily many kills (instead of just one or two)
            wrapper.pm(messages["player_kill_multiple"].format(*orig))
            msg = messages["wolfchat_kill_multiple"].format(wrapper.source, *orig)
            debuglog("{0} ({1}) KILL: {2} ({4}) and {3} ({5})".format(wrapper.source, rolename, *targets, get_main_role(targets[0]), get_main_role(targets[1])))
        else:
            wrapper.pm(messages["player_kill"].format(orig[0]))
            msg = messages["wolfchat_kill"].format(wrapper.source, orig[0])
            debuglog("{0} ({1}) KILL: {2} ({3})".format(wrapper.source, rolename, targets[0], get_main_role(targets[0])))

        send_wolfchat_message(var, wrapper.source, msg, Wolf, role=rolename, command="kill")

    @command("retract", "r", chan=False, pm=True, playing=True, phases=("night",), roles=(rolename,))
    def wolf_retract(var, wrapper, message):
        """Removes a wolf's kill selection."""
        if wrapper.source in KILLS:
            del KILLS[wrapper.source]
            wrapper.pm(messages["retracted_kill"])
            send_wolfchat_message(var, wrapper.source, messages["wolfchat_retracted_kill"].format(wrapper.source), Wolf, role=rolename, command="retract")

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    for killer, targets in list(KILLS.items()):
        for target in targets:
            if player is target:
                targets.remove(target)
        if player is killer or not targets:
            del KILLS[killer]

@event_listener("transition_day", priority=1)
def on_transition_day(evt, var):
    # figure out wolf target
    found = defaultdict(int)
    nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    for v in KILLS.values():
        for p in v:
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
            # special key to let us know to randomly select a wolf in case of retribution totem
            evt.data["killers"][target].append("@wolves")
            del found[target]

def _reorganize_killers(killers):
    wolfteam = get_players(Wolfteam)
    for victim, attackers in list(killers.items()):
        k2 = []
        kappend = []
        wolves = False
        for k in attackers:
            if k in wolfteam:
                kappend.append(k)
            elif k == "@wolves":
                wolves = True
            else:
                k2.append(k)
        k2.extend(kappend)
        if wolves:
            k2.append("@wolves")
        killers[victim] = k2

@event_listener("transition_day", priority=3)
def on_transition_day3(evt, var):
    _reorganize_killers(evt.data["killers"])

@event_listener("transition_day", priority=6)
def on_transition_day6(evt, var):
    _reorganize_killers(evt.data["killers"])

@event_listener("retribution_kill")
def on_retribution_kill(evt, var, victim, orig_target):
    if evt.data["target"] == "@wolves": # kill a random wolf
        evt.data["target"] = random.choice(get_players(Wolf & Killer))

@event_listener("new_role", priority=4)
def on_new_role(evt, var, player, old_role):
    wcroles = get_wolfchat_roles(var)

    if old_role is None:
        # initial role assignment; don't do all the logic below about notifying other wolves and such
        if evt.data["role"] in wcroles:
            evt.data["in_wolfchat"] = True
        return

    sayrole = evt.data["role"]
    if sayrole in Hidden:
        sayrole = var.HIDDEN_ROLE

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
                wofl.queue_message(messages["wolfchat_new_member"].format(player, sayrole))
            wofl.send_messages()
        else:
            return # no other wolves, nothing else to do

        pl = get_players()
        if player in pl:
            pl.remove(player)
        random.shuffle(pl)
        pt = []
        cursed = get_all_players(("cursed villager",))
        for p in pl:
            prole = get_main_role(p) # FIXME: Use proper message keys
            if prole in wcroles:
                pt.append("\u0002{0}\u0002 ({1}{2})".format(p, "cursed, " if p in cursed else "", prole))
            elif p in cursed:
                pt.append("{0} (cursed)".format(p))
            else:
                pt.append(p.nick)

        evt.data["messages"].append(messages["players_list"].format(pt))

        if var.PHASE == "night" and evt.data["role"] in Wolf & Killer:
            # inform the new wolf that they can kill and stuff
            nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
            nevt.dispatch(var)
            if not nevt.data["numkills"] and nevt.data["message"]:
                evt.data["messages"].append(messages[nevt.data["message"]])

@event_listener("chk_nightdone", priority=3)
def on_chk_nightdone(evt, var):
    nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    wofls = [x for x in get_players(Wolf & Killer) if not is_silent(var, x)]
    if not num_kills or not wofls:
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

# TODO: Split this into each role's file
@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    wolves = get_players(Wolfchat)
    # roles in wolfchat (including those that can only listen in but not speak)
    wcroles = get_wolfchat_roles(var)
    # roles allowed to talk in wolfchat
    talkroles = get_talking_roles(var)
    # condition imposed on talking in wolfchat (only during day/night, or no talking)
    # 0 = no talking
    # 1 = normal
    # 2 = only during day
    # 3 = only during night
    wccond = 1

    if var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
        if var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wccond = 0
        else:
            wccond = 2
    elif var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
        wccond = 3

    cursed = get_all_players(("cursed villager",))
    for wolf in wolves:
        normal_notify = not wolf.prefers_simple()
        role = get_main_role(wolf)

        if normal_notify:
            msg = "{0}_notify".format(role.replace(" ", "_"))

            wolf.send(messages[msg])

            if len(wolves) > 1 and role in talkroles:
                wolf.send(messages["wolfchat_notify_{0}".format(wccond)])
        else:
            wolf.send(messages["role_simple"].format(role))  # !simple

        if wolf in cursed:
            wolf.send(messages["cursed_notify"])

        if wolf not in KNOWS_MINIONS:
            minions = len(get_all_players(("minion",)))
            if minions > 0:
                wolf.send(messages["has_minions"].format(minions))
            KNOWS_MINIONS.add(wolf)

        pl = ps[:]
        random.shuffle(pl)
        pl.remove(wolf)  # remove self from list
        players = []
        if role in wcroles:
            cursed = get_all_players(("cursed villager",))
            for player in pl:
                prole = get_main_role(player)
                if prole in wcroles:
                    players.append("\u0002{0}\u0002 ({1}{2})".format(player, "cursed, " if player in cursed else "", prole))
                elif player in cursed:
                    players.append("{0} (cursed)".format(player))
                else:
                    players.append(player.nick)
        elif role == "warlock":
            # warlock specifically only sees cursed if they're not in wolfchat
            for player in pl:
                if player in var.ROLES["cursed villager"]:
                    # FIXME: make i18n friendly (also there's some code duplication between here and warlock.py)
                    players.append(player.nick + " (cursed)")
                else:
                    players.append(player.nick)

        wolf.send(messages["players_list"].format(players))
        nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
        nevt.dispatch(var)
        if role in Wolf & Killer and not nevt.data["numkills"] and nevt.data["message"]:
            wolf.send(messages[nevt.data["message"]])

@event_listener("gun_chances")
def on_gun_chances(evt, var, user, role):
    if user in get_players(get_wolfchat_roles(var)):
        hit, miss, headshot = var.WOLF_GUN_CHANCES
        evt.data["hit"] = hit
        evt.data["miss"] = miss
        evt.data["headshot"] = headshot
        evt.stop_processing = True

@event_listener("gun_shoot")
def on_gun_shoot(evt, var, user, target):
    wolves = get_players(get_wolfchat_roles(var))
    if user in wolves and target in wolves:
        evt.data["hit"] = False

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    KNOWS_MINIONS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
        nevt.dispatch(var)
        evt.data["wolf"] = nevt.data["numkills"]

_kill_cmds = ("kill", "retract")

def wolf_can_kill(var, wolf):
    # a wolf can kill if wolves in general can kill, and the wolf is a Killer
    # this is a utility function meant to be used by other wolf role modules
    nevt = Event("wolf_numkills", {"numkills": 1, "message": ""})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    if num_kills == 0:
        return False
    wolfroles = get_all_roles(wolf)
    return bool(Wolf & Killer & wolfroles)

def get_wolfchat_roles(var):
    wolves = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wolves = Wolf
        else:
            wolves = Wolf | {"traitor"}
    return wolves

def get_talking_roles(var):
    roles = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_WOLVES_ONLY_CHAT:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            roles = Wolf
        else:
            roles = Wolf | {"traitor"}
    return roles

def is_known_wolf_ally(var, actor, target):
    actor_role = get_main_role(actor)
    target_role = get_main_role(target)
    wolves = get_wolfchat_roles(var)
    return actor_role in wolves and target_role in wolves

def send_wolfchat_message(var, user, message, roles, *, role=None, command=None):
    if role not in Wolf & Killer and var.RESTRICT_WOLFCHAT & var.RW_NO_INTERACTION:
        return
    if command not in _kill_cmds and var.RESTRICT_WOLFCHAT & var.RW_ONLY_KILL_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            return
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            return
    if not is_known_wolf_ally(var, user, user):
        return

    wcroles = get_wolfchat_roles(var)
    if var.RESTRICT_WOLFCHAT & var.RW_ONLY_SAME_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            wcroles = roles
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wcroles = roles

    wcwolves = get_players(wcroles)
    wcwolves.remove(user)

    player = None
    for player in wcwolves:
        player.queue_message(message)
    for player in var.SPECTATING_WOLFCHAT:
        player.queue_message("[wolfchat] " + message)
    if player is not None:
        player.send_messages()

# vim: set sw=4 expandtab:
