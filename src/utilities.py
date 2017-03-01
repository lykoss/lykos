import itertools
import fnmatch
import re

import botconfig
import src.settings as var
from src import proxy, debuglog
from src.events import Event
from src.messages import messages

__all__ = ["pm", "is_fake_nick", "mass_mode", "mass_privmsg", "reply",
           "is_user_simple", "is_user_notice", "in_wolflist",
           "relay_wolfchat_command", "chk_nightdone", "chk_decision",
           "chk_win", "irc_lower", "irc_equals", "is_role", "match_hostmask",
           "is_owner", "is_admin", "plural", "singular", "list_players",
           "list_players_and_roles", "list_participants", "get_role", "get_roles",
           "get_reveal_role", "get_templates", "role_order", "break_long_message",
           "complete_match","complete_one_match", "get_victim", "get_nick", "InvalidModeException"]
# message either privmsg or notice, depending on user settings
def pm(cli, target, message):
    if is_fake_nick(target) and botconfig.DEBUG_MODE:
        debuglog("Would message fake nick {0}: {1!r}".format(target, message))
        return

    if is_user_notice(target):
        cli.notice(target, message)
        return

    cli.msg(target, message)

is_fake_nick = re.compile(r"^[0-9]+$").search

def mass_mode(cli, md_param, md_plain):
    """ Example: mass_mode(cli, [('+v', 'asdf'), ('-v','wobosd')], ['-m']) """
    lmd = len(md_param)  # store how many mode changes to do
    if md_param:
        for start_i in range(0, lmd, var.MODELIMIT):  # 4 mode-changes at a time
            if start_i + var.MODELIMIT > lmd:  # If this is a remainder (mode-changes < 4)
                z = list(zip(*md_param[start_i:]))  # zip this remainder
                ei = lmd % var.MODELIMIT  # len(z)
            else:
                z = list(zip(*md_param[start_i:start_i+var.MODELIMIT])) # zip four
                ei = var.MODELIMIT # len(z)
            # Now z equal something like [('+v', '-v'), ('asdf', 'wobosd')]
            arg1 = "".join(md_plain) + "".join(z[0])
            arg2 = " ".join(z[1])  # + " " + " ".join([x+"!*@*" for x in z[1]])
            cli.mode(botconfig.CHANNEL, arg1, arg2)
    elif md_plain:
            cli.mode(botconfig.CHANNEL, "".join(md_plain))

def mass_privmsg(cli, targets, msg, notice=False, privmsg=False):
    if not targets:
        return
    if not notice and not privmsg:
        msg_targs = []
        not_targs = []
        for target in targets:
            if is_fake_nick(target):
                debuglog("Would message fake nick {0}: {1!r}".format(target, msg))
            elif is_user_notice(target):
                not_targs.append(target)
            else:
                msg_targs.append(target)
        while msg_targs:
            if len(msg_targs) <= var.MAX_PRIVMSG_TARGETS:
                bgs = ",".join(msg_targs)
                msg_targs = None
            else:
                bgs = ",".join(msg_targs[:var.MAX_PRIVMSG_TARGETS])
                msg_targs = msg_targs[var.MAX_PRIVMSG_TARGETS:]
            cli.msg(bgs, msg)
        while not_targs:
            if len(not_targs) <= var.MAX_PRIVMSG_TARGETS:
                bgs = ",".join(not_targs)
                not_targs = None
            else:
                bgs = ",".join(not_targs[:var.MAX_PRIVMSG_TARGETS])
                not_targs = not_targs[var.MAX_PRIVMSG_TARGETS:]
            cli.notice(bgs, msg)
    else:
        while targets:
            if len(targets) <= var.MAX_PRIVMSG_TARGETS:
                bgs = ",".join(targets)
                targets = None
            else:
                bgs = ",".join(targets[:var.MAX_PRIVMSG_TARGETS])
                target = targets[var.MAX_PRIVMSG_TARGETS:]
            if notice:
                cli.notice(bgs, msg)
            else:
                cli.msg(bgs, msg)

# Decide how to reply to a user, depending on the channel / query it was called in, and whether a game is running and they are playing
def reply(cli, nick, chan, msg, private=False, prefix_nick=False):
    if chan == nick:
        pm(cli, nick, msg)
    elif private or (chan == botconfig.CHANNEL and
            ((nick not in list_players() and var.PHASE in var.GAME_PHASES) or
             (var.DEVOICE_DURING_NIGHT and var.PHASE == "night"))):
        cli.notice(nick, msg)
    else:
        if prefix_nick:
            cli.msg(chan, "{0}: {1}".format(nick, msg))
        else:
            cli.msg(chan, msg)

def is_user_simple(nick):
    if nick in var.USERS:
        ident = irc_lower(var.USERS[nick]["ident"])
        host = var.USERS[nick]["host"].lower()
        acc = irc_lower(var.USERS[nick]["account"])
    else:
        return False
    if acc and acc != "*" and not var.DISABLE_ACCOUNTS:
        if acc in var.SIMPLE_NOTIFY_ACCS:
            return True
        return False
    elif not var.ACCOUNTS_ONLY:
        for hostmask in var.SIMPLE_NOTIFY:
            if match_hostmask(hostmask, nick, ident, host):
                return True
    return False

def is_user_notice(nick):
    if nick in var.USERS and var.USERS[nick]["account"] and var.USERS[nick]["account"] != "*" and not var.DISABLE_ACCOUNTS:
        if irc_lower(var.USERS[nick]["account"]) in var.PREFER_NOTICE_ACCS:
            return True
    if nick in var.USERS and not var.ACCOUNTS_ONLY:
        ident = irc_lower(var.USERS[nick]["ident"])
        host = var.USERS[nick]["host"].lower()
        for hostmask in var.PREFER_NOTICE:
            if match_hostmask(hostmask, nick, ident, host):
                return True
    return False

def in_wolflist(nick, who):
    myrole = get_role(nick)
    role = get_role(who)
    wolves = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wolves = var.WOLF_ROLES
        else:
            wolves = var.WOLF_ROLES | {"traitor"}
    return myrole in wolves and role in wolves

def relay_wolfchat_command(cli, nick, message, roles, is_wolf_command=False, is_kill_command=False):
    if not is_wolf_command and var.RESTRICT_WOLFCHAT & var.RW_NO_INTERACTION:
        return
    if not is_kill_command and var.RESTRICT_WOLFCHAT & var.RW_ONLY_KILL_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            return
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            return
    if not in_wolflist(nick, nick):
        return

    wcroles = var.WOLFCHAT_ROLES
    if var.RESTRICT_WOLFCHAT & var.RW_ONLY_SAME_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            wcroles = roles
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wcroles = roles
    elif var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wcroles = var.WOLF_ROLES
        else:
            wcroles = var.WOLF_ROLES | {"traitor"}

    wcwolves = list_players(wcroles)
    wcwolves.remove(nick)
    mass_privmsg(cli, wcwolves, message)
    mass_privmsg(cli, var.SPECTATING_WOLFCHAT, "[wolfchat] " + message)

@proxy.stub
def chk_nightdone(cli):
    pass

@proxy.stub
def chk_decision(cli, force=""):
    pass

@proxy.stub
def chk_win(cli, end_game=True, winner=None):
    pass

def irc_lower(nick):
    if nick is None:
        return None

    mapping = {
        "[": "{",
        "]": "}",
        "\\": "|",
        "^": "~",
    }

    # var.CASEMAPPING may not be defined yet in some circumstances (like database upgrades)
    # if so, default to rfc1459
    if hasattr(var, "CASEMAPPING"):
        if var.CASEMAPPING == "strict-rfc1459":
            mapping.pop("^")
        elif var.CASEMAPPING == "ascii":
            mapping = {}

    return nick.lower().translate(str.maketrans(mapping))

def irc_equals(nick1, nick2):
    return irc_lower(nick1) == irc_lower(nick2)

is_role = lambda plyr, rol: rol in var.ROLES and plyr in var.ROLES[rol]

def match_hostmask(hostmask, nick, ident, host):
    # support n!u@h, u@h, or just h by itself
    matches = re.match('(?:(?:(.*?)!)?(.*?)@)?(.*)', hostmask)

    if ((not matches.group(1) or fnmatch.fnmatch(irc_lower(nick), irc_lower(matches.group(1)))) and
            (not matches.group(2) or fnmatch.fnmatch(irc_lower(ident), irc_lower(matches.group(2)))) and
            fnmatch.fnmatch(host.lower(), matches.group(3).lower())):
        return True

    return False

def is_owner(nick, ident=None, host=None, acc=None):
    hosts = set(botconfig.OWNERS)
    accounts = set(botconfig.OWNERS_ACCOUNTS)
    if nick in var.USERS:
        if not ident:
            ident = var.USERS[nick]["ident"]
        if not host:
            host = var.USERS[nick]["host"]
        if not acc:
            acc = var.USERS[nick]["account"]

    if not var.DISABLE_ACCOUNTS and acc and acc != "*":
        for pattern in accounts:
            if fnmatch.fnmatch(irc_lower(acc), irc_lower(pattern)):
                return True

    if host:
        for hostmask in hosts:
            if match_hostmask(hostmask, nick, ident, host):
                return True

    return False

def is_admin(nick, ident=None, host=None, acc=None):
    if nick in var.USERS:
        if not ident:
            ident = var.USERS[nick]["ident"]
        if not host:
            host = var.USERS[nick]["host"]
        if not acc:
            acc = var.USERS[nick]["account"]
    acc = irc_lower(acc)
    hostmask = irc_lower(nick) + "!" + irc_lower(ident) + "@" + host.lower()
    flags = var.FLAGS[hostmask] + var.FLAGS_ACCS[acc]

    if not "F" in flags:
        try:
            hosts = set(botconfig.ADMINS)
            accounts = set(botconfig.ADMINS_ACCOUNTS)

            if not var.DISABLE_ACCOUNTS and acc and acc != "*":
                for pattern in accounts:
                    if fnmatch.fnmatch(irc_lower(acc), irc_lower(pattern)):
                        return True

            if host:
                for hostmask in hosts:
                    if match_hostmask(hostmask, nick, ident, host):
                        return True
        except AttributeError:
            pass

        return is_owner(nick, ident, host, acc)

    return True

def plural(role, count=2):
    if count == 1:
        return role
    bits = role.split()
    if bits[-1][-2:] == "'s":
        bits[-1] = plural(bits[-1][:-2], count)
        bits[-1] += "'" if bits[-1][-1] == "s" else "'s"
    else:
        bits[-1] = {"person": "people",
                    "wolf": "wolves",
                    "has": "have",
                    "succubus": "succubi",
                    "child": "children"}.get(bits[-1], bits[-1] + "s")
    return " ".join(bits)

def singular(plural):
    # converse of plural above (kinda)
    # this is used to map plural team names back to singular,
    # so we don't need to worry about stuff like possessives
    # Note that this is currently only ever called on team names,
    # and will require adjustment if one wishes to use it on roles.
    # fool is present since we store fool wins as 'fool' rather than
    # 'fools' as only a single fool wins, however we don't want to
    # chop off the l and have it report 'foo wins'
    conv = {"wolves": "wolf",
            "succubi": "succubus",
            "fool": "fool"}
    if plural in conv:
        return conv[plural]
    # otherwise we just added an s on the end
    return plural[:-1]

def list_players(roles=None, *, rolemap=None):
    if rolemap is None:
        rolemap = var.ROLES
    if roles is None:
        roles = rolemap.keys()
    pl = set()
    for x in roles:
        if x in var.TEMPLATE_RESTRICTIONS:
            continue
        pl.update(rolemap.get(x, ()))
    if rolemap is not var.ROLES:
        # we weren't given an actual player list (possibly),
        # so the elements of pl are not necessarily in var.ALL_PLAYERS
        return list(pl)
    return [p.nick for p in var.ALL_PLAYERS if p.nick in pl]

def list_players_and_roles():
    plr = {}
    for x in var.ROLES.keys():
        if x in var.TEMPLATE_RESTRICTIONS.keys():
            continue # only get actual roles
        for p in var.ROLES[x]:
            plr[p] = x
    return plr

def list_participants():
    """List all people who are still able to participate in the game in some fashion."""
    pl = list_players()
    evt = Event("list_participants", {"pl": pl})
    evt.dispatch(var)
    return evt.data["pl"][:]

def get_role(p):
    for role, pl in var.ROLES.items():
        if role in var.TEMPLATE_RESTRICTIONS.keys():
            continue # only get actual roles
        if p in pl:
            return role
    # not found in player list, see if they're a special participant
    role = None
    if p in list_participants():
        evt = Event("get_participant_role", {"role": None})
        evt.dispatch(var, p)
        role = evt.data["role"]
    if role is None:
        raise ValueError("Nick {0} isn't playing and has no defined participant role".format(p))
    return role

def get_roles(*roles, rolemap=None):
    if rolemap is None:
        rolemap = var.ROLES
    all_roles = []
    for role in roles:
        all_roles.append(rolemap[role])
    return list(itertools.chain(*all_roles))

def get_reveal_role(nick):
    if var.HIDDEN_AMNESIAC and nick in var.ORIGINAL_ROLES["amnesiac"]:
        role = "amnesiac"
    elif var.HIDDEN_CLONE and nick in var.ORIGINAL_ROLES["clone"]:
        role = "clone"
    else:
        role = get_role(nick)

    evt = Event("get_reveal_role", {"role": role})
    evt.dispatch(var, nick)
    role = evt.data["role"]

    if var.ROLE_REVEAL != "team":
        return role

    if role in var.WOLFTEAM_ROLES:
        return "wolfteam player"
    elif role in var.TRUE_NEUTRAL_ROLES:
        return "neutral player"
    else:
        return "village member"

def get_templates(nick):
    tpl = []
    for x in var.TEMPLATE_RESTRICTIONS.keys():
        try:
            if nick in var.ROLES[x]:
                tpl.append(x)
        except KeyError:
            pass

    return tpl

role_order = lambda: var.ROLE_GUIDE

def break_long_message(phrases, joinstr = " "):
    message = []
    count = 0
    for phrase in phrases:
        # IRC max is 512, but freenode splits around 380ish, make 300 to have plenty of wiggle room
        if count + len(joinstr) + len(phrase) > 300:
            message.append("\n" + phrase)
            count = len(phrase)
        else:
            if not message:
                count = len(phrase)
            else:
                count += len(joinstr) + len(phrase)
            message.append(phrase)
    return joinstr.join(message)

#completes a partial nickname or string from a list
def complete_match(string, matches):
    possible_matches = set()
    for possible in matches:
        if string == possible:
            return [string]
        if possible.startswith(string) or possible.lstrip("[{\\^_`|}]").startswith(string):
            possible_matches.add(possible)
    return sorted(possible_matches)

def complete_one_match(string, matches):
    matches = complete_match(string,matches) 
    if len(matches) == 1:
        return matches.pop()
    return None

#wrapper around complete_match() used for roles
def get_victim(cli, nick, victim, in_chan, self_in_list=False, bot_in_list=False):
    chan = botconfig.CHANNEL if in_chan else nick
    if not victim:
        reply(cli, nick, chan, messages["not_enough_parameters"], private=True)
        return
    pl = [x for x in list_players() if x != nick or self_in_list]
    pll = [x.lower() for x in pl]

    if bot_in_list: # for villagergame
        pl.append(botconfig.NICK)
        pll.append(botconfig.NICK.lower())

    tempvictims = complete_match(victim.lower(), pll)
    if len(tempvictims) != 1:
        #ensure messages about not being able to act on yourself work
        if len(tempvictims) == 0 and nick.lower().startswith(victim.lower()):
            return nick
        reply(cli, nick, chan, messages["not_playing"].format(victim), private=True)
        return
    return pl[pll.index(tempvictims.pop())] #convert back to normal casing

# wrapper around complete_match() used for any nick on the channel
def get_nick(cli, nick):
    ul = [x for x in var.USERS]
    ull = [x.lower() for x in var.USERS]
    lnick = complete_match(nick.lower(), ull)
    if not lnick:
        return None
    return ul[ull.index(lnick)]

class InvalidModeException(Exception): pass

# vim: set sw=4 expandtab:
