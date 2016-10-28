from datetime import datetime, timedelta
import re

import botconfig
import src.settings as var
from src import db
from src.utilities import *
from src.decorators import cmd
from src.events import Event
from src.messages import messages

__all__ = ["is_user_stasised", "decrement_stasis", "parse_warning_target", "add_warning", "expire_tempbans"]

def is_user_stasised(nick):
    """Checks if a user is in stasis. Returns a number of games in stasis."""

    if nick in var.USERS:
        ident = irc_lower(var.USERS[nick]["ident"])
        host = var.USERS[nick]["host"].lower()
        acc = irc_lower(var.USERS[nick]["account"])
    else:
        return -1
    amount = 0
    if not var.DISABLE_ACCOUNTS and acc and acc != "*":
        if acc in var.STASISED_ACCS:
            amount = var.STASISED_ACCS[acc]
    for hostmask in var.STASISED:
        if match_hostmask(hostmask, nick, ident, host):
           amount = max(amount, var.STASISED[hostmask])
    return amount

def decrement_stasis(nick=None):
    if nick and nick in var.USERS:
        ident = irc_lower(var.USERS[nick]["ident"])
        host = var.USERS[nick]["host"].lower()
        acc = irc_lower(var.USERS[nick]["account"])
        # decrement account stasis even if accounts are disabled
        if acc in var.STASISED_ACCS:
            db.decrement_stasis(acc=acc)
        for hostmask in var.STASISED:
            if match_hostmask(hostmask, nick, ident, host):
                db.decrement_stasis(hostmask=hostmask)
    else:
        db.decrement_stasis()
    # Also expire any expired stasis and tempbans and update our tracking vars
    db.expire_stasis()
    db.init_vars()

def expire_tempbans(cli):
    acclist, hmlist = db.expire_tempbans()
    cmodes = []
    for acc in acclist:
        cmodes.append(("-b", "{0}{1}".format(var.ACCOUNT_PREFIX, acc)))
    for hm in hmlist:
        cmodes.append(("-b", "*!*@{0}".format(hm)))
    mass_mode(cli, cmodes, [])

def parse_warning_target(target, lower=False):
    if target[0] == "=":
        if var.DISABLE_ACCOUNTS:
            return (None, None)
        tacc = target[1:]
        thm = None
        if lower:
            tacc = irc_lower(tacc)
    elif target in var.USERS:
        tacc = var.USERS[target]["account"]
        ident = var.USERS[target]["ident"]
        host = var.USERS[target]["host"]
        if lower:
            tacc = irc_lower(tacc)
            ident = irc_lower(ident)
            host = host.lower()
        thm = target + "!" + ident + "@" + host
    elif "@" in target:
        tacc = None
        thm = target
        if lower:
            hml, hmr = thm.split("@", 1)
            thm = irc_lower(hml) + "@" + hmr.lower()
    elif not var.DISABLE_ACCOUNTS:
        tacc = target
        thm = None
        if lower:
            tacc = irc_lower(tacc)
    else:
        return (None, None)
    return (tacc, thm)

def add_warning(cli, target, amount, actor, reason, notes=None, expires=None, sanctions=None):
    # make 0-point warnings no-op successfully, otherwise we add warnings when things like PART_PENALTY is 0
    if amount == 0:
        return False

    tacc, thm = parse_warning_target(target)
    if tacc is None and thm is None:
        return False

    if actor not in var.USERS and actor != botconfig.NICK:
        return False
    sacc = None
    shm = None
    if actor in var.USERS:
        sacc = var.USERS[actor]["account"]
        shm = actor + "!" + var.USERS[actor]["ident"] + "@" + var.USERS[actor]["host"]

    # Turn expires into a datetime if we were passed a string; note that no error checking is performed here
    if isinstance(expires, str):
        exp_suffix = expires[-1]
        exp_amount = int(expires[:-1])

        if exp_suffix == "d":
            expires = datetime.utcnow() + timedelta(days=exp_amount)
        elif exp_suffix == "h":
            expires = datetime.utcnow() + timedelta(hours=exp_amount)
        elif exp_suffix == "m":
            expires = datetime.utcnow() + timedelta(minutes=exp_amount)
        else:
            raise ValueError("Invalid expiration string")
    elif isinstance(expires, int):
        expires = datetime.utcnow() + timedelta(days=expires)

    # Round expires to the nearest minute (30s rounds up)
    if isinstance(expires, datetime):
        round_add = 0
        if expires.second >= 30:
            round_add = 1
        expires -= timedelta(seconds=expires.second, microseconds=expires.microsecond)
        expires += timedelta(minutes=round_add)

    # determine if we need to automatically add any sanctions
    if sanctions is None:
        sanctions = {}
    prev = db.get_warning_points(tacc, thm)
    cur = prev + amount
    for (mn, mx, sanc) in var.AUTO_SANCTION:
        if (prev < mn and cur >= mn) or (prev >= mn and prev <= mx and cur <= mx):
            if "stasis" in sanc:
                if "stasis" not in sanctions:
                    sanctions["stasis"] = sanc["stasis"]
                else:
                    sanctions["stasis"] = max(sanctions["stasis"], sanc["stasis"])
            if "scalestasis" in sanc:
                (a, b, c) = sanc["scalestasis"]
                amt = (a * cur * cur) + (b * cur) + c
                if "stasis" not in sanctions:
                    sanctions["stasis"] = amt
                else:
                    sanctions["stasis"] = max(sanctions["stasis"], amt)
            if "deny" in sanc:
                if "deny" not in sanctions:
                    sanctions["deny"] = set(sanc["deny"])
                else:
                    sanctions["deny"].update(sanc["deny"])
            if "tempban" in sanc:
                # tempban's param can either be a fixed expiry time or a number
                # which indicates the warning point threshold that the ban will be lifted at
                # if two are set at once, the threshold takes precedence over set times
                # within each category, a larger set time or a lower threshold takes precedence
                exp = None
                ths = None
                if isinstance(sanc["tempban"], str) and sanc["tempban"][-1] in ("d", "h", "m"):
                    amt = int(sanc["tempban"][:-1])
                    dur = sanc["tempban"][-1]
                    if dur == "d":
                        exp = datetime.utcnow() + timedelta(days=amt)
                    elif dur == "h":
                        exp = datetime.utcnow() + timedelta(hours=amt)
                    elif dur == "m":
                        exp = datetime.utcnow() + timedelta(minutes=amt)
                else:
                    ths = int(sanc["tempban"])

                if "tempban" in sanctions:
                    if isinstance(sanctions["tempban"], datetime):
                        if ths is not None:
                            sanctions["tempban"] = ths
                        else:
                            sanctions["tempban"] = max(sanctions["tempban"], exp)
                    elif ths is not None:
                        sanctions["tempban"] = min(sanctions["tempban"], ths)
                elif ths is not None:
                    sanctions["tempban"] = ths
                else:
                    sanctions["tempban"] = exp

    sid = db.add_warning(tacc, thm, sacc, shm, amount, reason, notes, expires)
    if "stasis" in sanctions:
        db.add_warning_sanction(sid, "stasis", sanctions["stasis"])
    if "deny" in sanctions:
        for cmd in sanctions["deny"]:
            db.add_warning_sanction(sid, "deny command", cmd)
    if "tempban" in sanctions:
        # this inserts into the bantrack table too
        (acclist, hmlist) = db.add_warning_sanction(sid, "tempban", sanctions["tempban"])
        cmodes = []
        for acc in acclist:
            cmodes.append(("+b", "{0}{1}".format(var.ACCOUNT_PREFIX, acc)))
        for hm in hmlist:
            cmodes.append(("+b", "*!*@{0}".format(hm)))
        mass_mode(cli, cmodes, [])
        for (nick, user) in var.USERS.items():
            if user["account"] in acclist:
                cli.kick(botconfig.CHANNEL, nick, messages["tempban_kick"].format(nick=nick, botnick=botconfig.NICK, reason=reason))
            elif user["host"] in hmlist:
                cli.kick(botconfig.CHANNEL, nick, messages["tempban_kick"].format(nick=nick, botnick=botconfig.NICK, reason=reason))

    # Update any tracking vars that may have changed due to this
    db.init_vars()

    return sid

@cmd("stasis", chan=True, pm=True)
def stasis(cli, nick, chan, rest):
    st = is_user_stasised(nick)
    if st:
        msg = messages["your_current_stasis"].format(st, "" if st == 1 else "s")
    else:
        msg = messages["you_not_in_stasis"]

    reply(cli, nick, chan, msg, prefix_nick=True)

@cmd("fstasis", flag="A", chan=True, pm=True)
def fstasis(cli, nick, chan, rest):
    """Removes or views stasis penalties."""

    data = rest.split()
    msg = None

    if data:
        lusers = {k.lower(): v for k, v in var.USERS.items()}
        acc, hostmask = parse_warning_target(data[0], lower=True)
        cur = max(var.STASISED[hostmask], var.STASISED_ACCS[acc])

        if len(data) == 1:
            if acc is not None and var.STASISED_ACCS[acc] == cur:
                plural = "" if cur == 1 else "s"
                reply(cli, nick, chan, messages["account_in_stasis"].format(data[0], acc, cur, plural))
            elif hostmask is not None and var.STASISED[hostmask] == cur:
                plural = "" if cur == 1 else "s"
                reply(cli, nick, chan, messages["hostmask_in_stasis"].format(data[0], hostmask, cur, plural))
            elif acc is not None:
                reply(cli, nick, chan, messages["account_not_in_stasis"].format(data[0], acc))
            else:
                reply(cli, nick, chan, messages["hostmask_not_in_stasis"].format(data[0], hostmask))
        else:
            try:
                amt = int(data[1])
            except ValueError:
                reply(cli, nick, chan, messages["stasis_not_negative"])
                return

            if amt < 0:
                reply(cli, nick, chan, messages["stasis_not_negative"])
                return
            elif amt > cur and var.RESTRICT_FSTASIS:
                reply(cli, nick, chan, messages["stasis_cannot_increase"])
                return
            elif cur == 0:
                if acc is not None:
                    reply(cli, nick, chan, messages["account_not_in_stasis"].format(data[0], acc))
                    return
                else:
                    reply(cli, nick, chan, messages["hostmask_not_in_stasis"].format(data[0], hostmask))
                    return

            db.set_stasis(amt, acc, hostmask)
            db.init_vars()
            if amt > 0:
                plural = "" if amt == 1 else "s"
                if acc is not None:
                    reply(cli, nick, chan, messages["fstasis_account_add"].format(data[0], acc, amt, plural))
                else:
                    reply(cli, nick, chan, messages["fstasis_hostmask_add"].format(data[0], hostmask, amt, plural))
            elif acc is not None:
                reply(cli, nick, chan, messages["fstasis_account_remove"].format(data[0], acc))
            else:
                reply(cli, nick, chan, messages["fstasis_hostmask_remove"].format(data[0], hostmask))
    elif var.STASISED or var.STASISED_ACCS:
        stasised = {}
        for hostmask in var.STASISED:
            if var.DISABLE_ACCOUNTS:
                stasised[hostmask] = var.STASISED[hostmask]
            else:
                stasised[hostmask+" (Host)"] = var.STASISED[hostmask]
        if not var.DISABLE_ACCOUNTS:
            for acc in var.STASISED_ACCS:
                stasised[acc+" (Account)"] = var.STASISED_ACCS[acc]
        msg = messages["currently_stasised"].format(", ".join(
            "\u0002{0}\u0002 ({1})".format(usr, number)
            for usr, number in stasised.items()))
        reply(cli, nick, chan, msg)
    else:
        reply(cli, nick, chan, messages["noone_stasised"])

@cmd("warn", pm=True)
def warn(cli, nick, chan, rest):
    """View and acknowledge your warnings."""
    # !warn list [-all] [page] - lists all active warnings, or all warnings if all passed
    # !warn view <id> - views details on warning id
    # !warn ack <id> - acknowledges warning id
    # Default if only !warn is given is to do !warn list.
    params = re.split(" +", rest)

    try:
        command = params.pop(0)
        if command == "":
            command = "list"
    except IndexError:
        command = "list"

    if command not in ("list", "view", "ack", "help"):
        reply(cli, nick, chan, messages["warn_usage"])
        return

    if command == "help":
        try:
            subcommand = params.pop(0)
        except IndexError:
            reply(cli, nick, chan, messages["warn_help_syntax"])
            return
        if subcommand not in ("list", "view", "ack", "help"):
            reply(cli, nick, chan, messages["warn_usage"])
            return
        reply(cli, nick, chan, messages["warn_{0}_syntax".format(subcommand)])
        return

    if command == "list":
        list_all = False
        page = 1
        try:
            list_all = params.pop(0)
            target = params.pop(0)
            page = int(params.pop(0))
        except IndexError:
            pass
        except ValueError:
            reply(cli, nick, chan, messages["fwarn_page_invalid"])
            return

        try:
            if list_all and list_all != "-all":
                page = int(list_all)
                list_all = False
            elif list_all == "-all":
                list_all = True
        except ValueError:
            reply(cli, nick, chan, messages["fwarn_page_invalid"])
            return

        acc, hm = parse_warning_target(nick)
        warnings = db.list_warnings(acc, hm, expired=list_all, skip=(page-1)*10, show=11)
        points = db.get_warning_points(acc, hm)
        reply(cli, nick, chan, messages["warn_list_header"].format(points, "" if points == 1 else "s"), private=True)

        i = 0
        for warn in warnings:
            i += 1
            if (i == 11):
                parts = []
                if list_all:
                    parts.append("-all")
                parts.append(str(page + 1))
                reply(cli, nick, chan, messages["warn_list_footer"].format(" ".join(parts)), private=True)
                break
            start = ""
            end = ""
            ack = ""
            if warn["expires"] is not None:
                if warn["expired"]:
                    expires = messages["fwarn_list_expired"].format(warn["expires"])
                else:
                    expires = messages["fwarn_view_expires"].format(warn["expires"])
            else:
                expires = messages["fwarn_never_expires"]
            if warn["expired"]:
                start = "\u000314"
                end = " [\u00037{0}\u000314]\u0003".format(messages["fwarn_expired"])
            if not warn["ack"]:
                ack = "\u0002!\u0002 "
            reply(cli, nick, chan, messages["warn_list"].format(
                start, ack, warn["id"], warn["issued"], warn["reason"], warn["amount"],
                "" if warn["amount"] == 1 else "s", expires, end), private=True)
        if i == 0:
            reply(cli, nick, chan, messages["fwarn_list_empty"], private=True)
        return

    if command == "view":
        try:
            warn_id = params.pop(0)
            if warn_id[0] == "#":
                warn_id = warn_id[1:]
            warn_id = int(warn_id)
        except (IndexError, ValueError):
            reply(cli, nick, chan, messages["warn_view_syntax"])
            return

        acc, hm = parse_warning_target(nick)
        warning = db.get_warning(warn_id, acc, hm)
        if warning is None:
            reply(cli, nick, chan, messages["fwarn_invalid_warning"])
            return

        if warning["expired"]:
            expires = messages["fwarn_view_expired"].format(warning["expires"])
        elif warning["expires"] is None:
            expires = messages["fwarn_view_active"].format(messages["fwarn_never_expires"])
        else:
            expires = messages["fwarn_view_active"].format(messages["fwarn_view_expires"].format(warning["expires"]))

        reply(cli, nick, chan, messages["warn_view_header"].format(
            warning["id"], warning["issued"], warning["amount"],
            "" if warning["amount"] == 1 else "s", expires), private=True)
        reply(cli, nick, chan, warning["reason"], private=True)

        sanctions = []
        if not warning["ack"]:
            sanctions.append(messages["warn_view_ack"].format(warning["id"]))
        if warning["sanctions"]:
            sanctions.append(messages["fwarn_view_sanctions"])
            if "stasis" in warning["sanctions"]:
                if warning["sanctions"]["stasis"] != 1:
                    sanctions.append(messages["fwarn_view_stasis_plural"].format(warning["sanctions"]["stasis"]))
                else:
                    sanctions.append(messages["fwarn_view_stasis_sing"])
            if "deny" in warning["sanctions"]:
                sanctions.append(messages["fwarn_view_deny"].format(", ".join(warning["sanctions"]["deny"])))
        if sanctions:
            reply(cli, nick, chan, " ".join(sanctions), private=True)
        return

    if command == "ack":
        try:
            warn_id = params.pop(0)
            if warn_id[0] == "#":
                warn_id = warn_id[1:]
            warn_id = int(warn_id)
        except (IndexError, ValueError):
            reply(cli, nick, chan, messages["warn_ack_syntax"])
            return

        acc, hm = parse_warning_target(nick)
        warning = db.get_warning(warn_id, acc, hm)
        if warning is None:
            reply(cli, nick, chan, messages["fwarn_invalid_warning"])
            return

        # only add stasis if this is the first time this warning is being acknowledged
        if not warning["ack"] and warning["sanctions"].get("stasis", 0) > 0:
            db.set_stasis(warning["sanctions"]["stasis"], acc, hm, relative=True)
            db.init_vars()
        db.acknowledge_warning(warn_id)
        reply(cli, nick, chan, messages["fwarn_done"])
        return

@cmd("fwarn", flag="F", pm=True)
def fwarn(cli, nick, chan, rest):
    """Issues a warning to someone or views warnings."""
    # !fwarn list [-all] [nick] [page]
    # -all => Shows all warnings, if omitted only shows active (non-expired and non-deleted) ones.
    # nick => nick to view warnings for. Can also be a hostmask in nick!user@host form. If nick
    #     is not online, interpreted as an account name. To specify an account if nick is online,
    #     use =account. If not specified, shows all warnings on the bot.
    # !fwarn view <id> - views details on warning id
    # !fwarn del <id> - deletes warning id
    # !fwarn set <id> [~expiry] [reason] [| notes]
    # !fwarn add <nick> <points> [~expiry] [sanctions] [:]<reason> [| notes]
    # e.g. !fwarn add lykos 1 ~30d deny=goat,gstats stasis=5 Spamming | I secretly just hate him
    # nick => nick to warn. Can also be a hostmask in nick!user@host form. If nick is not online,
    #    interpreted as an account name. To specify an account if nick is online, use =account.
    # points => Warning points, must be above 0
    # ~expiry => Expiration time, must be suffixed with d (days), h (hours), or m (minutes)
    # sanctions => list of sanctions. Valid sanctions are:
    #    deny: denies access to the listed commands
    #    stasis: gives the user stasis
    # reason => Reason, required. If the first word of the reason is also a sanction, prefix it with :
    # |notes => Secret notes, not shown to the user (only shown if viewing the warning in PM)
    #    If specified, must be prefixed with |. This means | is not a valid character for use
    #    in reasons (no escaping is performed).

    params = re.split(" +", rest)
    target = None
    points = None
    expires = None
    sanctions = {}
    reason = None
    notes = None

    try:
        command = params.pop(0)
    except IndexError:
        reply(cli, nick, chan, messages["fwarn_usage"])
        return

    if command not in ("list", "view", "add", "del", "set", "help"):
        # if what follows is a number, assume we're viewing or setting a warning
        # (depending on number of params)
        # if it's another string, assume we're adding or listing, again depending
        # on number of params
        params.insert(0, command)
        try:
            num = int(command)
            if len(params) == 1:
                command = "view"
            else:
                command = "set"
        except ValueError:
            if len(params) < 3 or params[1] == "-all":
                command = "list"
                if len(params) > 1 and params[1] == "-all":
                    # fwarn list expects these two params in a different order
                    params.pop(1)
                    params.insert(0, "-all")
            else:
                command = "add"

    if command == "help":
        try:
            subcommand = params.pop(0)
        except IndexError:
            reply(cli, nick, chan, messages["fwarn_help_syntax"])
            return
        if subcommand not in ("list", "view", "add", "del", "set", "help"):
            reply(cli, nick, chan, messages["fwarn_usage"])
            return
        reply(cli, nick, chan, messages["fwarn_{0}_syntax".format(subcommand)])
        return

    if command == "list":
        list_all = False
        page = 1
        try:
            list_all = params.pop(0)
            target = params.pop(0)
            page = int(params.pop(0))
        except IndexError:
            pass
        except ValueError:
            reply(cli, nick, chan, messages["fwarn_page_invalid"])
            return

        try:
            if list_all and list_all != "-all":
                if target is not None:
                    page = int(target)
                target = list_all
                list_all = False
            elif list_all == "-all":
                list_all = True
        except ValueError:
            reply(cli, nick, chan, messages["fwarn_page_invalid"])
            return

        try:
            page = int(target)
            target = None
        except (TypeError, ValueError):
            pass

        if target is not None:
            acc, hm = parse_warning_target(target)
            if acc is None and hm is None:
                reply(cli, nick, chan, messages["fwarn_nick_invalid"])
                return
            warnings = db.list_warnings(acc, hm, expired=list_all, deleted=list_all, skip=(page-1)*10, show=11)
            points = db.get_warning_points(acc, hm)
            reply(cli, nick, chan, messages["fwarn_list_header"].format(target, points, "" if points == 1 else "s"), private=True)
        else:
            warnings = db.list_all_warnings(list_all=list_all, skip=(page-1)*10, show=11)

        i = 0
        for warn in warnings:
            i += 1
            if (i == 11):
                parts = []
                if list_all:
                    parts.append("-all")
                if target is not None:
                    parts.append(target)
                parts.append(str(page + 1))
                reply(cli, nick, chan, messages["fwarn_list_footer"].format(" ".join(parts)), private=True)
                break
            start = ""
            end = ""
            ack = ""
            if warn["expires"] is not None:
                if warn["expired"]:
                    expires = messages["fwarn_list_expired"].format(warn["expires"])
                else:
                    expires = messages["fwarn_view_expires"].format(warn["expires"])
            else:
                expires = messages["fwarn_never_expires"]
            if warn["deleted"]:
                start = "\u000314"
                end = " [\u00034{0}\u000314]\u0003".format(messages["fwarn_deleted"])
            elif warn["expired"]:
                start = "\u000314"
                end = " [\u00037{0}\u000314]\u0003".format(messages["fwarn_expired"])
            if not warn["ack"]:
                ack = "\u0002!\u0002 "
            reply(cli, nick, chan, messages["fwarn_list"].format(
                start, ack, warn["id"], warn["issued"], warn["target"],
                warn["sender"], warn["reason"], warn["amount"],
                "" if warn["amount"] == 1 else "s", expires, end), private=True)
        if i == 0:
            reply(cli, nick, chan, messages["fwarn_list_empty"], private=True)
        return

    if command == "view":
        try:
            warn_id = params.pop(0)
            if warn_id[0] == "#":
                warn_id = warn_id[1:]
            warn_id = int(warn_id)
        except (IndexError, ValueError):
            reply(cli, nick, chan, messages["fwarn_view_syntax"])
            return

        warning = db.get_warning(warn_id)
        if warning is None:
            reply(cli, nick, chan, messages["fwarn_invalid_warning"])
            return

        if warning["deleted"]:
            expires = messages["fwarn_view_deleted"].format(warning["deleted_on"], warning["deleted_by"])
        elif warning["expired"]:
            expires = messages["fwarn_view_expired"].format(warning["expires"])
        elif warning["expires"] is None:
            expires = messages["fwarn_view_active"].format(messages["fwarn_never_expires"])
        else:
            expires = messages["fwarn_view_active"].format(messages["fwarn_view_expires"].format(warning["expires"]))

        reply(cli, nick, chan, messages["fwarn_view_header"].format(
            warning["id"], warning["target"], warning["issued"], warning["sender"],
            warning["amount"], "" if warning["amount"] == 1 else "s", expires), private=True)

        reason = [warning["reason"]]
        if warning["notes"] is not None:
            reason.append(warning["notes"])
        reply(cli, nick, chan, " | ".join(reason), private=True)

        sanctions = []
        if not warning["ack"]:
            sanctions.append(messages["fwarn_view_ack"])
        if warning["sanctions"]:
            sanctions.append(messages["fwarn_view_sanctions"])
            if "stasis" in warning["sanctions"]:
                if warning["sanctions"]["stasis"] != 1:
                    sanctions.append(messages["fwarn_view_stasis_plural"].format(warning["sanctions"]["stasis"]))
                else:
                    sanctions.append(messages["fwarn_view_stasis_sing"])
            if "deny" in warning["sanctions"]:
                sanctions.append(messages["fwarn_view_deny"].format(", ".join(warning["sanctions"]["deny"])))
            if "tempban" in warning["sanctions"]:
                sanctions.append(messages["fwarn_view_tempban"].format(warning["sanctions"]["tempban"]))
        if sanctions:
            reply(cli, nick, chan, " ".join(sanctions), private=True)
        return

    if command == "del":
        try:
            warn_id = params.pop(0)
            if warn_id[0] == "#":
                warn_id = warn_id[1:]
            warn_id = int(warn_id)
        except (IndexError, ValueError):
            reply(cli, nick, chan, messages["fwarn_del_syntax"])
            return

        warning = db.get_warning(warn_id)
        if warning is None:
            reply(cli, nick, chan, messages["fwarn_invalid_warning"])
            return

        acc, hm = parse_warning_target(nick)
        db.del_warning(warn_id, acc, hm)
        reply(cli, nick, chan, messages["fwarn_done"])

        if var.LOG_CHANNEL:
            cli.msg(var.LOG_CHANNEL, messages["fwarn_log_del"].format(warn_id, warning["target"], hm,
                    warning["reason"], (" | " + warning["notes"]) if warning["notes"] else ""))

        return

    if command == "set":
        try:
            warn_id = params.pop(0)
            if warn_id[0] == "#":
                warn_id = warn_id[1:]
            warn_id = int(warn_id)
        except (IndexError, ValueError):
            reply(cli, nick, chan, messages["fwarn_set_syntax"])
            return

        warning = db.get_warning(warn_id)
        if warning is None:
            reply(cli, nick, chan, messages["fwarn_invalid_warning"])
            return

        rsp = " ".join(params).split("|", 1)
        if len(rsp) == 1:
            rsp.append(None)
        reason, notes = rsp
        reason = reason.strip()

        # check for modified expiry
        expires = warning["expires"]
        rsp = reason.split(" ", 1)
        if rsp[0] and rsp[0][0] == "~":
            if len(rsp) == 1:
                rsp.append("")
            expires, reason = rsp
            expires = expires[1:]
            reason = reason.strip()

            if expires in messages["never_aliases"]:
                expires = None
            else:
                suffix = expires[-1]
                try:
                    amount = int(expires[:-1])
                except ValueError:
                    reply(cli, nick, chan, messages["fwarn_expiry_invalid"])
                    return

                if amount <= 0:
                    reply(cli, nick, chan, messages["fwarn_expiry_invalid"])
                    return

                issued = datetime.strptime(warning["issued"], "%Y-%m-%d %H:%M:%S")
                if suffix == "d":
                    expires = issued + timedelta(days=amount)
                elif suffix == "h":
                    expires = issued + timedelta(hours=amount)
                elif suffix == "m":
                    expires = issued + timedelta(minutes=amount)
                else:
                    reply(cli, nick, chan, messages["fwarn_expiry_invalid"])
                    return

                round_add = 0
                if expires.second >= 30:
                    round_add = 1
                expires -= timedelta(seconds=expires.second, microseconds=expires.microsecond)
                expires += timedelta(minutes=round_add)

        # maintain existing reason if none was specified
        if not reason:
            reason = warning["reason"]

        # maintain existing notes if none were specified
        if notes is not None:
            notes = notes.strip()
            if not notes:
                notes = None
        else:
            notes = warning["notes"]

        db.set_warning(warn_id, expires, reason, notes)
        reply(cli, nick, chan, messages["fwarn_done"])

        if var.LOG_CHANNEL:
            changes = []
            if expires != warning["expires"]:
                oldexpiry = warning["expires"] if warning["expires"] else messages["fwarn_log_set_noexpiry"]
                newexpiry = expires if expires else messages["fwarn_log_set_noexpiry"]
                changes.append(messages["fwarn_log_set_expiry"].format(oldexpiry, newexpiry))
            if reason != warning["reason"]:
                changes.append(messages["fwarn_log_set_reason"].format(warning["reason"], reason))
            if notes != warning["notes"]:
                if warning["notes"]:
                    changes.append(messages["fwarn_log_set_notes"].format(warning["notes"], notes))
                else:
                    changes.append(messages["fwarn_log_set_notes_new"].format(notes))
            if changes:
                log_msg = messages["fwarn_log_set"].format(warn_id, warning["target"], nick, " | ".join(changes))
                cli.msg(var.LOG_CHANNEL, log_msg)

        return

    # command == "add"
    while params:
        p = params.pop(0)
        if target is None:
            # figuring out what target actually is is handled in add_warning
            target = p
        elif points is None:
            try:
                points = int(p)
            except ValueError:
                reply(cli, nick, chan, messages["fwarn_points_invalid"])
                return
            if points < 1:
                reply(cli, nick, chan, messages["fwarn_points_invalid"])
                return
        elif notes is not None:
            notes += " " + p
        elif reason is not None:
            rsp = p.split("|", 1)
            if len(rsp) > 1:
                notes = rsp[1]
            reason += " " + rsp[0]
        elif p[0] == ":":
            if p == ":":
                reason = ""
            else:
                reason = p[1:]
        elif p[0] == "~":
            if p == "~":
                reply(cli, nick, chan, messages["fwarn_syntax"])
                return
            expires = p[1:]
        else:
            # sanctions are the only thing left here
            sanc = p.split("=", 1)
            if sanc[0] == "deny":
                try:
                    cmds = sanc[1].split(",")
                    normalized_cmds = set()
                    for cmd in cmds:
                        normalized = None
                        for obj in COMMANDS[cmd]:
                            # do not allow denying in-game commands (vote, see, etc.)
                            # this technically traps goat too, so special case that, as we want
                            # goat to be deny-able. Furthermore, the warn command cannot be denied.
                            if (not obj.playing and not obj.roles) or obj.name == "goat":
                                normalized = obj.name
                            if normalized == "warn":
                                normalized = None
                        if normalized is None:
                            reply(cli, nick, chan, messages["fwarn_deny_invalid_command"].format(cmd))
                            return
                        normalized_cmds.add(normalized)
                    sanctions["deny"] = normalized_cmds
                except IndexError:
                    reply(cli, nick, chan, messages["fwarn_deny_invalid"])
                    return
            elif sanc[0] == "stasis":
                try:
                    sanctions["stasis"] = int(sanc[1])
                except (IndexError, ValueError):
                    reply(cli, nick, chan, messages["fwarn_stasis_invalid"])
                    return
            elif sanc[0] == "tempban":
                try:
                    banamt = sanc[1]
                    suffix = banamt[-1]
                    if suffix not in ("d", "h", "m"):
                        sanctions["tempban"] = int(banamt)
                    else:
                        banamt = int(banamt[:-1])
                        if suffix == "d":
                            sanctions["tempban"] = datetime.utcnow() + timedelta(days=banamt)
                        elif suffix == "h":
                            sanctions["tempban"] = datetime.utcnow() + timedelta(hours=banamt)
                        elif suffix == "m":
                            sanctions["tempban"] = datetime.utcnow() + timedelta(minutes=banamt)
                except (IndexError, ValueError):
                    reply(cli, nick, chan, messages["fwarn_tempban_invalid"])
                    return
            else:
                # not a valid sanction, assume this is the start of the reason
                reason = p

    if target is None or points is None or reason is None:
        reply(cli, nick, chan, messages["fwarn_add_syntax"])
        return

    reason = reason.strip()
    if notes is not None:
        notes = notes.strip()

    # convert expires into a proper datetime
    if expires is None:
        expires = var.DEFAULT_EXPIRY

    if expires.lower() in messages["never_aliases"]:
        expires = None

    try:
        warn_id = add_warning(cli, target, points, nick, reason, notes, expires, sanctions)
    except ValueError:
        reply(cli, nick, chan, messages["fwarn_expiry_invalid"])
        return

    if warn_id is False:
        reply(cli, nick, chan, messages["fwarn_cannot_add"])
    else:
        reply(cli, nick, chan, messages["fwarn_added"].format(warn_id))
        # Log to ops/log channel (even if the warning was placed in that channel)
        if var.LOG_CHANNEL:
            log_reason = reason
            if notes is not None:
                log_reason += " | " + notes
            if expires is None:
                log_length = messages["fwarn_log_add_noexpiry"]
            else:
                log_length = messages["fwarn_log_add_expiry"].format(expires)
            log_msg = messages["fwarn_log_add"].format(warn_id, target, nick, log_reason, points,
                                                       "" if points == 1 else "s", log_length)
            cli.msg(var.LOG_CHANNEL, log_msg)


# vim: set sw=4 expandtab:
