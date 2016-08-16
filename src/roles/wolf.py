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
    # eventually crow will listen on targeted_command and block kills that way
    # (or more likely, that restriction will be lifted and crow can do both)
    if role == "werecrow" and var.OBSERVED.get(nick):
        pm(cli, nick, messages["werecrow_transformed_nokill"])
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
        if victim.lower() == "and":
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
        # need to expand this eventually
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
    if len(var.ROLES["fallen angel"]) == 0:
        for monster in var.ROLES["monster"]:
            if monster in victims:
                evt.data["victims"].remove(monster)
                evt.data["bywolves"].discard(monster)
                evt.data["onlybywolves"].discard(monster)

@event_listener("transition_day", priority=5)
def on_transition_day2(evt, cli, var):
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
        for crow in var.ROLES["werecrow"]:
            if crow in var.OBSERVED:
                wolves.remove(crow)
        evt.data["target"] = random.choice(wolves)

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
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
        # allow len(kills) == 0 through as that means that crow was dumb and observed instead
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
        # should make the cursed information an event that cursedvillager can then add to
        # (e.g. an event to change what prefixes are sent with the role message, and a
        # 2nd event to change information in parens in player list)
        normal_notify = wolf in var.PLAYERS and not is_user_simple(wolf)
        role = get_role(wolf)
        cursed = "cursed " if wolf in var.ROLES["cursed villager"] and role in wcroles else ""

        if normal_notify:
            msg = "{0}_notify".format(role.replace(" ", "_"))
            cmsg = "cursed_" + msg
            try:
                if cursed:
                    try:
                        pm(cli, wolf, messages[cmsg])
                    except KeyError:
                        pm(cli, wolf, messages[msg].format(cursed))
                else:
                    pm(cli, wolf, messages[msg].format(cursed))
            except KeyError:
                # catchall in case we forgot something above
                an = 'n' if role.startswith(("a", "e", "i", "o", "u")) else ""
                pm(cli, wolf, messages["undefined_role_notify"].format(an, role))

            if len(wolves) > 1 and wccond is not None and role in talkroles:
                pm(cli, wolf, messages["wolfchat_notify"].format(wccond))
        else:
            an = "n" if cursed == "" and role.startswith(("a", "e", "i", "o", "u")) else ""
            pm(cli, wolf, messages["wolf_simple"].format(an, cursed, role))  # !simple

        pl = ps[:]
        random.shuffle(pl)
        pl.remove(wolf)  # remove self from list
        if role in wcroles:
            for i, player in enumerate(pl):
                prole = get_role(player)
                if prole in wcroles:
                    cursed = ""
                    if player in var.ROLES["cursed villager"]:
                        cursed = "cursed "
                    pl[i] = "\u0002{0}\u0002 ({1}{2})".format(player, cursed, prole)
                elif player in var.ROLES["cursed villager"]:
                    pl[i] = player + " (cursed)"
        elif role == "warlock":
            for i, player in enumerate(pl):
                if player in var.ROLES["cursed villager"]:
                    pl[i] = player + " (cursed)"

        pm(cli, wolf, "Players: " + ", ".join(pl))
        if role in CAN_KILL and var.DISEASED_WOLVES:
            pm(cli, wolf, messages["ill_wolves"])
        # TODO: split the following out into their own files (mystic, cub and alpha)
        if role == "wolf mystic":
            # if adding this info to !myrole, you will need to save off this count so that they can't get updated info until the next night
            # # of special villagers = # of players - # of villagers - # of wolves - # of neutrals
            numvills = len(ps) - len(list_players(var.WOLFTEAM_ROLES)) - len(list_players(("villager", "vengeful ghost", "time lord", "amnesiac", "lycan"))) - len(list_players(var.TRUE_NEUTRAL_ROLES))
            pm(cli, wolf, messages["wolf_mystic_info"].format("are" if numvills != 1 else "is", numvills, "s" if numvills != 1 else ""))
        if not var.DISEASED_WOLVES and var.ANGRY_WOLVES and role in CAN_KILL:
            pm(cli, wolf, messages["angry_wolves"])
        if var.ALPHA_ENABLED and role == "alpha wolf" and wolf not in var.ALPHA_WOLVES:
            pm(cli, wolf, messages["wolf_bite"])

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()

# vim: set sw=4 expandtab:
