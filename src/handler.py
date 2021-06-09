# The bot commands implemented in here are present no matter which module is loaded

from __future__ import annotations

import base64
import threading
import time
import functools
<<<<<<< HEAD
import logging
from typing import Optional

import src.settings as var
from src import config, decorators, wolfgame, channels, users
=======
import statistics
import math
from typing import List, Optional, Union

import botconfig  # type: ignore
import src.settings as var
from src import decorators, wolfgame, channels, users, plog
>>>>>>> master
from src.messages import messages
from src.functions import get_participants, get_all_roles, match_role
from src.dispatcher import MessageDispatcher
from src.decorators import handle_error, command, hook
from src.context import Features
from src.users import User
from src.events import Event, EventListener

@handle_error
def on_privmsg(cli, rawnick, chan, msg, *, notice=False):
    if notice and "!" not in rawnick or not rawnick: # server notice; we don't care about those
        return

    _ignore_locals_ = False
    if var.USER_DATA_LEVEL == 0 or var.CHANNEL_DATA_LEVEL == 0:
        _ignore_locals_ = True  # don't expose in tb if we're trying to anonymize stuff

    # bot needs to talk to itself during lagchecks
    from src import lagcheck
    allow_bot = lagcheck > 0
    user = users.get(rawnick, allow_none=True, allow_bot=allow_bot)

    ch = chan.lstrip("".join(Features["PREFIX"]))

    if users.equals(chan, users.Bot.nick): # PM
        target = users.Bot
    else:
        target = channels.get(ch, allow_none=True)

    if user is None or target is None:
        return

    wrapper = MessageDispatcher(user, target)

    if wrapper.public and config.Main.get("transports[0].user.ignore.hidden") and not chan.startswith(tuple(Features["CHANTYPES"])):
        return

    if (notice and ((wrapper.public and config.Main.get("transports[0].user.ignore.channel_notice")) or
                    (wrapper.private and config.Main.get("transports[0].user.ignore.private_notice")))):
        return  # not allowed in settings

    for fn in decorators.COMMANDS[""]:
        fn.caller(var, wrapper, msg)

    parts = msg.split(sep=" ", maxsplit=1)
    key = parts[0].lower()
    if len(parts) > 1:
        message = parts[1].strip()
    else:
        message = ""

    if wrapper.public and not key.startswith(config.Main.get("transports[0].user.command_prefix")):
        return  # channel message but no prefix; ignore
    parse_and_dispatch(var, wrapper, key, message)

def parse_and_dispatch(var,
                     wrapper: MessageDispatcher,
                     key: str,
                     message: str,
                     role: Optional[str] = None,
                     force: Optional[User] = None) -> None:
    """ Parses a command key and dispatches it should it match a valid command.

    :param var: Game state
    :param wrapper: Information about who is executing command and where command is being executed
    :param key: Command name. May be prefixed with command character and role name.
    :param message: Parameters to the command.
    :param role: Only dispatch a role command for the specified role. Even if a role name is specified in key,
        this will take precedence if set.
    :param force: Force the command to execute as the specified user instead of the current user.
        Admin and owner commands cannot be forced this way. When forcing a command, we set the appropriate context
        (channel vs PM) automatically as well.
    :return:
    """
    _ignore_locals_ = True
    cmd_prefix = config.Main.get("transports[0].user.command_prefix")
    if key.startswith(cmd_prefix):
        key = key[len(cmd_prefix):]

    # check for role prefix
    parts = key.split(sep=":", maxsplit=1)
    if len(parts) > 1 and len(parts[0]) and not parts[0].isnumeric():
        key = parts[1]
        role_prefix: Optional[str] = parts[0]
    else:
        key = parts[0]
        role_prefix = None

    if role:
        role_prefix = role

    if not key:
        return

    if force:
        context = MessageDispatcher(force, wrapper.target)
    else:
        context = wrapper

    if role_prefix is not None:
        # match a role prefix to a role. Multi-word roles are supported by stripping the spaces
        matches = match_role(var, role_prefix, remove_spaces=True)
        if len(matches) == 1:
            role_prefix = matches.get().key
        elif len(matches) > 1:
            wrapper.pm(messages["ambiguous_role"].format([m.singular for m in matches]))
            return
        else:
            wrapper.pm(messages["no_such_role"].format(role_prefix))
            return

    # Don't change this into decorators.COMMANDS[key] even though it's a defaultdict,
    # as we don't want to insert bogus command keys into the dict.
    cmds: List[command] = []
    phase = var.PHASE
    if context.source in get_participants():
        roles = get_all_roles(context.source)
        common_roles = set(roles)  # roles shared by every eligible role command
        # A user can be a participant but not have a role, for example, dead vengeful ghost
        has_roles = len(roles) != 0
    else:
        roles = set()
        common_roles = set()
        has_roles = False

    for i in range(2):
        cmds.clear()
        common_roles = set(roles)
        # if we execute this loop twice, it means we had an ambiguity the first time around
        # only fire off role commands for the user-specified role in that event, if one was provided
        # doing it this way ensures we only look at the role prefix if it's actually required,
        # meaning that prefixing a role for public commands doesn't "prove" the user has that role
        # in the vast majority of cases
        if i == 1 and role_prefix is not None:
            roles &= {role_prefix}

        for fn in decorators.COMMANDS.get(key, []):
            if not fn.roles:
                cmds.append(fn)
            elif roles.intersection(fn.roles):
                cmds.append(fn)
                common_roles.intersection_update(fn.roles)

        # if this isn't a role command or the command is unambiguous, continue logic instead of
        # making use of role_prefix
        if not has_roles or common_roles:
            break

    if has_roles and not common_roles:
        # getting here means that at least one of the role_cmds is disjoint
        # from the others. For example, augur see vs seer see when a bare see
        # is executed. In this event, display a helpful error message instructing
        # the user to resolve the ambiguity.
        common_roles = set(roles)
        info: List[Union[str, int]] = [0, 0]
        role_map = messages.get_role_mapping()
        for fn in cmds:
            fn_roles = roles.intersection(fn.roles)
            if not fn_roles:
                continue
            for role1 in common_roles:
                info[0] = role_map[role1].replace(" ", "")
                break
            for role2 in fn_roles:
                info[1] = role_map[role2].replace(" ", "")
                break
            common_roles &= fn_roles
            if not common_roles:
                break
        wrapper.pm(messages["ambiguous_command"].format(key, info[0], info[1]))
        return

    for fn in cmds:
        if force:
            if fn.owner_only or fn.flag:
                wrapper.pm(messages["no_force_admin"])
                return
            if fn.chan:
                context.target = channels.Main
            else:
                context.target = users.Bot
        if phase == var.PHASE:  # don't call any more commands if one we just called executed a phase transition
            fn.caller(var, context, message)


def unhandled(cli, prefix, cmd, *args):
    for fn in decorators.HOOKS.get(cmd, []):
        fn.caller(cli, prefix, *args)

def ping_server(cli):
    cli.send("PING :{0}".format(time.time()))

@command("latency", pm=True)
def latency(var, wrapper, message):
    ping_server(wrapper.client)

    @hook("pong", hookid=300)
    def latency_pong(cli, server, target, ts):
        lat = round(time.time() - float(ts), 3)
        wrapper.reply(messages["latency"].format(lat))
        hook.unhook(300)

<<<<<<< HEAD
=======
def run_lagcheck(cli):
    from oyoyo.client import TokenBucket
    cli.tokenbucket = TokenBucket(100, 0.1)
    plog("Lag check in progress. The bot will quit IRC after this is complete. This may take several minutes.")
    plog("The bot may restart a couple of times during the check.")

    # set up initial variables
    from src import lagcheck
    timings = []
    max_phases = lagcheck

    @command("", pm=True)
    def on_pm(var, wrapper, message):
        if wrapper.source is not users.Bot:
            return

        cur = time.perf_counter()
        phase, clock = message.split(" ")
        phase = int(phase)
        clock = float(clock)
        if phase > 0:
            # timing data for current phase
            timings.append((phase, cur - clock))
        elif clock < max_phases:
            # run another batch
            # note that clock is correct here; end of phase is sent as phase=0 clock=phase#
            next_phase = int(clock) + 1
            plog("Testing phase {0}/{1}...".format(next_phase, max_phases))
            _lagcheck_1(next_phase, max_phases)
        else:
            # process data
            _lagcheck_2(cli, timings, max_phases)

    # we still have startup lag at this point, so delay our check until we receive this message successfully
    users.Bot.send("0 0")

def _lagcheck_1(phase, max_phases):
    # Burst some messages and time how long it takes for them to get back to us
    burst = max(12, 12 - (phase * 2) + max_phases)
    for i in range(burst):
        users.Bot.send("{0} {1}".format(phase, time.perf_counter()))
    # signal that we're done
    users.Bot.send("0 {0}".format(phase))

def _lagcheck_2(cli, timings, max_phases):
    # Assume our first message isn't throttled and is an accurate representation of the roundtrip time
    # for the server. We use this to normalize all the other timings, as since we bursted N messages
    # at once, message N will have around N*RTT of delay even if there is no throttling going on.
    if timings:
        rtt = timings[0][1]
        fixed = [0] * len(timings)
    else:
        rtt = 0
        fixed = []
    counter = 0
    prev_phase = 0
    threshold = 0
    for i, (phase, diff) in enumerate(timings):
        if phase != prev_phase:
            prev_phase = phase
            counter = 0
        counter += 1
        fixed[i] = diff - (counter * rtt)

        if i < 4: # wait for a handful of data points
            continue
        avg = statistics.mean(fixed[0:i])
        stdev = statistics.pstdev(fixed[0:i], mu=avg)
        if stdev == 0: # need a positive std dev
            continue
        # if our current measurement varies more than 3 standard deviations from the mean,
        # then we probably started getting fakelag
        if threshold == 0 and fixed[i] > avg + 3 * stdev:
            # we've detected that we've hit fakelag; set threshold to i (technically it happens a while
            # before i, but i is a decent overestimate of when it happens)
            threshold = i

    plog("Lag check complete! We recommend adding the following settings to your botconfig.py:")
    delay = max(0.8 * fixed[threshold], 0.1)
    # establish a reasonable minimum burst amount
    # we were able to burst 10 + max_phases without getting disconnected so we know for sure it works
    burst = max(12, 10 + max_phases)

    if threshold == 0:
        print("IRC_TB_INIT = 30", "IRC_TB_BURST = 30", "IRC_TB_DELAY = {0:.2f}".format(delay), sep="\n")
    else:
        print("IRC_TB_INIT = {0}".format(burst), "IRC_TB_BURST = {0}".format(burst), "IRC_TB_DELAY = {0:.2f}".format(delay), sep="\n")

    if burst < 20 and delay > 1.5:
        # recommend turning off deadchat if we can't push out messages fast enough
        print("ENABLE_DEADCHAT = False")

    if burst == 12 and delay > 2:
        # if things are really bad, recommend turning off wolfchat too
        print("RESTRICT_WOLFCHAT = 0x0b")

    cli.quit()

>>>>>>> master
def connect_callback(cli):
    regaincount = 0
    releasecount = 0

    @hook("endofmotd", hookid=294)
    @hook("nomotd", hookid=294)
    def prepare_stuff(cli, prefix, *args):
<<<<<<< HEAD
        alog("Received end of MOTD from {0}".format(prefix))
=======
        from src import lagcheck
        plog("Received end of MOTD from {0}".format(prefix))
>>>>>>> master

        # This callback only sets up event listeners
        wolfgame.connect_callback()

        # just in case we haven't managed to successfully auth yet
        nick = config.Main.get("transports[0].user.nick")
        username = config.Main.get("transports[0].authentication.services.username")
        if not username:
            username = nick
        password = config.Main.get("transports[0].authentication.services.password")
        use_sasl = config.Main.get("transports[0].authentication.services.use_sasl")
        if password and not use_sasl:
            cli.ns_identify(username,
                            password,
                            nickserv=var.NICKSERV,
                            command=var.NICKSERV_IDENTIFY_COMMAND)

        # give bot operators an opportunity to do some custom stuff here if they wish
        event = Event("irc_connected", {})
        event.dispatch(var, cli)

<<<<<<< HEAD
        main_channel = config.Main.get("transports[0].channels.main")
        if isinstance(main_channel, str):
            main_channel = {"name": main_channel, "prefix": "", "key": ""}
        channels.Main = channels.add(main_channel["name"], cli, key=main_channel["key"])
        channels.Dummy = channels.add("*", cli)

        alt_channels = config.Main.get("transports[0].channels.alternate")
        transport_name = config.Main.get("transports[0].name")
        debug_chan = None
        log_chan = None
        for log in config.Main.get("logging.logs"):
            if log["transport"] != transport_name:
                continue
            if log["group"] == "debug":
                debug_chan = log["destination"]
            elif log["group"] == "warnings":
                log_chan = log["destination"]
        for chan in alt_channels:
            if isinstance(chan, str):
                chan = {"name": chan, "prefix": "", "key": ""}
            c = channels.add(chan["name"], cli, key=chan["key"])
            if chan == debug_chan:
                channels.Dev = c
                var.DEV_PREFIX = chan["prefix"]
            if chan == log_chan:
                var.LOG_PREFIX = chan["prefix"]

        users.Bot.change_nick(nick)
=======
        # don't join any channels if we're just doing a lag check
        if not lagcheck:
            channels.Main = channels.add(botconfig.CHANNEL, cli)
            channels.Dummy = channels.add("*", cli)

            if botconfig.ALT_CHANNELS:
                for chan in botconfig.ALT_CHANNELS.split(","):
                    channels.add(chan, cli)

            if botconfig.DEV_CHANNEL:
                channels.Dev = channels.add(botconfig.DEV_CHANNEL, cli)

            if var.LOG_CHANNEL:
                channels.add(var.LOG_CHANNEL, cli)
        else:
            plog("Preparing lag check")
            # if we ARE doing a lagcheck, we need at least our own host or things break
            users.Bot.who()

        users.Bot.change_nick(botconfig.NICK)
>>>>>>> master

        if var.SERVER_PING_INTERVAL > 0:
            def ping_server_timer(cli):
                ping_server(cli)

                t = threading.Timer(var.SERVER_PING_INTERVAL, ping_server_timer, args=(cli,))
                t.daemon = True
                t.start()

            ping_server_timer(cli)

        hook.unhook(294)

    def setup_handler(evt, target):
        target.client.command_handler["privmsg"] = on_privmsg
        target.client.command_handler["notice"] = functools.partial(on_privmsg, notice=True)
        who_end.remove("who_end")

    who_end = EventListener(setup_handler)
    who_end.install("who_end")

    def mustregain(cli, server, bot_nick, nick, msg):
        nonlocal regaincount

        config_nick = config.Main.get("transports[0].user.nick")
        password = config.Main.get("transports[0].authentication.services.password")
        if not password or bot_nick == nick or regaincount > 3:
            return
        if var.NICKSERV_REGAIN_COMMAND:
            cli.ns_regain(nick=config_nick, password=password, nickserv=var.NICKSERV, command=var.NICKSERV_REGAIN_COMMAND)
        else:
            cli.ns_ghost(nick=config_nick, password=password, nickserv=var.NICKSERV, command=var.NICKSERV_GHOST_COMMAND)
        # it is possible (though unlikely) that regaining the nick fails for some reason and we would loop infinitely
        # as such, keep track of a count of how many times we regain, and after 3 times we no longer attempt to regain nicks
        # Since we'd only be regaining on initial connect, this should be safe. The same trick is used below for release as well
        regaincount += 1
        users.Bot.change_nick(config_nick)

    def mustrelease(cli, server, bot_nick, nick, msg):
        nonlocal releasecount

        config_nick = config.Main.get("transports[0].user.nick")
        password = config.Main.get("transports[0].authentication.services.password")
        if not password or bot_nick == nick or releasecount > 3:
            return # prevents the bot from trying to release without a password
        if var.NICKSERV_RELEASE_COMMAND:
            cli.ns_release(nick=config_nick, password=password, nickserv=var.NICKSERV, command=var.NICKSERV_GHOST_COMMAND)
        else:
            cli.ns_ghost(nick=config_nick, password=password, nickserv=var.NICKSERV, command=var.NICKSERV_GHOST_COMMAND)
        releasecount += 1
        users.Bot.change_nick(config_nick)

    @hook("unavailresource", hookid=239)
    @hook("nicknameinuse", hookid=239)
    def must_use_temp_nick(cli, *etc):
        users.Bot.nick += "_"
        users.Bot.change_nick()

        hook.unhook(239)
        hook("unavailresource", hookid=240)(mustrelease)
        hook("nicknameinuse", hookid=241)(mustregain)

    request_caps = {"account-notify", "chghost", "extended-join", "multi-prefix"}

    if config.Main.get("transports[0].authentication.services.use_sasl"):
        request_caps.add("sasl")

    supported_caps = set()
    supported_sasl = None
    selected_sasl = None

    @hook("cap")
    def on_cap(cli, svr, mynick, cmd, *caps):
        nonlocal supported_sasl, selected_sasl
        # caps is a star because we might receive multiline in LS
        if cmd == "LS":
            for item in caps[-1].split(): # First item may or may not be *, for multiline
                try:
                    key, value = item.split("=", 1)
                except ValueError:
                    key = item
                    value = None
                supported_caps.add(key)
                if key == "sasl" and value is not None:
                    supported_sasl = set(value.split(","))

            if caps[0] == "*": # Multiline, don't continue yet
                return

<<<<<<< HEAD
            if config.Main.get("transports[0].authentication.services.use_sasl") and "sasl" not in supported_caps:
                alog("Server does not support SASL authentication")
=======
            if botconfig.SASL_AUTHENTICATION and "sasl" not in supported_caps:
                plog("Server does not support SASL authentication")
>>>>>>> master
                cli.quit()
                sys.exit(1)

            common_caps = request_caps & supported_caps

            if common_caps:
                cli.send("CAP REQ :{0}".format(" ".join(common_caps)))

        elif cmd == "ACK":
            acked_caps = caps[0].split()
            for c in acked_caps:
                enabled = True
                if c[0] == "-":
                    enabled = False
                    c = c[1:]
                Features[c] = enabled

            if Features.get("sasl", False):
                if var.SSL_CERTFILE:
                    mech = "EXTERNAL"
                else:
                    mech = "PLAIN"
                selected_sasl = mech

                if supported_sasl is None or mech in supported_sasl:
                    cli.send("AUTHENTICATE {0}".format(mech))
                else:
                    plog("Server does not support the SASL {0} mechanism".format(mech))
                    cli.quit()
                    sys.exit(1)
            else:
                cli.send("CAP END")
        elif cmd == "NAK":
            # This isn't supposed to happen. The server claimed to support a
            # capability but now claims otherwise.
            plog("Server refused capabilities: {0}".format(" ".join(caps[0])))

        elif cmd == "NEW":
            # New capability advertised by the server, see if we want to enable it
            new_caps = caps[0].split()
            req_new_caps = set()
            for item in new_caps:
                try:
                    key, value = item.split("=", 1)
                except ValueError:
                    key = item
                    value = None
                if key not in supported_caps and key in request_caps and key != "sasl":
                    req_new_caps.add(key)
                supported_caps.add(key)
            if req_new_caps:
                cli.send("CAP REQ :{0}".format(" ".join(req_new_caps)))

        elif cmd == "DEL":
            # Server no longer supports these capabilities
            rem_caps = caps[0].split()
            for item in rem_caps:
                supported_caps.discard(item)
                Features.unset(item)

    if config.Main.get("transports[0].authentication.services.use_sasl"):
        @hook("authenticate")
        def auth_plus(cli, something, plus):
            username = config.Main.get("transports[0].authentication.services.username")
            if not username:
                username = config.Main.get("transports[0].user.nick")
            password = config.Main.get("transports[0].authentication.services.password")
            if plus == "+":
                if selected_sasl == "EXTERNAL":
                    cli.send("AUTHENTICATE +")
                elif selected_sasl == "PLAIN":
                    account = username.encode("utf-8")
                    password = password.encode("utf-8")
                    auth_token = base64.b64encode(b"\0".join((account, account, password))).decode("utf-8")
                    cli.send("AUTHENTICATE " + auth_token, log="AUTHENTICATE [redacted]")

        @hook("saslsuccess")
        def on_successful_auth(cli, blah, blahh, blahhh):
            nonlocal selected_sasl
            Features["sasl"] = selected_sasl
            cli.send("CAP END")

        @hook("saslfail")
        @hook("sasltoolong")
        @hook("saslaborted")
        def on_failure_auth(cli, *etc):
            nonlocal selected_sasl
            if selected_sasl == "EXTERNAL" and (supported_sasl is None or "PLAIN" in supported_sasl):
                # EXTERNAL failed, retry with PLAIN as we may not have set up the client cert yet
                selected_sasl = "PLAIN"
                plog("EXTERNAL auth failed, retrying with PLAIN... ensure the client cert is set up in NickServ")
                cli.send("AUTHENTICATE PLAIN")
            else:
<<<<<<< HEAD
                alog("Authentication failed.  Did you fill the account name "
                     "in transport.authentication.services.username if it's different from the bot nick?")
=======
                plog("Authentication failed.  Did you fill the account name "
                     "in botconfig.USERNAME if it's different from the bot nick?")
>>>>>>> master
                cli.quit()
                sys.exit(1)

    users.Bot = users.BotUser(cli, config.Main.get("transports[0].user.nick"))
