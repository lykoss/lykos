import re
import random
from collections import defaultdict

import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

KILLS = {} # type: Dict[str, List[str]]
# wolves able to use the !kill command, roles should add to this in their own files via
# from src.roles import wolf
# wolf.CAN_KILL.add("wolf sphere") # or whatever the new wolf role is
# simply modifying var.WOLF_ROLES will *not* update this!
CAN_KILL = set(var.WOLF_ROLES - {"wolf cub"}) # type: Set[str]

@cmd("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=CAN_KILL)
def wolf_kill(cli, nick, chan, rest):
    """Kills one or more players as a wolf."""
    role = get_role(nick)
    # eventually cub will listen on targeted_command and block kills that way
    if var.DISEASED_WOLVES:
        pm(cli, nick, messages["ill_wolves"])
        return

    pieces = re.split(" +", rest)
    victims = []
    orig = []
    num_kills = 1
    if var.ANGRY_WOLVES:
        num_kills = 2

    i = 0
    extra = 0
    while i < num_kills + extra:
        try:
            victim = pieces[i]
        except IndexError:
            break
        if i > 0 and victim.lower() == "and" and i+1 < len(pieces):
            extra += 1
            i += 1
            victim = pieces[i]
        victim = get_victim(cli, nick, victim, False)
        if not victim:
            return
        
        if victim == nick:
            pm(cli, nick, messages["no_suicide"])
            return
        if in_wolflist(nick, victim):
            pm(cli, nick, messages["wolf_no_target_wolf"])
            return
        orig.append(victim)
        evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True})
        evt.dispatch(cli, var, "kill", nick, victim, frozenset({"detrimental"}))
        if evt.prevent_default:
            return
        victim = evt.data["target"]
        victims.append(victim)
        i += 1

    if len(set(victims)) < len(victims):
        pm(cli, nick, messages["wolf_must_target_multiple"])
        return
    KILLS[nick] = victims
    if len(orig) > 1:
        # need to expand this eventually (only accomodates 2 kills, whereas we should ideally support arbitrarily many)
        msg = messages["wolf_target_multiple"].format(orig[0], orig[1])
        pm(cli, nick, messages["player"].format(msg))
        debuglog("{0} ({1}) KILL: {2} ({3}) and {4} ({5})".format(nick, role, victims[0], get_role(victims[0]), victims[1], get_role(victims[1])))
    else:
        msg = messages["wolf_target"].format(orig[0])
        pm(cli, nick, messages["player"].format(msg))
        if num_kills > 1:
            pm(cli, nick, messages["wolf_target_second"])
        debuglog("{0} ({1}) KILL: {2} ({3})".format(nick, role, victims[0], get_role(victims[0])))

    if in_wolflist(nick, nick):
        relay_wolfchat_command(cli, nick, messages["wolfchat"].format(nick, msg), var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)

    chk_nightdone(cli)

@cmd("retract", "r", chan=False, pm=True, playing=True, phases=("night",))
def wolf_retract(cli, nick, chan, rest):
    """Removes a wolf's kill selection."""
    if nick in KILLS:
        del KILLS[nick]
        pm(cli, nick, messages["retracted_kill"])
        relay_wolfchat_command(cli, nick, messages["wolfchat_retracted_kill"].format(nick), var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)
    if get_role(nick) == "alpha wolf" and nick in var.BITE_PREFERENCES:
        del var.BITE_PREFERENCES[nick]
        var.ALPHA_WOLVES.remove(nick)
        pm(cli, nick, messages["no_bite"])
        relay_wolfchat_command(cli, nick, messages["wolfchat_no_bite"].format(nick), ("alpha wolf",), is_wolf_command=True)

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    if death_triggers:
        # TODO: split into cub
        if nickrole == "wolf cub":
            var.ANGRY_WOLVES = True
        # TODO: split into alpha
        if nickrole in var.WOLF_ROLES:
            var.ALPHA_ENABLED = True

    for a,b in list(KILLS.items()):
        for n in b:
            if n == nick:
                KILLS[a].remove(nick)
        if a == nick or len(KILLS[a]) == 0:
            del KILLS[a]

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    kvp = []
    for a,b in KILLS.items():
        nl = []
        for n in b:
            if n == prefix:
                n = nick
            nl.append(n)
        if a == prefix:
            a = nick
        kvp.append((a,nl))
    KILLS.update(kvp)
    if prefix in KILLS:
        del KILLS[prefix]

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in KILLS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(list_players(CAN_KILL))

@event_listener("transition_day", priority=1)
def on_transition_day(evt, cli, var):
    # figure out wolf target
    found = defaultdict(int)
    # split off into event + wolfcub.py
    num_kills = 1
    if var.ANGRY_WOLVES:
        num_kills = 2
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
            victim = random.choice(dups)
            evt.data["victims"].append(victim)
            evt.data["bywolves"].add(victim)
            evt.data["onlybywolves"].add(victim)
            # special key to let us know to randomly select a wolf in case of retribution totem
            evt.data["killers"][victim].append("@wolves")
            del found[victim]

    # this should be moved to an event in kill, where monster prefixes their nick with !
    # and fallen angel subsequently removes the ! prefix
    # TODO: when monster is split off
    if len(var.ROLES["fallen angel"]) == 0:
        for monster in var.ROLES["monster"]:
            if monster in evt.data["victims"]:
                evt.data["victims"].remove(monster)
                evt.data["bywolves"].discard(monster)
                evt.data["onlybywolves"].discard(monster)

@event_listener("transition_day", priority=3)
def on_transition_day3(evt, cli, var):
    evt.data["numkills"] = {v: evt.data["victims"].count(v) for v in set(evt.data["victims"])}
    on_transition_day6(evt, cli, var)

@event_listener("transition_day", priority=6)
def on_transition_day6(evt, cli, var):
    wolfteam = list_players(var.WOLFTEAM_ROLES)
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
def on_retribution_kill(evt, cli, var, victim, orig_target):
    t = evt.data["target"]
    if t == "@wolves":
        wolves = list_players(var.WOLF_ROLES)
        evt.data["target"] = random.choice(wolves)

@event_listener("exchange_roles", priority=2)
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    wcroles = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wcroles = var.WOLF_ROLES
        else:
            wcroles = var.WOLF_ROLES | {"traitor"}

    if nick_role in wcroles and actor_role not in wcroles:
        pl = list_players()
        random.shuffle(pl)
        pl.remove(actor)  # remove self from list
        notify = []
        for i, player in enumerate(pl):
            prole = get_role(player)
            if player == nick:
                prole = actor_role
            wevt = Event("wolflist", {"tags": set()})
            wevt.dispatch(cli, var, player, actor)
            tags = " ".join(wevt.data["tags"])
            if prole in wcroles:
                if tags:
                    tags += " "
                pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, tags, prole)
                notify.append(player)
            elif tags:
                pl[i] = "{0} ({1})".format(player, tags)

        mass_privmsg(cli, notify, messages["players_exchanged_roles"].format(nick, actor))
        evt.data["actor_messages"].append("Players: " + ", ".join(pl))
        if nick_role in CAN_KILL and var.DISEASED_WOLVES:
            evt.data["actor_messages"].append(messages["ill_wolves"])
        if not var.DISEASED_WOLVES and var.ANGRY_WOLVES and nick_role in CAN_KILL:
            evt.data["actor_messages"].append(messages["angry_wolves"])
        if var.ALPHA_ENABLED and nick_role == "alpha wolf" and actor not in var.ALPHA_WOLVES:
            evt.data["actor_messages"].append(messages["wolf_bite"])
    elif actor_role in wcroles and nick_role not in wcroles:
        pl = list_players()
        random.shuffle(pl)
        pl.remove(nick)  # remove self from list
        notify = []
        for i, player in enumerate(pl):
            prole = get_role(player)
            if player == actor:
                prole = nick_role
            wevt = Event("wolflist", {"tags": set()})
            wevt.dispatch(cli, var, player, nick)
            tags = " ".join(wevt.data["tags"])
            if prole in wcroles:
                if tags:
                    tags += " "
                pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, tags, prole)
                notify.append(player)
            elif tags:
                pl[i] = "{0} ({1})".format(player, tags)

        mass_privmsg(cli, notify, messages["players_exchanged_roles"].format(actor, nick))
        evt.data["nick_messages"].append("Players: " + ", ".join(pl))
        if actor_role in CAN_KILL and var.DISEASED_WOLVES:
            evt.data["nick_messages"].append(messages["ill_wolves"])
        if not var.DISEASED_WOLVES and var.ANGRY_WOLVES and actor_role in CAN_KILL:
            evt.data["nick_messages"].append(messages["angry_wolves"])
        if var.ALPHA_ENABLED and actor_role == "alpha wolf" and nick not in var.ALPHA_WOLVES:
            evt.data["nick_messages"].append(messages["wolf_bite"])

    if actor in KILLS:
        del KILLS[actor]
    if nick in KILLS:
        del KILLS[nick]

@event_listener("chk_nightdone", priority=3)
def on_chk_nightdone(evt, cli, var):
    if not var.DISEASED_WOLVES:
        evt.data["actedcount"] += len(KILLS)
        # eventually wolf cub will remove itself from nightroles in wolfcub.py
        evt.data["nightroles"].extend(list_players(CAN_KILL))

@event_listener("chk_nightdone", priority=20)
def on_chk_nightdone2(evt, cli, var):
    if not evt.prevent_default and not var.DISEASED_WOLVES:
        # flatten KILLS
        kills = set()
        for ls in KILLS.values():
            kills.update(ls)
        # check if wolves are actually agreeing
        if not var.ANGRY_WOLVES and len(kills) > 1:
            evt.data["actedcount"] -= 1
        elif var.ANGRY_WOLVES and (len(kills) == 1 or len(kills) > 2):
            evt.data["actedcount"] -= 1

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    ps = list_players()
    wolves = list_players(var.WOLFCHAT_ROLES)
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
        normal_notify = wolf in var.PLAYERS and not is_user_simple(wolf)
        role = get_role(wolf)
        wevt = Event("wolflist", {"tags": set()})
        tags = ""
        if role in wcroles:
            wevt.dispatch(cli, var, wolf, wolf)
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
                    pm(cli, wolf, messages[cmsg].format(tags2))
                except KeyError:
                    pm(cli, wolf, messages[msg].format(tags))
            else:
                pm(cli, wolf, messages[msg].format(tags))

            if len(wolves) > 1 and wccond is not None and role in talkroles:
                pm(cli, wolf, messages["wolfchat_notify"].format(wccond))
        else:
            an = ""
            if tags:
                if tags.startswith(("a", "e", "i", "o", "u")):
                    an = "n"
            elif role.startswith(("a", "e", "i", "o", "u")):
                an = "n"
            pm(cli, wolf, messages["wolf_simple"].format(an, tags, role))  # !simple

        pl = ps[:]
        random.shuffle(pl)
        pl.remove(wolf)  # remove self from list
        if role in wcroles:
            for i, player in enumerate(pl):
                prole = get_role(player)
                wevt.data["tags"] = set()
                wevt.dispatch(cli, var, player, wolf)
                tags = " ".join(wevt.data["tags"])
                if prole in wcroles:
                    if tags:
                        tags += " "
                    pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, tags, prole)
                elif tags:
                    pl[i] = "{0} ({1})".format(player, tags)
        elif role == "warlock":
            # warlock specifically only sees cursed if they're not in wolfchat
            for i, player in enumerate(pl):
                if player in var.ROLES["cursed villager"]:
                    pl[i] = player + " (cursed)"

        pm(cli, wolf, "Players: " + ", ".join(pl))
        if role in CAN_KILL and var.DISEASED_WOLVES:
            pm(cli, wolf, messages["ill_wolves"])
        # TODO: split the following out into their own files (cub and alpha)
        if not var.DISEASED_WOLVES and var.ANGRY_WOLVES and role in CAN_KILL:
            pm(cli, wolf, messages["angry_wolves"])
        if var.ALPHA_ENABLED and role == "alpha wolf" and wolf not in var.ALPHA_WOLVES:
            pm(cli, wolf, messages["wolf_bite"])

@event_listener("chk_win", priority=1)
def on_chk_win(evt, cli, var, rolemap, lpl, lwolves, lrealwolves):
    # TODO: split into cub
    did_something = False
    if lrealwolves == 0:
        for wc in list(rolemap["wolf cub"]):
            rolemap["wolf"].add(wc)
            rolemap["wolf cub"].remove(wc)
            did_something = True
            if var.PHASE in var.GAME_PHASES:
                # don't set cub's FINAL_ROLE to wolf, since we want them listed in endgame
                # stats as cub still.
                pm(cli, wc, messages["cub_grow_up"])
                debuglog(wc, "(wolf cub) GROW UP")
    if did_something:
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("reconfigure_stats")
def on_reconfigure_stats(evt, cli, var, stats):
    # TODO: split into cub
    if "wolf cub" not in stats or stats["wolf cub"] == 0:
        return
    for role in var.WOLF_ROLES - {"wolf cub"}:
        if role in stats and stats[role] > 0:
            break
    else:
        stats["wolf"] = stats["wolf cub"]
        stats["wolf cub"] = 0

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    if var.ROLES["succubus"].intersection(KILLS.get(victim, ())):
        for s in var.ROLES["succubus"]:
            if s in KILLS[victim]:
                pm(cli, victim, messages["no_kill_succubus"].format(nick))
                KILLS[victim].remove(s)
        if not KILLS[victim]:
            del KILLS[victim]

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, cli, var, kind):
    if kind == "night_kills":
        if var.DISEASED_WOLVES:
            evt.data["wolf"] = 0
        elif var.ANGRY_WOLVES:
            evt.data["wolf"] = 2
        else:
            evt.data["wolf"] = 1
        # TODO: split into alpha
        if var.ALPHA_ENABLED:
            # alpha wolf gives an extra kill; note that we consider someone being
            # bitten a "kill" for this metadata kind as well
            # rolled into wolf instead of as a separate alpha wolf key for ease of implementing
            # special logic for wolf kills vs non-wolf kills (as when alpha kills it is treated
            # as any other wolf kill).
            evt.data["wolf"] += 1

# vim: set sw=4 expandtab:
