from __future__ import annotations

from datetime import datetime, timedelta
from typing import Union, List, Optional
import re

import botconfig  # type: ignore
import src.settings as var
from src import channels, db, users
from src.lineparse import LineParser, LineParseError, WantsHelp
from src.utilities import *
from src.decorators import command, COMMANDS
from src.events import Event
from src.messages import messages

__all__ = ["decrement_stasis", "add_warning", "expire_tempbans"]

def decrement_stasis(user=None):
    if user is not None:
        # decrement account stasis even if accounts are disabled
        if user.account in var.STASISED_ACCS:
            db.decrement_stasis(acc=user.account)
    else:
        db.decrement_stasis()
    # Also expire any expired stasis and tempbans and update our tracking vars
    db.expire_stasis()
    db.init_vars()

def expire_tempbans():
    acclist = db.expire_tempbans()
    cmodes = []
    for acc in acclist:
        cmodes.append(("-b", "{0}{1}".format(var.ACCOUNT_PREFIX, acc)))
    channels.Main.mode(*cmodes)

def _get_auto_sanctions(sanctions, prev, cur):
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
    

def add_warning(target: Union[str, users.User], amount: int, actor: users.User, reason: str, notes: str = None, expires=None, sanctions=None):
    if isinstance(target, users.User):
        tacc = target.account
        if tacc is None:
            return False
    else:
        tacc = target

    reason = reason.format()
    sacc = actor.account

    # Turn expires into a datetime if we were passed a string; note that no error checking is performed here
    if not isinstance(expires, datetime):
        expires = _parse_expires(expires)

    # determine if we need to automatically add any sanctions
    if sanctions is None:
        sanctions = {}
    prev = db.get_warning_points(tacc)
    cur = prev + amount
    if amount > 0:
        _get_auto_sanctions(sanctions, prev, cur)

    sid = db.add_warning(tacc, sacc, amount, reason, notes, expires)
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
        channels.Main.mode(*cmodes)
        for user in channels.Main.users:
            if user.account in acclist:
                channels.Main.kick(user, messages["tempban_kick"].format(nick=user, botnick=users.Bot.nick, reason=reason))

    # Update any tracking vars that may have changed due to this
    db.init_vars()

    return sid

@command("stasis", chan=True, pm=True)
def stasis(var, wrapper, message):
    st = wrapper.source.stasis_count()
    if st:
        msg = messages["your_current_stasis"].format(st)
    else:
        msg = messages["you_not_in_stasis"]

    wrapper.reply(msg, prefix_nick=True)

@command("fstasis", flag="A", chan=True, pm=True)
def fstasis(var, wrapper, message):
    """Removes or views stasis penalties."""

    data = re.split(" +", message)
    from src.context import lower as irc_lower

    if data[0]:
        m = users.complete_match(data[0])
        if m:
            acc = m.get().account
        else:
            acc = data[0]
        cur = var.STASISED_ACCS[irc_lower(acc)]

        if len(data) == 1:
            if var.STASISED_ACCS[irc_lower(acc)] == cur and cur > 0:
                wrapper.reply(messages["account_in_stasis"].format(data[0], acc, cur))
            else:
                wrapper.reply(messages["account_not_in_stasis"].format(data[0], acc))
        else:
            try:
                amt = int(data[1])
            except ValueError:
                wrapper.reply(messages["stasis_non_negative"])
                return

            if amt < 0:
                wrapper.reply(messages["stasis_non_negative"])
                return
            elif amt > cur and var.RESTRICT_FSTASIS:
                wrapper.reply(messages["stasis_cannot_increase"])
                return
            elif cur == 0:
                wrapper.reply(messages["account_not_in_stasis"].format(data[0], acc))
                return

            db.set_stasis(amt, acc)
            db.init_vars()
            if amt > 0:
                wrapper.reply(messages["fstasis_account_add"].format(data[0], acc, amt))
            else:
                wrapper.reply(messages["fstasis_account_remove"].format(data[0], acc))
    else:
        stasised = {}
        for acc in var.STASISED_ACCS:
            if var.STASISED_ACCS[acc] > 0:
                stasised[acc] = var.STASISED_ACCS[acc]

        if stasised:
            msg = messages["currently_stasised"].format(", ".join(
                "\u0002{0}\u0002 ({1})".format(usr, number)
                for usr, number in stasised.items()))
            wrapper.reply(msg)
        else:
            wrapper.reply(messages["noone_stasised"])

def _parse_expires(expires: str, base: Optional[str] = None) -> Optional[datetime]:
    if expires in messages.raw("never_aliases"):
        return None

    try:
        # if passed a raw int, treat it as days
        amount = int(expires)
        suffix = messages.raw("day_suffix")
    except ValueError:
        amount = int(expires[:-1])
        suffix = expires[-1]

    if amount <= 0:
        raise ValueError("amount cannot be negative")

    if not base:
        base_dt = datetime.utcnow()
    else:
        base_dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")

    if suffix == messages.raw("day_suffix"):
        expires_dt = base_dt + timedelta(days=amount)
    elif suffix == messages.raw("hour_suffix"):
        expires_dt = base_dt + timedelta(hours=amount)
    elif suffix == messages.raw("minute_suffix"):
        expires_dt = base_dt + timedelta(minutes=amount)
    else:
        raise ValueError("unrecognized time suffix")

    round_add = 0
    if expires_dt.second >= 30:
        round_add = 1
    expires_dt -= timedelta(seconds=expires_dt.second, microseconds=expires_dt.microsecond)
    expires_dt += timedelta(minutes=round_add)
    return expires_dt

def warn_list(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["warn_list_syntax"])
        return

    acc = wrapper.source.account
    if not acc:
        return

    warnings = db.list_warnings(acc, expired=args.all, skip=(args.page - 1) * 10, show=11)
    points = db.get_warning_points(acc)
    wrapper.pm(messages["warn_list_header"].format(points))

    for i, warning in enumerate(warnings):
        if i == 10:
            parts = []
            if args.all:
                parts.append(_wall[0])
            parts.append(str(args.page + 1))
            wrapper.pm(messages["warn_list_footer"].format("warn", parts))
            break
        wrapper.pm(messages["warn_list"].format(**warning))

    if not warnings:
        wrapper.pm(messages["fwarn_list_empty"])

def warn_view(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["warn_view_syntax"])
        return

    acc = wrapper.source.account
    if not acc:
        return

    warning = db.get_warning(args.id, acc)
    if not warning:
        wrapper.reply(messages["fwarn_invalid_warning"])
        return

    wrapper.pm(messages["warn_view_header"].format(**warning))
    wrapper.pm(warning["reason"])
    if not warning["ack"]:
        wrapper.pm(messages["warn_view_ack"].format(warning["id"]))

    sanctions = []
    if warning["sanctions"]:
        if "stasis" in warning["sanctions"]:
            sanctions.append(messages["warn_view_stasis"].format(warning["sanctions"]["stasis"]))
        if "deny" in warning["sanctions"]:
            sanctions.append(messages["warn_view_deny"].format(warning["sanctions"]["deny"]))
    if sanctions:
        wrapper.pm(messages["warn_view_sanctions"].format(sanctions))

def warn_ack(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["warn_ack_syntax"])
        return

    acc = wrapper.source.account
    if not acc:
        return

    warning = db.get_warning(args.id, acc)
    if not warning:
        wrapper.reply(messages["fwarn_invalid_warning"])
        return

    # only add stasis if this is the first time this warning is being acknowledged
    if not warning["ack"] and warning["sanctions"].get("stasis", 0) > 0:
        db.set_stasis(warning["sanctions"]["stasis"], acc, relative=True)
        db.init_vars()

    db.acknowledge_warning(args.id)
    wrapper.reply(messages["fwarn_done"])

def warn_help(var, wrapper, args):
    if args.command in _wl:
        wrapper.reply(messages["warn_list_syntax"])
    elif args.command in _wv:
        wrapper.reply(messages["warn_view_syntax"])
    elif args.command in _wa:
        wrapper.reply(messages["warn_ack_syntax"])
    elif args.command in _wh:
        wrapper.reply(messages["warn_help_syntax"])
    else:
        wrapper.reply(messages["warn_usage"])

def fwarn_add(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["fwarn_add_syntax"])
        return

    if args.account:
        target = args.nick
    else:
        m = users.complete_match(args.nick)
        if m:
            target = m.get()
        else:
            target = args.nick

    if args.points < 0:
        wrapper.reply(messages["fwarn_points_invalid"])
        return

    try:
        expires = _parse_expires(args.expires)
    except ValueError:
        wrapper.reply(messages["fwarn_expiry_invalid"])
        return

    sanctions = {}

    if args.stasis is not None:
        if args.stasis < 1:
            wrapper.reply(messages["fwarn_stasis_invalid"])
            return
        sanctions["stasis"] = args.stasis

    if args.deny is not None:
        normalized_cmds = set()
        for cmd in args.deny:
            for obj in COMMANDS[cmd]:
                normalized_cmds.add(obj.key)
        # don't allow the warn command to be denied
        # in-game commands bypass deny restrictions as well
        normalized_cmds.discard("warn")
        sanctions["deny"] = normalized_cmds

    if args.ban is not None:
        try:
            sanctions["tempban"] = _parse_expires(args.ban)
        except ValueError:
            try:
                sanctions["tempban"] = int(args.ban)
            except ValueError:
                wrapper.reply(messages["fwarn_tempban_invalid"])
                return

    reason = " ".join(args.reason).strip()

    if args.notes is not None:
        notes = " ".join(args.notes).strip()
    else:
        notes = None

    warn_id = add_warning(target, args.points, wrapper.source, reason, notes, expires, sanctions)
    if not warn_id:
        wrapper.reply(messages["fwarn_cannot_add"])
        return

    wrapper.reply(messages["fwarn_added"].format(warn_id))
    # Log to ops/log channel (even if the warning was placed in that channel)
    if var.LOG_CHANNEL:
        log_reason = reason
        if notes is not None:
            log_reason += " | " + notes
        if expires is None:
            log_exp = messages["fwarn_log_add_noexpiry"]
        else:
            log_exp = messages["fwarn_log_add_expiry"].format(expires)
        log_msg = messages["fwarn_log_add"].format(warn_id, target, wrapper.source, log_reason, args.points, log_exp)
        channels.get(var.LOG_CHANNEL).send(log_msg, prefix=var.LOG_PREFIX)

def fwarn_del(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["fwarn_del_syntax"])
        return

    warning = db.get_warning(args.id)
    if not warning:
        wrapper.reply(messages["fwarn_invalid_warning"])
        return

    warning["deleted_by"] = wrapper.source
    db.del_warning(args.id, wrapper.source.account)
    db.init_vars()
    wrapper.reply(messages["fwarn_done"])

    if var.LOG_CHANNEL:
        msg = messages["fwarn_log_del"].format(**warning)
        channels.get(var.LOG_CHANNEL).send(msg, prefix=var.LOG_PREFIX)

def fwarn_help(var, wrapper, args):
    if args.command in _fa:
        wrapper.reply(messages["fwarn_add_syntax"])
    elif args.command in _fd:
        wrapper.reply(messages["fwarn_del_syntax"])
    elif args.command in _fh:
        wrapper.reply(messages["fwarn_help_syntax"])
    elif args.command in _fs:
        wrapper.reply(messages["fwarn_set_syntax"])
    elif args.command in _fv:
        wrapper.reply(messages["fwarn_view_syntax"])
    else:
        wrapper.reply(messages["fwarn_usage"])

def fwarn_list(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["fwarn_list_syntax"])
        return

    if args.account or args.nick == "*":
        acc = args.nick
    else:
        m = users.complete_match(args.nick)
        if m:
            acc = m.get().account
        else:
            acc = args.nick

    if not acc:
        wrapper.reply(messages["fwarn_nick_invalid"].format(args.nick))
        return

    if acc == "*":
        warnings = db.list_all_warnings(list_all=args.all, skip=(args.page - 1) * 10, show=11)
    else:
        warnings = db.list_warnings(acc, expired=args.all, deleted=args.all, skip=(args.page - 1) * 10, show=11)
        points = db.get_warning_points(acc)
        wrapper.pm(messages["fwarn_list_header"].format(acc, points))

    for i, warning in enumerate(warnings):
        if i == 10:
            parts = []
            if args.all:
                parts.append(_wall[0])
            parts.append(acc)
            parts.append(str(args.page + 1))
            wrapper.pm(messages["warn_list_footer"].format("fwarn", parts))
            break
        wrapper.pm(messages["fwarn_list"].format(**warning))

    if not warnings:
        wrapper.pm(messages["fwarn_list_empty"])

def fwarn_set(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["fwarn_set_syntax"])
        return

    warning = db.get_warning(args.id)
    if not warning:
        wrapper.reply(messages["fwarn_invalid_warning"])
        return

    if args.expires is not None:
        try:
            expires = _parse_expires(args.expires, warning["issued"])
        except ValueError:
            wrapper.reply(messages["fwarn_expiry_invalid"])
            return
    else:
        expires = warning["expires"]

    if args.reason is not None:
        reason = " ".join(args.reason).strip()
        if not reason:
            wrapper.reply(messages["fwarn_reason_invalid"])
            return
    else:
        # maintain existing reason if none was specified
        reason = warning["reason"]

    if args.notes is not None:
        notes = " ".join(args.notes).strip()
        if not notes:
            # empty notes unsets them
            notes = None
    else:
        # maintain existing notes if none were specified
        notes = warning["notes"]

    db.set_warning(args.id, expires, reason, notes)
    wrapper.reply(messages["fwarn_done"])

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
        warning["changed_by"] = wrapper.source
        warning["changes"] = changes
        if changes:
            log_msg = messages["fwarn_log_set"].format(**warning)
            channels.get(var.LOG_CHANNEL).send(log_msg, prefix=var.LOG_PREFIX)

def fwarn_view(var, wrapper, args):
    if args.help:
        wrapper.reply(messages["fwarn_view_syntax"])
        return

    warning = db.get_warning(args.id)
    if warning is None:
        wrapper.reply(messages["fwarn_invalid_warning"])
        return

    wrapper.pm(messages["fwarn_view_header"].format(**warning))
    reason = warning["reason"]
    if warning["notes"] is not None:
        reason += " | " + warning["notes"]
    wrapper.pm(reason)
    if not warning["ack"]:
        wrapper.pm(messages["fwarn_view_ack"])

    sanctions = []
    if warning["sanctions"]:
        if "stasis" in warning["sanctions"]:
            sanctions.append(messages["warn_view_stasis"].format(warning["sanctions"]["stasis"]))
        if "deny" in warning["sanctions"]:
            sanctions.append(messages["warn_view_deny"].format(warning["sanctions"]["deny"]))
        if "tempban" in warning["sanctions"]:
            sanctions.append(messages["warn_view_tempban"].format(warning["sanctions"]["tempban"]))
    if sanctions:
        wrapper.pm(messages["warn_view_sanctions"].format(sanctions))

warn_parser = LineParser(prog="warn")
warn_subparsers = warn_parser.add_subparsers()
_waccount = messages.raw("_commands", "warn opt account") # type: List[str]
_wall = messages.raw("_commands", "warn opt all") # type: List[str]
_wban = messages.raw("_commands", "warn opt ban") # type: List[str]
_wdeny = messages.raw("_commands", "warn opt deny") # type: List[str]
_wexpires = messages.raw("_commands", "warn opt expires") # type: List[str]
_whelp = messages.raw("_commands", "warn opt help") # type: List[str]
_wnotes = messages.raw("_commands", "warn opt notes") # type: List[str]
_wreason = messages.raw("_commands", "warn opt reason") # type: List[str]
_wstasis = messages.raw("_commands", "warn opt stasis") # type: List[str]

_wl = messages.raw("_commands", "warn list") # type: List[str]
_warn_list = warn_subparsers.add_parser(_wl[0], aliases=_wl[1:])
_warn_list.add_argument(*_wall, dest="all", action="store_true")
_warn_list.add_argument(*_whelp, dest="help", action="help")
_warn_list.add_argument("page", type=int, nargs="?", default=1)
_warn_list.set_defaults(func=warn_list)

_wv = messages.raw("_commands", "warn view") # type: List[str]
_warn_view = warn_subparsers.add_parser(_wv[0], aliases=_wv[1:])
_warn_view.add_argument(*_whelp, dest="help", action="help")
_warn_view.add_argument("id", type=int)
_warn_view.set_defaults(func=warn_view)

_wa = messages.raw("_commands", "warn ack") # type: List[str]
_warn_ack = warn_subparsers.add_parser(_wa[0], aliases=_wa[1:])
_warn_ack.add_argument(*_whelp, dest="help", action="help")
_warn_ack.add_argument("id", type=int)
_warn_ack.set_defaults(func=warn_ack)

_wh = messages.raw("_commands", "warn help") # type: List[str]
_warn_help = warn_subparsers.add_parser(_wh[0], aliases=_wh[1:])
_warn_help.add_argument("command", nargs="?", default="help")
_warn_help.set_defaults(func=warn_help)

fwarn_parser = LineParser(prog="fwarn")
fwarn_subparsers = fwarn_parser.add_subparsers()

_fa = messages.raw("_commands", "warn add") # type: List[str]
_fwarn_add = fwarn_subparsers.add_parser(_fa[0], aliases=_fa[1:])
_fwarn_add.add_argument(*_whelp, dest="help", action="help")
_fwarn_add.add_argument(*_waccount, dest="account", action="store_true")
_fwarn_add.add_argument(*_wban, dest="ban")
_fwarn_add.add_argument(*_wdeny, dest="deny", action="append")
_fwarn_add.add_argument(*_wexpires, dest="expires", default=var.DEFAULT_EXPIRY)
_fwarn_add.add_argument(*_wnotes, dest="notes", nargs="*")
_fwarn_add.add_argument(*_wstasis, dest="stasis", type=int)
_fwarn_add.add_argument("nick")
_fwarn_add.add_argument("points", type=int)
_fwarn_add.add_argument("reason", nargs="+")
_fwarn_add.set_defaults(func=fwarn_add)

_fd = messages.raw("_commands", "warn del") # type: List[str]
_fwarn_del = fwarn_subparsers.add_parser(_fd[0], aliases=_fd[1:])
_fwarn_del.add_argument(*_whelp, dest="help", action="help")
_fwarn_del.add_argument("id", type=int)
_fwarn_del.set_defaults(func=fwarn_del)

_fs = messages.raw("_commands", "warn set") # type: List[str]
_fwarn_set = fwarn_subparsers.add_parser(_fs[0], aliases=_fs[1:])
_fwarn_set.add_argument(*_whelp, dest="help", action="help")
_fwarn_set.add_argument(*_wexpires, dest="expires")
_fwarn_set.add_argument(*_wreason, dest="reason", nargs="*")
_fwarn_set.add_argument(*_wnotes, dest="notes", nargs="*")
_fwarn_set.add_argument("id", type=int)
_fwarn_set.set_defaults(func=fwarn_set)

_fv = messages.raw("_commands", "warn view") # type: List[str]
_fwarn_view = fwarn_subparsers.add_parser(_fv[0], aliases=_fv[1:])
_fwarn_view.add_argument(*_whelp, dest="help", action="help")
_fwarn_view.add_argument("id", type=int)
_fwarn_view.set_defaults(func=fwarn_view)

_fl = messages.raw("_commands", "warn list") # type: List[str]
_fwarn_list = fwarn_subparsers.add_parser(_fl[0], aliases=_fl[1:])
_fwarn_list.add_argument(*_whelp, dest="help", action="help")
_fwarn_list.add_argument(*_waccount, dest="account", action="store_true")
_fwarn_list.add_argument(*_wall, dest="all", action="store_true")
_fwarn_list.add_argument("nick")
_fwarn_list.add_argument("page", type=int, nargs="?", default=1)
_fwarn_list.set_defaults(func=fwarn_list)

_fh = messages.raw("_commands", "warn help") # type: List[str]
_fwarn_help = fwarn_subparsers.add_parser(_fh[0], aliases=_fh[1:])
_fwarn_help.add_argument("command", nargs="?", default="help")
_fwarn_help.set_defaults(func=fwarn_help)

@command("warn", pm=True)
def warn(var, wrapper, message):
    """View and acknowledge your warnings."""
    # !warn list [-all] [page] - lists all active warnings, or all warnings if all passed
    # !warn view <id> - views details on warning id
    # !warn ack <id> - acknowledges warning id
    # Default if only !warn is given is to do !warn list.
    if not message:
        message = _wl[0]

    params = re.split(" +", message)
    params = [p for p in params if p]
    try:
        args = warn_parser.parse_args(params)
        args.func(var, wrapper, args)
    except LineParseError as e:
        if botconfig.DEBUG_MODE:
            # this isn't translated so debug mode only for now?
            wrapper.reply(e.message)
        try:
            wrapper.reply(messages[e.parser.prog.replace(" ", "_") + "_syntax"])
        except KeyError:
            wrapper.reply(messages["warn_usage"])

@command("fwarn", flag="F", pm=True)
def fwarn(var, wrapper, message):
    """Issues a warning to someone or views warnings."""
    # !fwarn list [-all] [-account] [nick] [page]
    # -all => Shows all warnings, if omitted only shows active (non-expired and non-deleted) ones.
    # -account => Specifies nick is an account name. If not specified, the nick must be online
    # nick => nick to view warnings for. If "*", show all warnings on the bot
    # !fwarn view <id> - views details on warning id
    # !fwarn del <id> - deletes warning id
    # !fwarn set <id> [-expires expiry] [-reason reason] [-notes notes]
    # !fwarn add [-account] <nick> <points> [-expires expiry] [sanctions] <reason> [-notes notes]
    # e.g. !fwarn add lykos 1 -expires 30d -deny goat -deny gstats -stasis 5 Spamming -notes I secretly just hate him
    # nick => nick to warn. Use -account to specify this is an account name instead of a nick
    # points => Warning points, must be at least 0
    # -account => nick is an account, not a nick. If not specified, the nick must be online
    # -expires => Expiration time, must be suffixed with d (days), h (hours), or m (minutes)
    # -deny => Denies access to the specified command
    # -stasis => Adds the amount of stasis, must be above 0
    # -tempban => Temporarily bans the user for either a period of time or until warning points expire
    # reason => Reason, required
    # -notes => Secret notes, not shown to the user (only shown if viewing the warning in PM)
    if not message:
        message = _fh[0]

    params = re.split(" +", message)
    params = [p for p in params if p]
    try:
        args = fwarn_parser.parse_args(params)
        args.func(var, wrapper, args)
    except WantsHelp as e:
        args = e.namespace
        args.func(var, wrapper, args)
    except LineParseError as e:
        if botconfig.DEBUG_MODE:
            # this isn't translated so debug mode only for now?
            wrapper.reply(e.message)
        try:
            wrapper.reply(messages[e.parser.prog.replace(" ", "_") + "_syntax"])
        except KeyError:
            wrapper.reply(messages["fwarn_usage"])
