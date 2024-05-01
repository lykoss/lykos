# Copyright (c) 2011, Jimmy Cao All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.  Redistributions in binary
# form must reproduce the above copyright notice, this list of conditions and
# the following disclaimer in the documentation and/or other materials provided
# with the distribution.  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS
# AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING,
# BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER
# OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import annotations

import itertools
import json
import logging
import os
import random
import re
import signal
import socket
import subprocess
import sys
import urllib.request
import urllib.error

from collections import Counter
from datetime import datetime
from typing import Optional

import src
from src import db, config, locks, dispatcher, channels, users, hooks, handler, trans, reaper, context, relay, votes
from src.channels import Channel
from src.users import User

from src.events import Event, EventListener, event_listener
from src.transport.irc import get_ircd
from src.decorators import command, hook, COMMANDS
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState, PregameState
from src.gamemodes import GameMode
from src.messages import messages, LocalMode
from src.warnings import expire_tempbans
from src.context import IRCContext
from src.status import add_dying, kill_players
from src.votes import chk_decision
from src.trans import chk_win, chk_nightdone, reset, stop_game
from src.cats import Hidden

from src.functions import (
    get_players, get_all_players, get_participants,
    get_main_role, get_reveal_role,
    match_role, match_mode
   )

# dummy line just to make the src import not unused; having src in scope is useful for !eval and !exec
assert src is not None

def connect_callback():
    db.init_vars()
    SIGUSR1 = getattr(signal, "SIGUSR1", None)
    SIGUSR2 = getattr(signal, "SIGUSR2", None)

    def sighandler(signum, frame):
        wrapper = dispatcher.MessageDispatcher(users.FakeUser.from_nick("<console>"), channels.Main)
        if signum == signal.SIGINT:
            # Exit immediately if Ctrl-C is pressed twice
            signal.signal(signal.SIGINT, signal.SIG_DFL)

        if signum in (signal.SIGINT, signal.SIGTERM):
            forced_exit.func(wrapper, "")
        elif signum == SIGUSR1:
            restart_program.func(wrapper, "")
        elif signum == SIGUSR2:
            logging.getLogger("general").info("Scheduling aftergame restart")
            aftergame.func(wrapper, "frestart")

    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)

    if SIGUSR1:
        signal.signal(SIGUSR1, sighandler)

    if SIGUSR2:
        signal.signal(SIGUSR2, sighandler)

    def who_end(event, request):
        if request is channels.Main:
            # Devoice all on connect
            mode = hooks.Features["PREFIX"]["+"]
            pending = []
            for user in channels.Main.modes.get(mode, ()):
                pending.append(("-" + mode, user))
            accumulator.send(pending)
            next(accumulator, None)

            # Expire tempbans
            expire_tempbans()

            players = db.get_pre_restart_state()
            if players:
                channels.Main.send(*players, first="PING! ")
                channels.Main.send(messages["game_restart_cancel"])

            reset(channels.Main.game_state)

            who_end_listener.remove("who_end")

    def end_listmode(event, chan: Channel, mode: str):
        if chan is channels.Main and mode == get_ircd().quiet_mode:
            pending = []
            for quiet in chan.modes.get(mode, ()):
                if re.search(r"^{0}.+!\*@\*$".format(get_ircd().quiet_prefix), quiet):
                    pending.append(("-" + mode, quiet))
            accumulator.send(pending)
            next(accumulator, None)

            end_listmode_listener.remove("end_listmode")

    def mode_change(event, actor, target):
        if target is channels.Main: # we may or may not be opped; assume we are
            accumulator.send(("-m",))
            next(accumulator, None)

            mode_change_listener.remove("mode_change")

    who_end_listener = EventListener(who_end)
    who_end_listener.install("who_end")
    end_listmode_listener = EventListener(end_listmode)
    end_listmode_listener.install("end_listmode")
    mode_change_listener = EventListener(mode_change)
    mode_change_listener.install("mode_change")

    def accumulate_cmodes(count):
        modes = []
        for i in range(count):
            item = yield
            modes.extend(item)
            yield i

        if modes:
            channels.Main.mode(*modes)

    accumulator = accumulate_cmodes(3)
    accumulator.send(None)

@command("sync", flag="m", pm=True)
def fsync(wrapper: MessageDispatcher, message: str):
    """Makes the bot apply the currently appropriate channel modes."""
    sync_modes()

@event_listener("sync_modes")
def on_sync_modes(evt):
    sync_modes()

def sync_modes():
    game_state = channels.Main.game_state
    voices = [None]
    mode = hooks.Features["PREFIX"]["+"]
    pl = get_players(game_state) if game_state else []

    for user in channels.Main.users:
        if game_state and not config.Main.get("gameplay.nightchat") and game_state.current_phase == "night":
            if mode in user.channels[channels.Main]:
                voices.append(("-" + mode, user))
        elif user in pl and mode not in user.channels[channels.Main]:
            voices.append(("+" + mode, user))
        elif user not in pl and mode in user.channels[channels.Main]:
            voices.append(("-" + mode, user))

    if game_state and game_state.in_game:
        voices[0] = "+m"
    else:
        voices[0] = "-m"

    channels.Main.mode(*voices)

@command("refreshdb", flag="m", pm=True)
def refreshdb(wrapper: MessageDispatcher, message: str):
    """Updates our tracking vars to the current db state."""
    db.expire_stasis()
    db.init_vars()
    expire_tempbans()
    wrapper.reply("Done.")

@command("fdie", flag="F", pm=True)
def forced_exit(wrapper: MessageDispatcher, message: str):
    """Forces the bot to close."""

    var = wrapper.game_state

    args = message.split()

    # Force in debug mode by default
    force = config.Main.get("debug.enabled")

    if args and args[0] == "-dirty":
        # use as a last resort
        os.abort()
    elif args and args[0] == "-force":
        force = True
        message = " ".join(args[1:])

    if var:
        if var.current_phase == "join" or force or wrapper.source.nick == "<console>":
            stop_game(var, log=False)
        elif var.in_game:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(what="stop", cmd="fdie"))
            return

    msg = "{0} quit from {1}"

    if message.strip():
        msg += " ({2})"

    hooks.quit(wrapper, msg.format("Scheduled" if forced_exit.aftergame else "Forced",
               wrapper.source, message.strip()))

def _restart_program(mode=None):
    logging.getLogger("general").info("RESTARTING")

    python = sys.executable

    # FIXME: should maintain the same --config option
    args = []
    if (mode != "normal" and config.Main.get("debug.enabled")) or mode == "debug":
        args.append("--debug")
    os.execl(python, python, sys.argv[0], *args)

@command("frestart", flag="D", pm=True)
def restart_program(wrapper: MessageDispatcher, message: str):
    """Restarts the bot."""

    var = wrapper.game_state

    args = message.split()

    # Force in debug mode by default
    force = config.Main.get("debug.enabled")

    if args and args[0] == "-force":
        force = True
        message = " ".join(args[1:])

    if var:
        if not var.in_game or force:
            db.set_pre_restart_state(p.nick for p in get_players(var))
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(what="restart", cmd="frestart"))
            return

    msg = "{0} restart from {1}".format(
        "Scheduled" if restart_program.aftergame else "Forced", wrapper.source)

    message = message.strip()
    mode = None

    if message:
        args = message.split()
        first_arg = args[0].lower()

        if first_arg.endswith("mode") and first_arg != "mode":
            mode = first_arg.replace("mode", "")

            valid_modes = ("normal", "debug")

            if mode not in valid_modes:
                wrapper.pm(messages["invalid_restart_mode"].format(mode, valid_modes))
                return

            msg += " in {0} mode".format(mode)
            message = " ".join(args[1:])

    if message:
        msg += " ({0})".format(message.strip())

    hooks.quit(wrapper, msg.format(wrapper.source, message.strip()))

    def restart_buffer(evt, user, reason):
        # restart the bot once our quit message goes though to ensure entire IRC queue is sent
        if user is users.Bot:
            _restart_program(mode)

    EventListener(restart_buffer).install("server_quit")

    # This is checked in the on_error handler. Some IRCds, such as InspIRCd, don't send the bot
    # its own QUIT message, so we need to use ERROR. Ideally, we shouldn't even need the above
    # handler now, but I'm keeping it for now just in case.
    restart_program.restarting = True

restart_program.restarting = False

@command("ping", pm=True)
def pinger(wrapper: MessageDispatcher, message: str):
    """Check if you or the bot is still connected."""
    wrapper.reply(messages["ping"].format(nick=wrapper.source, bot_nick=users.Bot))

@command("notice", pm=True)
def mark_prefer_notice(wrapper: MessageDispatcher, message: str):
    """Makes the bot NOTICE you for every interaction."""
    if wrapper.private and message:
        # Ignore if called in PM with parameters, likely a message to wolfchat
        # and not an intentional invocation of this command
        return

    temp = wrapper.source.lower()

    account = temp.account

    if not account:
        wrapper.pm(messages["not_logged_in"])
        return

    notice = wrapper.source.prefers_notice()
    action, toggle = (db.PREFER_NOTICE.discard, "off") if notice else (db.PREFER_NOTICE.add, "on")

    action(account)
    db.toggle_notice(account)
    # message keys used: "notice_on", "notice_off"
    wrapper.pm(messages["notice_" + toggle])

@command("swap", pm=True, phases=("join", "day", "night"))
def replace(wrapper: MessageDispatcher, message: str):
    """Swap out a player logged in to your account."""
    if wrapper.source not in channels.Main.users:
        wrapper.pm(messages["invalid_channel"].format(channels.Main))
        return

    var = wrapper.game_state

    pl = get_players(var)
    if wrapper.source in pl:
        wrapper.pm(messages["you_already_playing"])
        return

    if not wrapper.source.account:
        wrapper.pm(messages["not_logged_in"])
        return

    participants = get_participants(var)
    target: Optional[User] = None

    for user in var.players:
        if context.equals(user.account, wrapper.source.account):
            if user is wrapper.source or user not in participants:
                continue
            elif target is None:
                target = user
            else:
                wrapper.pm(messages["swap_notice"])
                return

    if target is None:
        wrapper.pm(messages["account_not_playing"])
        return
    elif target is not wrapper.source:
        target.swap(wrapper.source)
        if var.in_game:
            reaper.return_to_village(var, wrapper.source, show_message=False)

        cmodes = []

        if (config.Main.get("gameplay.nightchat") or var.current_phase != "night") and target in pl:
            cmodes += [("-v", target), ("+v", wrapper.source)]

        toggle_modes = config.Main.get("transports[0].channels.main.auto_mode_toggle", ())
        for mode in set(toggle_modes) & wrapper.source.channels[channels.Main]: # user.channels is a set of current modes
            cmodes.append(("-" + mode, wrapper.source))
            channels.Main.old_modes[wrapper.source].add(mode)

        for mode in channels.Main.old_modes[target]:
            cmodes.append(("+" + mode, target))

        channels.Main.mode(*cmodes)

        channels.Main.send(messages["player_swap"].format(wrapper.source, target))
        if var.in_game:
            myrole.func(wrapper, "")

@event_listener("chan_kick")
def kicked_modes(evt, chan: Channel, actor, target, reason):
    if target is users.Bot and chan is channels.Main:
        chan.join()
    channels.Main.old_modes.pop(target, None)

@event_listener("chan_part")
def parted_modes(evt, chan: Channel, user, reason):
    if user is users.Bot and chan is channels.Main:
        chan.join()
    channels.Main.old_modes.pop(user, None)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if not var.in_game:
        return

    # update the role stats
    # Event priorities:
    # 1 = Expanding the possible set (e.g. traitor would add themselves if nickrole is villager)
    # 3 = Removing from the possible set (e.g. can't be traitor if was a night kill and only wolves could kill at night),
    # 5 = Setting known_role to True if the role is actually known for sure publically (e.g. revealing totem)
    # 2 and 4 are not used by included roles, but may be useful expansion points for custom roles to modify stats
    event = Event("update_stats", {"possible": {evt.params.main_role, evt.params.reveal_role}, "known_role": False},
                  killer_role=evt.params.killer_role,
                  reason=evt.params.reason)
    event.dispatch(var, player, evt.params.main_role, evt.params.reveal_role, all_roles)
    # Given the set of possible roles this nick could be (or its actual role if known_role is True),
    # figure out the set of roles that need deducting from their counts in the role stats
    if event.data["known_role"]:
        # we somehow know the exact role that died (for example, we know traitor died even though they revealed as villager)
        # as a result, deduct only them
        possible = {evt.params.main_role}
    else:
        possible = set(event.data["possible"])
    newstats = set()
    # For every possible role this person is, try to deduct 1 from that role's count in our stat sets
    # if a stat set doesn't contain the role, then that would lead to an impossible condition and therefore
    # that set is not added to newstats to indicate that set is no longer possible
    for p in possible:
        for rs in var.get_role_stats():
            d = Counter(dict(rs))
            if p in d and d[p] >= 1:
                d[p] -= 1
                newstats.add(frozenset(d.items()))
    var.set_role_stats(newstats)

# FIXME: get rid of the priority once we move state transitions into the main event loop instead of having it here
@event_listener("kill_players", priority=10)
def on_kill_players(evt: Event, var: GameState, players: set[User]):
    cmode = []
    deadchat = []
    game_ending = False

    for player in players:
        if not player.is_fake:
            if var.current_phase != "night" or config.Main.get("gameplay.nightchat"):
                cmode.append(("-v", player.nick))
            if var.in_game and config.Main.get("gameplay.quiet_dead_players"):
                # Died during the game, so quiet!
                ircd = get_ircd()
                if ircd.supports_quiet():
                    cmode.append((f"+{ircd.quiet_mode}", f"{ircd.quiet_prefix}{player.nick}!*@*"))
            if var.current_phase == "join":
                for mode in channels.Main.old_modes[player]:
                    cmode.append(("+" + mode, player.nick))
                del channels.Main.old_modes[player]
            lplayer = player.lower()
            if lplayer.account not in db.DEADCHAT_PREFS:
                deadchat.append(player)

    # attempt to devoice all dead players
    if cmode:
        channels.Main.mode(*cmode)

    if not evt.params.end_game:
        relay.join_deadchat(var, *deadchat)
        return

    # see if we need to end the game or transition phases
    # FIXME: make state transitions part of the overall event loop
    game_ending = chk_win(var)

    if not game_ending:
        # if game isn't about to end, join people to deadchat
        relay.join_deadchat(var, *deadchat)

        if not var.in_phase_transition:
            if var.current_phase == "day":
                # ensure we only induce lynch during actual daytime
                chk_decision(var)
            elif var.current_phase == "night":
                # ensure we only try to end night during actual nighttime
                chk_nightdone(var)
    else:
        # HACK: notify kill_players that game is ending so it can pass it to its caller
        evt.prevent_default = True

@event_listener("chan_join", priority=1)
def on_join(evt, chan, user: User):
    if user is users.Bot:
        logging.getLogger("transport.{}".format(config.Main.get("transports[0].name"))).info("Joined {0}".format(chan))
    if chan is not channels.Main:
        return
    user.update_account_data("<chan_join>", lambda new_user: reaper.return_to_village(channels.Main.game_state, new_user, show_message=True))

@event_listener("account_change")
def account_change(evt, user: User, old_account): # FIXME: This uses var
    if user not in channels.Main.users or not channels.Main.game_state:
        return # We only care about game-related changes in this function

    var = channels.Main.game_state

    pl = get_participants(var)
    if user in pl and user.account not in trans.ORIGINAL_ACCOUNTS.values() and user not in reaper.DISCONNECTED:
        leave(var, "account", user) # this also notifies the user to change their account back
        if var.current_phase != "join":
            channels.Main.mode(["-v", user.nick])
    elif (user not in pl or user in reaper.DISCONNECTED) and user.account in trans.ORIGINAL_ACCOUNTS.values():
        # if they were gone, maybe mark them as back
        reaper.return_to_village(var, user, show_message=True)

@event_listener("chan_part")
def left_channel(evt, chan: Channel, user, reason): # FIXME: This uses var
    leave(chan.game_state, "part", user, chan)

@event_listener("chan_kick") # FIXME: This uses var
def channel_kicked(evt, chan: Channel, actor, user, reason):
    leave(chan.game_state, "kick", user, chan)

@event_listener("server_quit")
def quit_server(evt, user, reason): # FIXME: This uses var
    leave(channels.Main.game_state, "quit", user, reason)

def leave(var: Optional[GameState | PregameState], what: str, user: User, why=None):
    if what in ("part", "kick") and why is not channels.Main:
        return
    if var is None:
        return

    ps = get_players(var)
    # Only mark living players as disconnected, unless they were kicked
    if (user in ps or what == "kick") and var.in_game:
        reaper.DCED_LOSERS.add(user)

    # leaving the game channel means you leave deadchat
    if user in relay.DEADCHAT_PLAYERS:
        relay.leave_deadchat(var, user)

    if user not in ps or user in reaper.DISCONNECTED:
        return

    # If we got that far, the player was in the game. This variable tracks whether or not we want to kill them off.
    killplayer = True

    population = ""

    if var.current_phase == "join":
        lpl = len(ps) - 1
        if lpl < config.Main.get("gameplay.player_limits.minimum"):
            with locks.join_timer:
                from src.pregame import START_VOTES
                START_VOTES.clear()

        if lpl <= 0:
            population = " " + messages["no_players_remaining"]
        else:
            population = " " + messages["new_player_count"].format(lpl)

    reveal = ""
    if not var.in_game or var.role_reveal not in ("on", "team"):
        reveal = "_no_reveal"

    grace_times = {"leave": 0, "part": 0, "quit": 0, "account": 0}
    if config.Main.get("reaper.part.enabled"):
        grace_times["part"] = config.Main.get("reaper.part.grace")
    if config.Main.get("reaper.quit.enabled"):
        grace_times["quit"] = config.Main.get("reaper.quit.grace")
    if config.Main.get("reaper.account.enabled"):
        grace_times["account"] = config.Main.get("reaper.account.grace")

    reason = what
    if reason == "kick":
        reason = "leave"

    if what == "kick" or grace_times[reason] <= 0 or var.current_phase == "join":
        # possible message keys (for easy grep):
        # "quit_death", "quit_death_no_reveal", "leave_death", "leave_death_no_reveal", "account_death", "account_death_no_reveal"
        msg = messages["{0}_death{1}".format(reason, reveal)]
    else:
        if reason != "quit":
            # message keys: "part_grace_time_notice", "account_grace_time_notice"
            # No message is sent for quit because the user won't be online to receive it...
            user.send(messages["{0}_grace_time_notice".format(reason)].format(grace_times[reason], chan=channels.Main))
        msg = messages["player_missing"]
        population = ""
        killplayer = False

    role = ""
    if var.in_game:
        role = get_reveal_role(var, user)

    channels.Main.send(msg.format(user, role) + population)
    relay.WOLFCHAT_SPECTATE.discard(user)
    relay.DEADCHAT_SPECTATE.discard(user)
    relay.leave_deadchat(var, user)

    if killplayer:
        add_dying(var, user, "bot", what, death_triggers=False)
        kill_players(var)
    else:
        reaper.DISCONNECTED[user] = (datetime.now(), what)

@hook("error")
def on_error(cli, pfx, msg: str):
    if restart_program.restarting or msg.lower().endswith("(excess flood)"):
        _restart_program()
    elif msg.lower().startswith("closing link:"):
        sys.exit()

@command("ftemplate", flag="F", pm=True)
def ftemplate(wrapper: MessageDispatcher, message: str):
    params = re.split(" +", message)
    var = wrapper.game_state

    if params[0] == "":
        # display a list of all templates
        tpls = db.get_templates()
        if not tpls:
            wrapper.reply(messages["no_templates"])
        else:
            tpls = ["{0} (+{1})".format(name, "".join(sorted(flags))) for name, flags in tpls]
            wrapper.reply(*tpls, sep=", ")
    elif len(params) == 1:
        wrapper.reply(messages["not_enough_parameters"])
    else:
        name = params[0].upper()
        flags = params[1]
        tid, cur_flags = db.get_template(name)
        cur_flags = set(cur_flags)

        if flags[0] != "+" and flags[0] != "-":
            # flags is a template name
            tpl_name = flags.upper()
            tpl_id, tpl_flags = db.get_template(tpl_name)
            if tpl_id is None:
                wrapper.reply(messages["template_not_found"].format(tpl_name))
                return
            tpl_flags = "".join(sorted(tpl_flags))
            db.update_template(name, tpl_flags)
            wrapper.reply(messages["template_set"].format(name, tpl_flags))
        else:
            adding = True
            for flag in flags:
                if flag == "+":
                    adding = True
                    continue
                elif flag == "-":
                    adding = False
                    continue
                elif flag == "*":
                    if adding:
                        cur_flags = cur_flags | (db.ALL_FLAGS.keys() - {"F"})
                    else:
                        cur_flags = set()
                    continue
                elif flag not in db.ALL_FLAGS:
                    wrapper.reply(messages["invalid_flag"].format(flag, "".join(sorted(db.ALL_FLAGS))))
                    return
                elif adding:
                    cur_flags.add(flag)
                else:
                    cur_flags.discard(flag)
            if cur_flags:
                tpl_flags = "".join(sorted(cur_flags))
                db.update_template(name, tpl_flags)
                wrapper.reply(messages["template_set"].format(name, tpl_flags))
            elif tid is None:
                wrapper.reply(messages["template_not_found"].format(name))
            else:
                db.delete_template(name)
                wrapper.reply(messages["template_deleted"].format(name))

        # re-init db.FLAGS since it may have changed
        db.init_vars()

@command("fflags", flag="F", pm=True)
def fflags(wrapper: MessageDispatcher, message: str):
    params = re.split(" +", message)
    params = [p for p in params if p]

    var = wrapper.game_state

    _fa = messages.raw("_commands", "warn opt account")
    _fh = messages.raw("_commands", "warn opt help")
    if not params or params[0] in _fh:
        wrapper.reply(messages["fflags_usage"])
        return

    account = False
    if params[0] in _fa:
        params.pop(0)
        account = True

    if not params:
        wrapper.reply(messages["fflags_usage"])
        return

    nick = params.pop(0)
    flags = None
    if params:
        flags = params.pop(0)

    if nick == "*":
        # display a list of all access
        parts = []
        for acc, flags in db.FLAGS.items():
            if not flags:
                continue
            parts.append("{0} (+{1})".format(acc, "".join(sorted(flags))))
        if not parts:
            wrapper.reply(messages["no_access"])
        else:
            wrapper.reply(*parts, sep=", ")
        return

    if account:
        acc = nick
    else:
        m = users.complete_match(nick)
        if m:
            acc = m.get().account
            if not acc:
                wrapper.reply(messages["account_not_logged_in"].format(m))
                return
        else:
            acc = nick

    # db.FLAGS stores lowercased accounts, ensure acc is lowercased as well
    from src.context import lower
    lacc = lower(acc)

    if not flags:
        # display access for the given user
        if not db.FLAGS[lacc]:
            wrapper.reply(messages["no_access_account"].format(acc))
        else:
            wrapper.reply(messages["access_account"].format(acc, "".join(sorted(db.FLAGS[lacc]))))
        return

    cur_flags = set(db.FLAGS[lacc])
    if flags[0] != "+" and flags[0] != "-":
        # flags is a template name
        tpl_name = flags.upper()
        tpl_id, tpl_flags = db.get_template(tpl_name)
        if tpl_id is None:
            wrapper.reply(messages["template_not_found"].format(tpl_name))
            return
        tpl_flags = "".join(sorted(tpl_flags))
        db.set_access(acc, tid=tpl_id)
        wrapper.reply(messages["access_set_account"].format(acc, tpl_flags))
    else:
        adding = True
        for flag in flags:
            if flag == "+":
                adding = True
                continue
            elif flag == "-":
                adding = False
                continue
            elif flag == "*":
                if adding:
                    cur_flags = cur_flags | (db.ALL_FLAGS.keys() - {"F"})
                else:
                    cur_flags = set()
                continue
            elif flag not in db.ALL_FLAGS:
                wrapper.reply(messages["invalid_flag"].format(flag, "".join(sorted(db.ALL_FLAGS))))
                return
            elif adding:
                cur_flags.add(flag)
            else:
                cur_flags.discard(flag)
        if cur_flags:
            flags = "".join(sorted(cur_flags))
            db.set_access(acc, flags=flags)
            wrapper.reply(messages["access_set_account"].format(acc, flags))
        else:
            db.set_access(acc, flags=None)
            wrapper.reply(messages["access_deleted_account"].format(acc))

        # re-init db.FLAGS since it may have changed
        db.init_vars()

@command("rules", pm=True)
def show_rules(wrapper: MessageDispatcher, message: str):
    """Displays the rules."""

    rules = config.Main.get("gameplay.rules")
    if rules:
        wrapper.reply(messages["channel_rules"].format(channels.Main, rules))
    else:
        wrapper.reply(messages["no_channel_rules"].format(channels.Main))

@command("help", pm=True)
def get_help(wrapper: MessageDispatcher, message: str):
    """Gets help."""
    commands = set()
    for name, functions in COMMANDS.items():
        if not name:
            continue
        for fn in functions:
            if not fn.flag and not fn.owner_only and name not in fn.aliases:
                commands.add(name)
                break
    admin_commands = set()
    if wrapper.source.is_admin():
        for name, functions in COMMANDS.items():
            for fn in functions:
                if fn.flag and name not in fn.aliases:
                    admin_commands.add(name)
    wrapper.pm(messages["commands_list"].format(sorted(commands)))
    if admin_commands:
        wrapper.pm(messages["admin_commands_list"].format(sorted(admin_commands)))
    wrapper.pm(messages["commands_further_help"])

def get_wiki_page(URI):
    try:
        response = urllib.request.urlopen(URI, timeout=2).read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, socket.timeout):
        return False, messages["wiki_request_timed_out"]
    if not response:
        return False, messages["wiki_open_failure"]
    parsed = json.loads(response)
    if not parsed:
        return False, messages["wiki_open_failure"]
    return True, parsed

@command("wiki", pm=True)
def wiki(wrapper: MessageDispatcher, message: str):
    """Prints information from the wiki."""

    # no arguments, just print a link to the wiki
    if not message:
        wrapper.reply("https://werewolf.chat")
        return
    rest = message.replace(" ", "_").lower()

    # Get suggestions, for autocompletion
    URI = "https://werewolf.chat/w/api.php?action=opensearch&format=json&search={0}".format(rest)
    success, suggestionjson = get_wiki_page(URI)
    if not success:
        wrapper.pm(suggestionjson)
        return

    # Parse suggested pages, take the first result
    try:
        suggestion = suggestionjson[1][0].replace(" ", "_")
    except IndexError:
        wrapper.pm(messages["wiki_no_info"])
        return

    # Fetch a page from the api, in json format
    URI = "https://werewolf.chat/w/api.php?action=query&prop=extracts&exintro=true&explaintext=true&titles={0}&redirects&format=json".format(suggestion)
    success, pagejson = get_wiki_page(URI)
    if not success:
        wrapper.pm(pagejson)
        return

    try:
        p = pagejson["query"]["pages"].popitem()[1]
        suggestion = p["title"]
        page = p["extract"]
    except (KeyError, IndexError):
        wrapper.pm(messages["wiki_no_info"])
        return

    try:
        fragment = pagejson["query"]["redirects"][0]["tofragment"]
        suggestion += "#{0}".format(fragment)
    except (KeyError, IndexError):
        pass

    # We only want the first paragraph
    if page.find("\n") >= 0:
        page = page[:page.find("\n")]

    wikilink = "https://werewolf.chat/{0}".format(suggestion.replace(" ", "_"))
    wrapper.reply(wikilink)
    if "#" not in wikilink:
        wrapper.pm(page)

@hook("invite")
def on_invite(cli, raw_nick, something, chan):
    if chan == config.Main.get("transports[0].channels.main"):
        cli.join(chan)
        return # No questions
    user = users.get(raw_nick, allow_none=True)
    if user and user.is_admin():
        cli.join(chan) # Allows the bot to be present in any channel

@command("coin", pm=False)
def coin(wrapper: MessageDispatcher, message: str):
    """It's a bad idea to base any decisions on this command."""

    wrapper.send(messages["coin_toss"].format(wrapper.source))
    rnd = random.random()
    # 59/29/12 split, 59+29=88
    if rnd < 0.59:
        coin = messages.get("coin_land", 0)
    elif rnd < 0.88:
        coin = messages.get("coin_land", 1)
    else:
        coin = messages.get("coin_land", 2)
    wrapper.send(coin.format())

@command("pony", pm=False)
def pony(wrapper: MessageDispatcher, message: str):
    """Toss a magical pony into the air and see what happens!"""

    wrapper.send(messages["pony_toss"].format(wrapper.source))
    # 59/29/7/5 split
    rnd = random.random()
    if rnd < 0.59:
        pony = messages.get("pony_land", 0)
    elif rnd < 0.88:
        pony = messages.get("pony_land", 1)
    elif rnd < 0.95:
        pony = messages.get("pony_land", 2)
    else:
        pony = messages.get("pony_land", 3)
    wrapper.send(pony.format(nick=wrapper.source))

@command("cat", pm=False)
def cat(wrapper: MessageDispatcher, message: str):
    """Toss a cat into the air and see what happens!"""
    wrapper.send(messages["cat_toss"].format(wrapper.source), messages["cat_land"].format(), sep="\n")

@command("roles", pm=True)
def list_roles(wrapper: MessageDispatcher, message: str):
    """Display which roles are in play for a specific gamemode."""
    from src.gamemodes import GAME_MODES

    var = wrapper.game_state

    lpl = len(var.players) if var else 0
    specific = 0

    pieces = re.split(" +", message.strip())
    gamemode = var.current_mode if var else None

    if not pieces[0] or pieces[0].isdigit():
        if not var or not var.in_game:
            wrapper.reply(messages["roles_need_gamemode"], prefix_nick=True)
            return
        if gamemode and not gamemode.ROLE_GUIDE:
            minp = max(GAME_MODES[gamemode.name][1], config.Main.get("gameplay.player_limits.minimum"))
            msg = " ".join((messages["roles_players"].format(lpl), messages["roles_disabled"].format(gamemode.name, minp)))
            wrapper.reply(msg, prefix_nick=True)
            return

    msg = []

    if gamemode and (not pieces[0] and lpl):
        msg.append(messages["roles_players"].format(lpl))
        if var.in_game:
            msg.append(messages["roles_gamemode"].format(gamemode.name))
            pieces[0] = str(lpl)

    if pieces[0] and not pieces[0].isdigit():
        valid = GAME_MODES.keys() - set(config.Main.get("gameplay.disable.gamemodes")) - {"roles"}
        mode = pieces.pop(0)

        matches = match_mode(mode, scope=valid, remove_spaces=True)
        if len(matches) == 0:
            wrapper.reply(messages["invalid_mode"].format(mode), prefix_nick=True)
            return
        elif len(matches) > 1:
            wrapper.reply(messages["ambiguous_mode"].format([m.local for m in matches]), prefix_nick=True)
            return

        mode = matches.get().key

        gamemode: GameMode = GAME_MODES[mode][0]()

        if not gamemode.ROLE_GUIDE:
            minp = max(GAME_MODES[mode][1], config.Main.get("gameplay.player_limits.minimum"))
            wrapper.reply(messages["roles_disabled"].format(gamemode.name, minp), prefix_nick=True)
            return

    strip = lambda x: re.sub(r"\(.*\)", "", x)
    rolecnt = Counter()
    roles = list((x, map(strip, y)) for x, y in gamemode.ROLE_GUIDE.items())
    roles.sort(key=lambda x: x[0])

    if pieces and pieces[0].isdigit():
        specific = int(pieces[0])
        new = []
        for role in itertools.chain.from_iterable([y for x, y in roles if x <= specific]):
            if role.startswith("-"):
                rolecnt[role[1:]] -= 1
                new.remove(role[1:])
            else:
                rolecnt[role] += 1
                append = "({0})".format(rolecnt[role]) if rolecnt[role] > 1 else ""
                new.append(role + append)

        if new and config.Main.get("gameplay.player_limits.minimum") <= specific <= config.Main.get("gameplay.player_limits.maximum"):
            msg.append("[{0}]".format(specific))
            msg.append(", ".join(new))
        else:
            msg.append(messages["roles_undefined"].format(specific))

    else:
        final = []

        roles_dict = {}
        for num, role_num in roles:
            roles_dict[num] = list(role_num)

        roles_dict_final = roles_dict.copy()

        for num, role_num in reversed(list(roles_dict.items())):
            if num < config.Main.get("gameplay.player_limits.minimum"):
                roles_dict_final[config.Main.get("gameplay.player_limits.minimum")] = list(role_num) + list(roles_dict_final[config.Main.get("gameplay.player_limits.maximum")])
                del roles_dict_final[num]

        for num, role_num in roles_dict_final.items():
            snum = "[{0}]".format(num)
            if num <= lpl:
                snum = "\u0002{0}\u0002".format(snum)
            final.append(snum)
            new = []
            for role in role_num:
                if role.startswith("-"):
                    if role[1:] not in role_num:
                        rolecnt[role[1:]] -= 1
                        roles = role[1:].split("/")
                        localized_roles = [messages.raw("_roles", x)[0] for x in roles]
                        new.append("-{0}".format("/".join(localized_roles)))
                else:
                    if f"-{role}" not in role_num:
                        rolecnt[role] += 1
                        append = "({0})".format(rolecnt[role]) if rolecnt[role] > 1 else ""
                        roles = role.split("/")
                        localized_roles = [messages.raw("_roles", x)[0] for x in roles]
                        new.append("/".join(localized_roles) + append)

            final.append(", ".join(new))

        msg.append(" ".join(final))

    if not msg:
        msg.append(messages["roles_undefined"].format(specific or lpl))

    wrapper.send(*msg)

@command("myrole", pm=True, phases=("day", "night"))
def myrole(wrapper: MessageDispatcher, message: str):
    """Remind you of your current role."""

    var = wrapper.game_state

    ps = get_participants(var)
    if wrapper.source not in ps:
        return

    role = get_main_role(var, wrapper.source)
    if role in Hidden:
        role = var.hidden_role

    evt = Event("myrole", {"role": role, "messages": []})
    if not evt.dispatch(var, wrapper.source):
        return
    role = evt.data["role"]

    wrapper.pm(messages["show_role"].format(role))

    for msg in evt.data["messages"]:
        wrapper.pm(msg)

@command("faftergame", flag="D", pm=True)
def aftergame(wrapper: MessageDispatcher, message: str):
    """Schedule a command to be run after the current game."""
    if not message.strip():
        wrapper.pm(messages["incorrect_syntax"])
        return

    var = wrapper.game_state

    args = re.split(" +", message)
    before, prefix, after = args.pop(0).lower().partition(config.Main.get("transports[0].user.command_prefix"))
    if not prefix: # the prefix was not in the string
        cmd = before
    elif after and not before: # message was prefixed
        cmd = after
    else: # some weird thing, e.g. "fsay!" or even "fs!ay"; we don't care about that
        return

    if cmd in COMMANDS:
        def do_action():
            for fn in COMMANDS[cmd]:
                fn.aftergame = True
                context = MessageDispatcher(wrapper.source, channels.Main if fn.chan else users.Bot)
                fn.caller(context, " ".join(args))
                fn.aftergame = False
    else:
        wrapper.pm(messages["command_not_found"])
        return

    if var is None:
        do_action()
        return

    channels.Main.send(messages["command_scheduled"].format(" ".join([cmd] + args), wrapper.source))
    trans.ENDGAME_COMMAND = do_action

def _command_disabled(wrapper: MessageDispatcher, message: str):
    wrapper.send(messages["command_disabled_admin"])

@command("flastgame", flag="D", pm=True)
def flastgame(wrapper: MessageDispatcher, message: str):
    """Disables starting or joining a game, and optionally schedules a command to run after the current game ends."""
    for cmdcls in (COMMANDS["join"] + COMMANDS["start"]):
        cmdcls.func = _command_disabled

    channels.Main.send(messages["disable_new_games"].format(wrapper.source))
    trans.ADMIN_STOPPED.append(wrapper.source)

    if message.strip():
        aftergame.func(wrapper, message)

@command("whoami", pm=True)
def whoami(wrapper: MessageDispatcher, message: str):
    if wrapper.source.account:
        wrapper.pm(messages["whoami_loggedin"].format(wrapper.source.account))
    else:
        wrapper.pm(messages["whoami_loggedout"])

@command("setdisplay", pm=True)
def setdisplay(wrapper: MessageDispatcher, message: str):
    if not wrapper.source.account:
        wrapper.pm(messages["not_logged_in"])
        return

    db.set_primary_player(wrapper.source.account)
    wrapper.reply(messages["display_name_set"].format(wrapper.source.account))

# Called from !game and !join, used to vote for a game mode
def vote_gamemode(wrapper: MessageDispatcher, gamemode, doreply): # FIXME: remove var
    from src.gamemodes import GAME_MODES
    if wrapper.game_state.current_mode is not None:
        if doreply:
            wrapper.pm(messages["admin_forced_game"])
        return

    allowed = GAME_MODES.keys() - {"roles"} - set(config.Main.get("gameplay.disable.gamemodes"))
    matches = match_mode(gamemode, scope=allowed, remove_spaces=True)
    if len(matches) == 0:
        if doreply:
            wrapper.pm(messages["invalid_mode"].format(gamemode))
        return
    elif len(matches) > 1:
        if doreply:
            wrapper.pm(messages["ambiguous_mode"].format([m.local for m in matches]))
        return

    gamemode = matches.get().key
    if votes.GAMEMODE_VOTES.get(wrapper.source) == gamemode:
        wrapper.pm(messages["already_voted_game"].format(gamemode))
    else:
        votes.GAMEMODE_VOTES[wrapper.source] = gamemode
        wrapper.send(messages["vote_game_mode"].format(wrapper.source, gamemode))

def _get_gamemodes(var):
    from src.gamemodes import GAME_MODES
    gamemodes = []
    order = {}
    for gm, (cls, min, max, chance) in GAME_MODES.items():
        if gm == "roles" or gm in config.Main.get("gameplay.disable.gamemodes"):
            continue
        order[LocalMode(gm).local] = (min, max)

    for gm in sorted(order.keys()):
        min, max = order[gm]
        if min <= len(get_players(var)) <= max:
            gm = messages["bold"].format(gm)
        gamemodes.append(gm)

    return gamemodes

@command("game", playing=True, phases=("join",))
def game(wrapper: MessageDispatcher, message: str):
    """Vote for a game mode to be picked."""
    var = wrapper.game_state
    if message:
        vote_gamemode(wrapper, message.lower().split()[0], doreply=True)
    else:
        wrapper.pm(messages["no_mode_specified"].format(_get_gamemodes(var)))

@command("games", pm=True)
def show_modes(wrapper: MessageDispatcher, message: str):
    """Show the available game modes."""
    wrapper.pm(messages["available_modes"].format(_get_gamemodes(wrapper.game_state)))

def _call_command(wrapper, command, no_out=False):
    """
    Executes a system command.

    If `no_out` is True, the command's output will not be sent to IRC,
    unless the exit code is non-zero.
    """

    child = subprocess.Popen(command.split(),
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    (out, err) = child.communicate()
    ret = child.returncode

    if not (no_out and ret == 0):
        for line in (out + err).splitlines():
            wrapper.pm(line.decode("utf-8"))

    if ret != 0:
        if ret < 0:
            cause = "signal"
            ret *= -1
        else:
            cause = "status"

        wrapper.pm(messages["process_exited"].format(command, cause, ret))

    return ret, out

def _git_pull(wrapper):
    (ret, _) = _call_command(wrapper, "git fetch")
    if ret != 0:
        return False

    (ret, out) = _call_command(wrapper, "git status -b --porcelain", no_out=True)
    if ret != 0:
        return False

    if not re.search(rb"behind \d+", out.splitlines()[0]):
        # Already up-to-date
        wrapper.pm(messages["already_up_to_date"])
        return False

    (ret, _) = _call_command(wrapper, "git pull --stat --ff-only")
    return ret == 0

@command("fpull", flag="D", pm=True)
def fpull(wrapper: MessageDispatcher, message: str):
    """Pulls from the repository to update the bot."""
    _git_pull(wrapper)

@command("update", flag="D", pm=True)
def update(wrapper: MessageDispatcher, message: str):
    """Pull from the repository and restart the bot to update it."""

    var = wrapper.game_state

    force = (message.strip() == "-force")

    if var:
        if not var.in_game or force:
            stop_game(var, log=False)
        else:
            wrapper.pm(messages["stop_bot_ingame_safeguard"].format(what="restart", cmd="update"))
            return

    if update.aftergame:
        # Display "Scheduled restart" instead of "Forced restart" when called with !faftergame
        restart_program.aftergame = True

    ret = _git_pull(wrapper)
    if ret:
        restart_program.func(wrapper, "Updating bot")

@command("fsend", owner_only=True, pm=True)
def fsend(wrapper: MessageDispatcher, message: str):
    """Send raw IRC commands to the server."""
    wrapper.source.client.send(message)

def _say(wrapper, rest, cmd, action=False):
    rest = rest.split(" ", 1)

    if len(rest) < 2:
        wrapper.pm(messages["fsend_usage"].format(cmd))
        return

    target, message = rest

    if target.startswith(tuple(hooks.Features["CHANTYPES"])):
        targ = channels.get(target, allow_none=True)
    else:
        targ = users.get(target, allow_multiple=True)
        if len(targ) == 1:
            targ = targ[0]
        else:
            targ = None

    if targ is None:
        targ = IRCContext(target, wrapper.source.client)

    if not wrapper.source.is_owner() and targ is not channels.Main:
        wrapper.pm(messages["invalid_fsend_permissions"])
        return

    if action:
        message = "\u0001ACTION {0}\u0001".format(message)

    targ.send(message, privmsg=True)

@command("fsay", flag="s", pm=True)
def fsay(wrapper: MessageDispatcher, message: str):
    """Talk through the bot as a normal message."""
    _say(wrapper, message, "fsay")

@command("fdo", flag="s", pm=True)
def fdo(wrapper: MessageDispatcher, message: str):
    """Act through the bot as an action."""
    _say(wrapper, message, "fdo", action=True)

@command("fgame", flag="g", phases=("join",))
def fgame(wrapper: MessageDispatcher, message: str):
    """Force a certain game mode to be picked. Disable voting for game modes upon use."""
    from src.gamemodes import GAME_MODES
    var = wrapper.game_state

    if message:
        gamemode = message.strip().lower()
        parts = gamemode.replace("=", " ", 1).split(None, 1)
        if len(parts) > 1:
            gamemode, modeargs = parts
        else:
            gamemode = parts[0]
            modeargs = None

        _fr = messages.raw("_commands", "fgame opt reset")
        if gamemode in _fr:
            var.current_mode.teardown()
            var.current_mode = None
            channels.Main.send(messages["fgame_success"].format(wrapper.source))
            return

        allowed = GAME_MODES.keys() - set(config.Main.get("gameplay.disable.gamemodes"))
        gamemode = gamemode.split()[0]
        match = match_mode(gamemode, scope=allowed, remove_spaces=True)
        if len(match) == 0:
            wrapper.pm(messages["invalid_mode"].format(gamemode))
            return
        elif len(match) > 1:
            wrapper.pm(messages["ambiguous_mode"].format([m.local for m in match]))
            return
        parts[0] = match.get().key

        from src.gamestate import set_gamemode
        if set_gamemode(var, "=".join(parts)):
            channels.Main.send(messages["fgame_success"].format(wrapper.source))
    else:
        wrapper.pm(fgame_help())

def fgame_help(args=""):
    args = args.strip()
    from src.gamemodes import GAME_MODES

    if not args:
        return messages["available_mode_setters"].format(GAME_MODES.keys() - set(config.Main.get("gameplay.disable.gamemodes")))
    elif args in GAME_MODES.keys() and args not in config.Main.get("gameplay.disable.gamemodes"):
        return GAME_MODES[args][0].__doc__ or messages["setter_no_doc"].format(args)
    else:
        return messages["setter_not_found"].format(args)

# eval/exec/freceive are owner-only but also marked with "d" flag
# to disable them outside of debug mode
@command("eval", owner_only=True, flag="d", pm=True)
def pyeval(wrapper: MessageDispatcher, message: str):
    """Evaluate a Python expression."""
    import inspect  # for more expressive debugging
    var = wrapper.game_state
    try:
        wrapper.send(str(eval(message))[:500])
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

@command("exec", owner_only=True, flag="d", pm=True)
def py(wrapper: MessageDispatcher, message: str):
    """Execute arbitrary Python code."""
    var = wrapper.game_state
    try:
        exec(message)
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

@command("freceive", owner_only=True, flag="d", pm=True)
def freceive(wrapper: MessageDispatcher, message: str):
    from oyoyo.parse import parse_raw_irc_command
    try:
        line = message.encode("utf-8")
        prefix, cmd, args = parse_raw_irc_command(line)
        prefix = prefix.decode("utf-8")
        args = [arg.decode("utf-8") for arg in args if isinstance(arg, bytes)]
        if cmd in ("privmsg", "notice"):
            is_notice = cmd == "notice"
            handler.on_privmsg(wrapper.client, prefix, *args, notice=is_notice)
        else:
            handler.unhandled(wrapper.client, prefix, cmd, *args)
    except Exception as e:
        wrapper.send("{e.__class__.__name__}: {e}".format(e=e))

@command("ferror", flag="d")
def force_error(wrapper: MessageDispatcher, message: str):
    if not message:
        message = f"Error requested by {wrapper.source.name}"
    raise RuntimeError(message)

def _force_command(wrapper: MessageDispatcher, name: str, players, message):
    for user in players:
        handler.parse_and_dispatch(wrapper, name, message, force=user)
    wrapper.send(messages["operation_successful"])

@command("force", flag="d")
def force(wrapper: MessageDispatcher, message: str):
    """Force a certain player to use a specific command."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    target = msg.pop(0).strip()
    match = users.complete_match(target, get_participants(wrapper.game_state))
    if target == "*":
        players = get_players(wrapper.game_state)
    elif not match:
        wrapper.send(messages["invalid_target"])
        return
    else:
        players = [match.get()]

    _force_command(wrapper, msg.pop(0), players, " ".join(msg))

@command("rforce", flag="d")
def rforce(wrapper: MessageDispatcher, message: str):
    """Force all players of a given role to perform a certain action."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    var = wrapper.game_state

    target = msg.pop(0).strip().lower()
    possible = match_role(target, allow_special=False, remove_spaces=True)
    if target == "*":
        players = get_players(var)
    elif possible:
        players = get_all_players(var, (possible.get().key,))
    elif len(possible) > 1:
        wrapper.send(messages["ambiguous_role"].format([r.singular for r in possible]))
        return
    else:
        wrapper.send(messages["no_such_role"].format(message))
        return

    _force_command(wrapper, msg.pop(0), players, " ".join(msg))

@command("ftotem", flag="d", phases=("night",))
def ftotem(wrapper: MessageDispatcher, message: str):
    """Force a shaman to have a particular totem."""
    msg = re.split(" +", message)
    if len(msg) < 2:
        wrapper.send(messages["incorrect_syntax"])
        return

    var = wrapper.game_state

    target = msg.pop(0).strip()
    match = users.complete_match(target, get_players(var))
    if not match:
        wrapper.send(messages["invalid_target"])
        return

    from src.roles.helper.shamans import change_totem
    try:
        change_totem(var, match.get(), " ".join(msg))
    except ValueError as e:
        wrapper.send(str(e))
        return

    wrapper.send(messages["operation_successful"])
