import random
import re

import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

WILD_CHILDREN = set()
IDOLS = {}

@cmd("choose", chan=False, pm=True, playing=True, phases=("night",), roles=("wild child",))
def choose_idol(cli, nick, chan, rest):
    """Pick your idol, if they die, you'll become a wolf!"""
    if not var.FIRST_NIGHT:
        return
    if nick in IDOLS:
        pm(cli, nick, messages["wild_child_already_picked"])
        return

    victim = get_victim(cli, nick, re.split(" +", rest)[0], False)
    if not victim:
        return

    if nick == victim:
        pm(cli, nick, messages["no_target_self"])
        return

    IDOLS[nick] = victim
    pm(cli, nick, messages["wild_child_success"].format(victim))

    debuglog("{0} ({1}) IDOLIZE: {2} ({3})".format(nick, get_role(nick), victim, get_role(victim)))
    chk_nightdone(cli)

@event_listener("see")
def on_see(evt, cli, var, seer, victim):
    if get_role(seer) != "augur" and victim in WILD_CHILDREN:
        evt.data["role"] = "wild child"

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in WILD_CHILDREN:
        WILD_CHILDREN.remove(prefix)
        WILD_CHILDREN.add(nick)

    for (wildchild, idol) in IDOLS.items():
        if wildchild == prefix:
            IDOLS[nick] = IDOLS[wildchild]
            del IDOLS[wildchild]
        elif idol == prefix:
            IDOLS[wildchild] = nick

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    if actor_role == "wolf" and actor in WILD_CHILDREN and nick not in WILD_CHILDREN:
        WILD_CHILDREN.discard(actor)
        WILD_CHILDREN.add(nick)
    elif actor_role == "wild child":
        if nick_role == "wild child":
            temp = IDOLS[nick]
            IDOLS[nick] = IDOLS[actor]
            IDOLS[actor] = temp
            evt.data["actor_messages"].append(messages["wild_child_idol"].format(IDOLS[actor]))
            evt.data["nick_messages"].append(messages["wild_child_idol"].format(IDOLS[nick]))
        else:
            IDOLS[nick] = IDOLS.pop(actor)
            evt.data["nick_messages"].append(messages["wild_child_idol"].format(IDOLS[nick]))
    if nick_role == "wolf" and nick in WILD_CHILDREN and actor not in WILD_CHILDREN:
        WILD_CHILDREN.discard(nick)
        WILD_CHILDREN.add(actor)
    elif nick_role == "wild child" and actor_role != "wild child":
        # if they're both wild children, already swapped idols above
        IDOLS[actor] = IDOLS.pop(nick)
        evt.data["actor_messages"].append(messages["wild_child_idol"].format(IDOLS[actor]))

@event_listener("myrole")
def on_myrole(evt, cli, var, nick):
    if evt.data["role"] == "wild child" and nick in IDOLS:
        evt.data["messages"].append(messages["wild_child_idol"].format(IDOLS[nick]))

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    if var.PHASE not in var.GAME_PHASES:
        return

    for child in var.ROLES["wild child"].copy():
        if child not in IDOLS or child in evt.params.deadlist or IDOLS[child] not in evt.params.deadlist:
            continue

        pm(cli, child, messages["idol_died"])
        WILD_CHILDREN.add(child)
        var.ROLES["wild child"].remove(child)
        var.ROLES["wolf"].add(child)
        var.FINAL_ROLES[child] = "wolf"

        wcroles = var.WOLFCHAT_ROLES
        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}
        wolves = list_players(wcroles)
        wolves.remove(child)
        mass_privmsg(cli, wolves, messages["wild_child_as_wolf"].format(child))
        if var.PHASE == "day":
            random.shuffle(wolves)
            for i, wolf in enumerate(wolves):
                wolfroles = get_role(wolf)
                cursed = ""
                if wolf in var.ROLES["cursed villager"]:
                    cursed = "cursed "
                wolves[i] = "\u0002{0}\u0002 ({1}{2})".format(wolf, cursed, wolfroles)

            if wolves:
                pm(cli, child, "Wolves: " + ", ".join(wolves))
            else:
                pm(cli, child, messages["no_other_wolves"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    if var.FIRST_NIGHT:
        evt.data["actedcount"] += len(IDOLS.keys())
        evt.data["nightroles"].extend(var.ROLES["wild child"])

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, cli, var):
    if (not var.START_WITH_DAY or not var.FIRST_DAY) and var.FIRST_NIGHT:
        for child in var.ROLES["wild child"]:
            if child not in IDOLS:
                pl = list_players()
                pl.remove(child)
                if pl:
                    target = random.choice(pl)
                    IDOLS[child] = target
                    pm(cli, child, messages["wild_child_random_idol"].format(target))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    for child in var.ROLES["wild child"]:
        if child in var.PLAYERS and not is_user_simple(child):
            pm(cli, child, messages["child_notify"])
        else:
            pm(cli, child, messages["child_simple"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, wrapper, nick, role):
    if role == "wild child":
        if nick in IDOLS:
            evt.data["special_case"].append("picked {0} as idol".format(IDOLS[nick]))
        else:
            evt.data["special_case"].append("no idol picked yet")

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, nick):
    if nick in WILD_CHILDREN:
        evt.data["role"] = "wild child"

@event_listener("reset")
def on_reset(evt, var):
    WILD_CHILDREN.clear()
    IDOLS.clear()

# vim: set sw=4 expandtab:
