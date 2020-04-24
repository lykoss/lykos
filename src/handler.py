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
from src import decorators, wolfgame, channels, users, errlog as log, stream_handler as alog
from src.messages import messages
from src.functions import get_participants, get_all_roles
from src.utilities import complete_role
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

    user = users.get(rawnick, allow_none=True)

    ch = chan.lstrip("".join(Features["PREFIX"]))

    if users.equals(chan, users.Bot.nick): # PM
        target = users.Bot
    else:
        target = channels.get(ch, allow_none=True)

    if user is None or target is None:
        return

    wrapper = MessageDispatcher(user, target)

    if wrapper.public and botconfig.IGNORE_HIDDEN_COMMANDS and not chan.startswith(tuple(Features["CHANTYPES"])):
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
    if len(parts) > 1 and len(parts[0]):
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

def connect_callback(cli):
    regaincount = 0
    releasecount = 0

    @hook("endofmotd", hookid=294)
    @hook("nomotd", hookid=294)
    def prepare_stuff(cli, prefix, *args):
        alog("Received end of MOTD from {0}".format(prefix))

        # This callback only sets up event listeners
        wolfgame.connect_callback()

        # just in case we haven't managed to successfully auth yet
        if botconfig.PASS and not botconfig.SASL_AUTHENTICATION:
            cli.ns_identify(botconfig.USERNAME or botconfig.NICK,
                            botconfig.PASS,
                            nickserv=var.NICKSERV,
                            command=var.NICKSERV_IDENTIFY_COMMAND)

        # give bot operators an opportunity to do some custom stuff here if they wish
        event = Event("irc_connected", {})
        event.dispatch(var, cli)

        channels.Main = channels.add(botconfig.CHANNEL, cli)
        channels.Dummy = channels.add("*", cli)

        if botconfig.ALT_CHANNELS:
            for chan in botconfig.ALT_CHANNELS.split(","):
                channels.add(chan, cli)

        if botconfig.DEV_CHANNEL:
            channels.Dev = channels.add(botconfig.DEV_CHANNEL, cli)

        if var.LOG_CHANNEL:
            channels.add(var.LOG_CHANNEL, cli)

        users.Bot.change_nick(botconfig.NICK)

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

    request_caps = {"account-notify", "chghost", "extended-join", "multi-prefix"}

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
                    alog("Server does not support the SASL {0} mechanism".format(mech))
                    cli.quit()
                    raise ValueError("Server does not support the SASL {0} mechanism".format(mech))
            else:
                cli.send("CAP END")
        elif cmd == "NAK":
            # This isn't supposed to happen. The server claimed to support a
            # capability but now claims otherwise.
            alog("Server refused capabilities: {0}".format(" ".join(caps[0])))

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
                alog("EXTERNAL auth failed, retrying with PLAIN... ensure the client cert is set up in NickServ")
                cli.send("AUTHENTICATE PLAIN")
            else:
                alog("Authentication failed.  Did you fill the account name "
                     "in botconfig.USERNAME if it's different from the bot nick?")
                cli.quit()

    users.Bot = users.BotUser(cli, botconfig.NICK)
