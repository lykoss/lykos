import re
import random
import itertools
import math
from collections import defaultdict, deque

import botconfig
import src.settings as var
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.messages import messages
from src.events import Event

def _get_targets(var, pl, nick):
    """Gets the mad scientist's targets.

    var - settings module
    pl - list of alive players
    nick - nick of the mad scientist"""
    for index, user in enumerate(var.ALL_PLAYERS):
        if user.nick == nick: # FIXME
            break

    num_players = len(var.ALL_PLAYERS)
    target1 = var.ALL_PLAYERS[index - 1]
    target2 = var.ALL_PLAYERS[(index + 1) % num_players]
    if num_players >= var.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS:
        # determine left player
        i = index
        while True:
            i = (i - 1) % num_players
            if var.ALL_PLAYERS[i].nick in pl or var.ALL_PLAYERS[i].nick == nick:
                target1 = var.ALL_PLAYERS[i]
                break
        # determine right player
        i = index
        while True:
            i = (i + 1) % num_players
            if var.ALL_PLAYERS[i].nick in pl or var.ALL_PLAYERS[i].nick == nick:
                target2 = var.ALL_PLAYERS[i]
                break

    return (target1, target2)


@event_listener("del_player")
def on_del_player(evt, cli, var, nick, mainrole, allroles, death_triggers):
    if not death_triggers or "mad scientist" not in allroles:
        return

    pl = evt.data["pl"]
    target1, target2 = _get_targets(var, pl, nick)

    # apply protections (if applicable)
    prots1 = deque(var.ACTIVE_PROTECTIONS[target1.nick])
    prots2 = deque(var.ACTIVE_PROTECTIONS[target2.nick])
    # for this event, we don't tell the event that the other side is dying
    # this allows, e.g. a bodyguard and the person they are guarding to get splashed,
    # and the bodyguard to still sacrifice themselves to guard the other person
    aevt = Event("assassinate", {"pl": pl, "target": target1},
        del_player=evt.params.del_player,
        deadlist=evt.params.deadlist,
        original=evt.params.original,
        refresh_pl=evt.params.refresh_pl,
        message_prefix="mad_scientist_fail_",
        source="mad scientist",
        killer=nick,
        killer_mainrole=mainrole,
        killer_allroles=allroles,
        prots=prots1)
    while len(prots1) > 0:
        # events may be able to cancel this kill
        if not aevt.dispatch(cli, var, nick, target1.nick, prots1[0]):
            pl = aevt.data["pl"]
            if target1 is not aevt.data["target"]:
                target1 = aevt.data["target"]
                prots1 = deque(var.ACTIVE_PROTECTIONS[target1.nick])
                aevt.params.prots = prots1
                continue
            break
        prots1.popleft()
    aevt.data["target"] = target2
    aevt.params.prots = prots2
    while len(prots2) > 0:
        # events may be able to cancel this kill
        if not aevt.dispatch(cli, var, nick, target2.nick, prots2[0]):
            pl = aevt.data["pl"]
            if target2 is not aevt.data["target"]:
                target2 = aevt.data["target"]
                prots2 = deque(var.ACTIVE_PROTECTIONS[target2.nick])
                aevt.params.prots = prots2
                continue
            break
        prots2.popleft()

    kill1 = target1.nick in pl and len(prots1) == 0
    kill2 = target2.nick in pl and len(prots2) == 0 and target1 is not target2

    if kill1:
        if kill2:
            if var.ROLE_REVEAL in ("on", "team"):
                r1 = get_reveal_role(target1.nick)
                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                r2 = get_reveal_role(target2.nick)
                an2 = "n" if r2.startswith(("a", "e", "i", "o", "u")) else ""
                tmsg = messages["mad_scientist_kill"].format(nick, target1, an1, r1, target2, an2, r2)
            else:
                tmsg = messages["mad_scientist_kill_no_reveal"].format(nick, target1, target2)
            cli.msg(botconfig.CHANNEL, tmsg)
            debuglog(nick, "(mad scientist) KILL: {0} ({1}) - {2} ({3})".format(target1, get_role(target1.nick), target2, get_role(target2.nick)))
            # here we DO want to tell that the other one is dying already so chained deaths don't mess things up
            deadlist1 = evt.params.deadlist[:]
            deadlist1.append(target2)
            deadlist2 = evt.params.deadlist[:]
            deadlist2.append(target1)
            evt.params.del_player(cli, target1.nick, True, end_game=False, killer_role="mad scientist", deadlist=deadlist1, original=evt.params.original, ismain=False)
            evt.params.del_player(cli, target2.nick, True, end_game=False, killer_role="mad scientist", deadlist=deadlist2, original=evt.params.original, ismain=False)
            pl = evt.params.refresh_pl(pl)
        else:
            if var.ROLE_REVEAL in ("on", "team"):
                r1 = get_reveal_role(target1.nick)
                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                tmsg = messages["mad_scientist_kill_single"].format(nick, target1, an1, r1)
            else:
                tmsg = messages["mad_scientist_kill_single_no_reveal"].format(nick, target1)
            cli.msg(botconfig.CHANNEL, tmsg)
            debuglog(nick, "(mad scientist) KILL: {0} ({1})".format(target1, get_role(target1.nick)))
            evt.params.del_player(cli, target1.nick, True, end_game=False, killer_role="mad scientist", deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
            pl = evt.params.refresh_pl(pl)
    else:
        if kill2:
            if var.ROLE_REVEAL in ("on", "team"):
                r2 = get_reveal_role(target2.nick)
                an2 = "n" if r2.startswith(("a", "e", "i", "o", "u")) else ""
                tmsg = messages["mad_scientist_kill_single"].format(nick, target2, an2, r2)
            else:
                tmsg = messages["mad_scientist_kill_single_no_reveal"].format(nick, target2)
            cli.msg(botconfig.CHANNEL, tmsg)
            debuglog(nick, "(mad scientist) KILL: {0} ({1})".format(target2, get_role(target2.nick)))
            evt.params.del_player(cli, target2.nick, True, end_game=False, killer_role="mad scientist", deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
            pl = evt.params.refresh_pl(pl)
        else:
            tmsg = messages["mad_scientist_fail"].format(nick)
            cli.msg(botconfig.CHANNEL, tmsg)
            debuglog(nick, "(mad scientist) KILL FAIL")

    evt.data["pl"] = pl

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    for ms in var.ROLES["mad scientist"]:
        pl = list_players()
        target1, target2 = _get_targets(var, pl, ms)

        if ms in var.PLAYERS and not is_user_simple(ms):
            pm(cli, ms, messages["mad_scientist_notify"].format(target1, target2))
        else:
            pm(cli, ms, messages["mad_scientist_simple"].format(target1, target2))


# vim: set sw=4 expandtab:
