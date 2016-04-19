import re

import botconfig
import src.settings as var

# message either privmsg or notice, depending on user settings
# used in decorators (imported by proxy), so needs to go here
def pm(cli, target, message):
    if is_fake_nick(target) and botconfig.DEBUG_MODE:
        debuglog("Would message fake nick {0}: {1!r}".format(target, message))
        return

    if is_user_notice(target):
        cli.notice(target, message)
        return

    cli.msg(target, message)

from src import proxy, debuglog

# Some miscellaneous helper functions

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
    else:
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
    elif private or (nick not in var.list_players() and var.PHASE in var.GAME_PHASES and chan == botconfig.CHANNEL):
        cli.notice(nick, msg)
    else:
        if prefix_nick:
            cli.msg(chan, "{0}: {1}".format(nick, msg))
        else:
            cli.msg(chan, msg)

def is_user_simple(nick):
    if nick in var.USERS:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        acc = var.USERS[nick]["account"]
    else:
        return False
    if acc and acc != "*" and not var.DISABLE_ACCOUNTS:
        if acc in var.SIMPLE_NOTIFY_ACCS:
            return True
        return False
    elif not var.ACCOUNTS_ONLY:
        for hostmask in var.SIMPLE_NOTIFY:
            if var.match_hostmask(hostmask, nick, ident, host):
                return True
    return False

def is_user_notice(nick):
    if nick in var.USERS and var.USERS[nick]["account"] and var.USERS[nick]["account"] != "*" and not var.DISABLE_ACCOUNTS:
        if var.USERS[nick]["account"] in var.PREFER_NOTICE_ACCS:
            return True
    if nick in var.USERS and not var.ACCOUNTS_ONLY:
        ident = var.USERS[nick]["ident"]
        host = var.USERS[nick]["host"]
        for hostmask in var.PREFER_NOTICE:
            if var.match_hostmask(hostmask, nick, ident, host):
                return True
    return False

def is_fake_nick(who):
    return re.search(r"^[0-9]+$", who)

def in_wolflist(nick, who):
    myrole = var.get_role(nick)
    role = var.get_role(who)
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

    wcwolves = var.list_players(wcroles)
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

# vim: set expandtab:sw=4:ts=4:
