import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

MATCHMAKERS = UserSet() # type: Set[users.User]
LOVERS = UserDict() # type: Dict[users.User, Set[users.User]]

def _set_lovers(target1, target2):
    if target1 in LOVERS:
        LOVERS[target1].add(target2)
    else:
        LOVERS[target1] = UserSet({target2})

    if target2 in LOVERS:
        LOVERS[target2].add(target1)
    else:
        LOVERS[target2] = UserSet({target1})

    t1_msg = "matchmaker_target_notify"
    if target1.prefers_simple():
        t1_msg += "_simple"

    t2_msg = "matchmaker_target_notify"
    if target2.prefers_simple():
        t2_msg += "_simple"

    target1.send(messages[t1_msg].format(target2))
    target2.send(messages[t2_msg].format(target1))

def get_lovers():
    lovers = []
    pl = get_players()
    for lover in LOVERS:
        done = None
        for i, lset in enumerate(lovers):
            if lover in pl and lover in lset:
                if done is not None: # plot twist! two clusters turn out to be linked!
                    done.update(lset)
                    for lvr in LOVERS[lover]:
                        if lvr in pl:
                            done.add(lvr)

                    lset.clear()
                    continue

                for lvr in LOVERS[lover]:
                    if lvr in pl:
                        lset.add(lvr)
                done = lset

        if done is None and lover in pl:
            lovers.append(set())
            lovers[-1].add(lover)
            for lvr in LOVERS[lover]:
                if lvr in pl:
                    lovers[-1].add(lvr)

    while set() in lovers:
        lovers.remove(set())

    return lovers

@command("match", "choose", chan=False, pm=True, playing=True, phases=("night",), roles=("matchmaker",))
def choose(var, wrapper, message):
    """Select two players to fall in love. You may select yourself as one of the lovers."""
    if not var.FIRST_NIGHT:
        return
    if wrapper.source in MATCHMAKERS:
        wrapper.send(messages["already_matched"])
        return

    pieces = re.split(" +", message)
    victim1 = pieces[0]
    if len(pieces) > 1:
        if len(pieces) > 2 and pieces[1].lower() == "and":
            victim2 = pieces[2]
        else:
            victim2 = pieces[1]
    else:
        victim2 = None

    target1 = get_target(var, wrapper, victim1, allow_self=True)
    target2 = get_target(var, wrapper, victim2, allow_self=True)
    if not target1 or not target2:
        return

    if target1 is target2:
        wrapper.send(messages["match_different_people"])
        return

    MATCHMAKERS.add(wrapper.source)

    _set_lovers(target1, target2)

    wrapper.send(messages["matchmaker_success"].format(target1, target2))

    debuglog("{0} (matchmaker) MATCH: {1} ({2}) WITH {3} ({4})".format(wrapper.source, target1, get_main_role(target1), target2, get_main_role(target2)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    pl = get_players()
    for mm in get_all_players(("matchmaker",)):
        if mm not in MATCHMAKERS:
            lovers = random.sample(pl, 2)
            MATCHMAKERS.add(mm)
            _set_lovers(*lovers)
            mm.send(messages["random_matchmaker"])

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        ps = get_players()
        for mm in get_all_players(("matchmaker",)):
            pl = ps[:]
            random.shuffle(pl)
            if mm.prefers_simple():
                mm.send(messages["matchmaker_simple"])
            else:
                mm.send(messages["matchmaker_notify"])
            mm.send("Players: " + ", ".join(p.nick for p in pl))

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    if death_triggers and player in LOVERS:
        lovers = set(LOVERS[player])
        for lover in lovers:
            if lover not in evt.data["pl"]:
                continue # already died somehow
            if var.ROLE_REVEAL in ("on", "team"):
                role = get_reveal_role(lover)
                an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                message = messages["lover_suicide"].format(lover, an, role)
            else:
                message = messages["lover_suicide_no_reveal"].format(lover)
            channels.Main.send(message)
            debuglog("{0} ({1}) LOVE SUICIDE: {2} ({3})".format(lover, get_main_role(lover), player, mainrole))
            evt.params.del_player(lover, end_game=False, killer_role=evt.params.killer_role, deadlist=evt.params.deadlist, original=evt.params.original, ismain=False)
            evt.data["pl"] = evt.params.refresh_pl(evt.data["pl"])

@event_listener("game_end_messages")
def on_game_end_messages(evt, var):
    done = {}
    lovers = []
    for lover1, lset in LOVERS.items():
        for lover2 in lset:
            # check if already said the pairing
            if (lover1 in done and lover2 in done[lover1]) or (lover2 in done and lover1 in done[lover2]):
                continue
            lovers.append("\u0002{0}\u0002/\u0002{1}\u0002".format(lover1, lover2))
            if lover1 in done:
                done[lover1].append(lover2)
            else:
                done[lover1] = [lover2]

    if len(lovers) == 1 or len(lovers) == 2:
        evt.data["messages"].append("The lovers were {0}.".format(" and ".join(lovers)))
    elif len(lovers) > 2:
        evt.data["messages"].append("The lovers were {0}, and {1}".format(", ".join(lovers[0:-1]), lovers[-1]))

@event_listener("player_win")
def on_player_win(evt, var, player, role, winner, survived):
    if player in LOVERS:
        evt.data["special"].append("lover")
    if winner == "lovers" and player in LOVERS:
        evt.data["iwon"] = True

    elif player in LOVERS and survived and LOVERS[player].intersection(get_players()):
        for lvr in LOVERS[player]:
            if lvr not in get_players():
                # cannot win with dead lover (lover idled out)
                continue

            lover_role = get_main_role(lvr)

            if not winner.startswith("@") and singular(winner) not in var.WIN_STEALER_ROLES:
                evt.data["iwon"] = True
                break
            elif winner.startswith("@") and winner == "@" + lvr.nick and var.LOVER_WINS_WITH_FOOL:
                evt.data["iwon"] = True
                break
            elif singular(winner) in var.WIN_STEALER_ROLES and lover_role == singular(winner):
                evt.data["iwon"] = True
                break

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    if var.FIRST_NIGHT:
        evt.data["actedcount"] += len(MATCHMAKERS)
        evt.data["nightroles"].extend(get_all_players(("matchmaker",)))

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_all_players(("matchmaker",)))

@event_listener("get_team_affiliation")
def on_get_team_affiliation(evt, var, target1, target2):
    if target1 in LOVERS and target2 in LOVERS:
        for lset in get_lovers():
            if target1 in lset and target2 in lset:
                evt.data["same"] = True
                break

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind lovers of each other
    if user in get_players() and user in LOVERS:
        msg = [messages["matched_info"]]
        lovers = sorted(LOVERS[user], key=lambda x: x.nick)
        if len(lovers) == 1:
            msg.append(lovers[0].nick)
        elif len(lovers) == 2:
            msg.extend((lovers[0].nick, "and", lovers[1].nick))
        else:
            msg.extend((", ".join([l.nick for l in lovers[:-1]]) + ",", "and", lovers[-1].nick))
        evt.data["messages"].append(" ".join(msg) + ".")

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    # print out lovers
    pl = get_players()
    done = {}
    lovers = []
    for lover1, lset in LOVERS.items():
        if lover1 not in pl:
            continue
        for lover2 in lset:
            # check if already said the pairing
            if (lover1 in done and lover2 in done[lover1]) or (lover2 in done and lover1 in done[lover2]):
                continue
            if lover2 not in pl:
                continue
            lovers.append("{0}/{1}".format(lover1, lover2))
            if lover1 in done:
                done[lover1].append(lover2)
            else:
                done[lover1] = [lover2]
    if len(lovers) == 1 or len(lovers) == 2:
        evt.data["output"].append("\u0002lovers\u0002: {0}".format(" and ".join(lovers)))
    elif len(lovers) > 2:
        evt.data["output"].append("\u0002lovers\u0002: {0}, and {1}".format(", ".join(lovers[0:-1]), lovers[-1]))

@event_listener("reset")
def on_reset(evt, var):
    MATCHMAKERS.clear()
    LOVERS.clear()

# vim: set sw=4 expandtab:
