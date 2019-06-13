# The bot commands implemented in here are present no matter which module is loaded

import base64
import socket
import sys
import threading
import time
import traceback
import functools
import statistics
import math
from typing import Optional

import botconfig
import src.settings as var
from src import decorators, wolfgame, events, channels, hooks, users, errlog as log, stream_handler as alog
from src.messages import messages
from src.functions import get_participants, get_all_roles
from src.utilities import complete_role
from src.dispatcher import MessageDispatcher
from src.decorators import handle_error, command, hook
from src.users import User

@handle_error
def on_privmsg(cli, rawnick, chan, msg, *, notice=False):
    if notice and "!" not in rawnick or not rawnick: # server notice; we don't care about those
        return

    _ignore_locals_ = False
    if var.USER_DATA_LEVEL == 0 or var.CHANNEL_DATA_LEVEL == 0:
        _ignore_locals_ = True  # don't expose in tb if we're trying to anonymize stuff

    user = users._get(rawnick, allow_none=True) # FIXME

    ch = chan.lstrip("".join(hooks.Features["PREFIX"]))

    if users.equals(chan, users.Bot.nick): # PM
        target = users.Bot
    else:
        target = channels.get(ch, allow_none=True)

    if user is None or target is None:
        return

    wrapper = MessageDispatcher(user, target)

    if wrapper.public and botconfig.IGNORE_HIDDEN_COMMANDS and not chan.startswith(tuple(hooks.Features["CHANTYPES"])):
        return

    if (notice and ((wrapper.public and not botconfig.ALLOW_NOTICE_COMMANDS) or
                    (wrapper.private and not botconfig.ALLOW_PRIVATE_NOTICE_COMMANDS))):
        return  # not allowed in settings

    for fn in decorators.COMMANDS[""]:
        fn.caller(var, wrapper, msg)

    parts = msg.split(sep=" ", maxsplit=1)
    key = parts[0].lower()
    if len(parts) > 1:
        message = parts[1].strip()
    else:
        message = ""

    if wrapper.public and not key.startswith(botconfig.CMD_CHAR):
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
    if key.startswith(botconfig.CMD_CHAR):
        key = key[len(botconfig.CMD_CHAR):]

    # check for role prefix
    parts = key.split(sep=":", maxsplit=1)
    if len(parts) > 1:
        key = parts[1]
        role_prefix = parts[0]
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
        matches = complete_role(var, role_prefix, remove_spaces=True)
        if len(matches) == 1:
            role_prefix = matches[0]
        elif len(matches) > 1:
            wrapper.pm(messages["ambiguous_role"].format(matches))
            return
        else:
            wrapper.pm(messages["no_such_role"].format(role_prefix))
            return

    # Don't change this into decorators.COMMANDS[key] even though it's a defaultdict,
    # as we don't want to insert bogus command keys into the dict.
    cmds = []
    phase = var.PHASE
    if context.source in get_participants():
        roles = get_all_roles(context.source)
        common_roles = set(roles)  # roles shared by every eligible role command
        # A user can be a participant but not have a role, for example, dead vengeful ghost
        has_roles = len(roles) != 0
        if role_prefix is not None:
            roles &= {role_prefix}  # only fire off role commands for the user-specified role
    else:
        roles = set()
        common_roles = set()
        has_roles = False

    for fn in decorators.COMMANDS.get(key, []):
        if not fn.roles:
            cmds.append(fn)
        elif roles.intersection(fn.roles):
            cmds.append(fn)
            common_roles.intersection_update(fn.roles)

    if has_roles and not common_roles:
        # getting here means that at least one of the role_cmds is disjoint
        # from the others. For example, augur see vs seer see when a bare see
        # is executed. In this event, display a helpful error message instructing
        # the user to resolve the ambiguity.
        common_roles = set(roles)
        info = [0, 0]
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

def run_lagcheck(cli):
    from oyoyo.client import TokenBucket
    cli.tokenbucket = TokenBucket(100, 0.1)
    print("Lag check in progress. The bot will quit IRC after this is complete. This may take several minutes.")

    # set up initial variables
    timings = []

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
        elif clock < 5:
            # run another batch
            _lagcheck_1(cli, int(clock) + 1)
        else:
            # process data
            _lagcheck_2(cli, timings)

    # we still have startup lag at this point, so delay our check until we receive this message successfully
    users.Bot.send("0 0")

def _lagcheck_1(cli, phase=1):
    # Burst some messages and time how long it takes for them to get back to us
    # This is a bit conservative in order to establish a baseline (so that we don't flood ourselves out)
    for i in range(12):
        users.Bot.send("{0} {1}".format(phase, time.perf_counter()))
    # signal that we're done
    users.Bot.send("0 {0}".format(phase))

def _lagcheck_2(cli, timings):
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

    print("Lag check complete! We recommend adding the following settings to your botconfig.py:")
    delay = max(0.8 * fixed[threshold], 0.1)
    burst = int(4 * threshold)
    if burst < 12: # we know we can successfully burst at least 12 messages at once
        burst = 12

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

def connect_callback(cli):
    regaincount = 0
    releasecount = 0

    @hook("endofmotd", hookid=294)
    @hook("nomotd", hookid=294)
    def prepare_stuff(cli, prefix, *args):
        from src import lagcheck
        alog("Received end of MOTD from {0}".format(prefix))

        # This callback only sets up event listeners
        wolfgame.connect_callback()

        # just in case we haven't managed to successfully auth yet
        if botconfig.PASS and not botconfig.SASL_AUTHENTICATION:
            cli.ns_identify(botconfig.USERNAME or botconfig.NICK,
                            botconfig.PASS,
                            nickserv=var.NICKSERV,
                            command=var.NICKSERV_IDENTIFY_COMMAND)

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
            alog("Preparing lag check")
            # if we ARE doing a lagcheck, we need at least our own host or things break
            users.Bot.who()

        #if var.CHANSERV_OP_COMMAND: # TODO: Add somewhere else if needed
        #    cli.msg(var.CHANSERV, var.CHANSERV_OP_COMMAND.format(channel=botconfig.CHANNEL))

        users.Bot.change_nick(botconfig.NICK)

        if var.SERVER_PING_INTERVAL > 0:
            def ping_server_timer(cli):
                ping_server(cli)

                t = threading.Timer(var.SERVER_PING_INTERVAL, ping_server_timer, args=(cli,))
                t.daemon = True
                t.start()

            ping_server_timer(cli)

    def setup_handler(evt, var, target):
        from src import lagcheck
        if lagcheck: # we just got our own host back
            target.client.command_handler["privmsg"] = on_privmsg
            run_lagcheck(target.client)
        else:
            target.client.command_handler["privmsg"] = on_privmsg
            target.client.command_handler["notice"] = functools.partial(on_privmsg, notice=True)

        events.remove_listener("who_end", setup_handler)

    events.add_listener("who_end", setup_handler)

    def mustregain(cli, server, bot_nick, nick, msg):
        nonlocal regaincount

        if not botconfig.PASS or bot_nick == nick or regaincount > 3:
            return
        if var.NICKSERV_REGAIN_COMMAND:
            cli.ns_regain(nick=botconfig.NICK, password=botconfig.PASS, nickserv=var.NICKSERV, command=var.NICKSERV_REGAIN_COMMAND)
        else:
            cli.ns_ghost(nick=botconfig.NICK, password=botconfig.PASS, nickserv=var.NICKSERV, command=var.NICKSERV_GHOST_COMMAND)
        # it is possible (though unlikely) that regaining the nick fails for some reason and we would loop infinitely
        # as such, keep track of a count of how many times we regain, and after 3 times we no longer attempt to regain nicks
        # Since we'd only be regaining on initial connect, this should be safe. The same trick is used below for release as well
        regaincount += 1
        users.Bot.change_nick(botconfig.NICK)

    def mustrelease(cli, server, bot_nick, nick, msg):
        nonlocal releasecount

        if not botconfig.PASS or bot_nick == nick or releasecount > 3:
            return # prevents the bot from trying to release without a password
        if var.NICKSERV_RELEASE_COMMAND:
            cli.ns_release(nick=botconfig.NICK, password=botconfig.PASS, nickserv=var.NICKSERV, command=var.NICKSERV_GHOST_COMMAND)
        else:
            cli.ns_ghost(nick=botconfig.NICK, password=botconfig.PASS, nickserv=var.NICKSERV, command=var.NICKSERV_GHOST_COMMAND)
        releasecount += 1
        users.Bot.change_nick(botconfig.NICK)

    @hook("unavailresource", hookid=239)
    @hook("nicknameinuse", hookid=239)
    def must_use_temp_nick(cli, *etc):
        users.Bot.nick += "_"
        users.Bot.change_nick()
        cli.user(botconfig.NICK, "") # TODO: can we remove this?

        hook.unhook(239)
        hook("unavailresource", hookid=240)(mustrelease)
        hook("nicknameinuse", hookid=241)(mustregain)

    request_caps = {"account-notify", "extended-join", "multi-prefix", "chghost"}

    if botconfig.SASL_AUTHENTICATION:
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

            if botconfig.SASL_AUTHENTICATION and "sasl" not in supported_caps:
                alog("Server does not support SASL authentication")
                cli.quit()
                raise ValueError("Server does not support SASL authentication")

            common_caps = request_caps & supported_caps

            if common_caps:
                cli.send("CAP REQ " ":{0}".format(" ".join(common_caps)))

        elif cmd == "ACK":
            if "sasl" in caps[0]:
                if var.SSL_CERTFILE:
                    mech = "EXTERNAL"
                else:
                    mech = "PLAIN"
                selected_sasl = mech

                if supported_sasl is None or mech in supported_sasl:
                    cli.send("AUTHENTICATE {0}".format(mech))
                else:
                    alog("Server does not support the SASL {0} mechanism".format(mech))
                    cli.quit()
                    raise ValueError("Server does not support the SASL {0} mechanism".format(mech))
            else:
                cli.send("CAP END")
        elif cmd == "NAK":
            # This isn't supposed to happen. The server claimed to support a
            # capability but now claims otherwise.
            alog("Server refused capabilities: {0}".format(" ".join(caps[0])))

    if botconfig.SASL_AUTHENTICATION:
        @hook("authenticate")
        def auth_plus(cli, something, plus):
            if plus == "+":
                if selected_sasl == "EXTERNAL":
                    cli.send("AUTHENTICATE +")
                elif selected_sasl == "PLAIN":
                    account = (botconfig.USERNAME or botconfig.NICK).encode("utf-8")
                    password = botconfig.PASS.encode("utf-8")
                    auth_token = base64.b64encode(b"\0".join((account, account, password))).decode("utf-8")
                    cli.send("AUTHENTICATE " + auth_token, log="AUTHENTICATE [redacted]")

        @hook("903")
        def on_successful_auth(cli, blah, blahh, blahhh):
            cli.send("CAP END")

        @hook("904")
        @hook("905")
        @hook("906")
        @hook("907")
        def on_failure_auth(cli, *etc):
            nonlocal selected_sasl
            if selected_sasl == "EXTERNAL" and (supported_sasl is None or "PLAIN" in supported_sasl):
                # EXTERNAL failed, retry with PLAIN as we may not have set up the client cert yet
                selected_sasl = "PLAIN"
                alog("EXTERNAL auth failed, retrying with PLAIN... ensure the client cert is set up in NickServ")
                cli.send("AUTHENTICATE PLAIN")
            else:
                alog("Authentication failed.  Did you fill the account name "
                     "in botconfig.USERNAME if it's different from the bot nick?")
                cli.quit()

    users.Bot = users.BotUser(cli, botconfig.NICK)

# vim: set sw=4 expandtab:
