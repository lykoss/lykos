# The bot commands implemented in here are present no matter which module is loaded

import base64
import socket
import sys
import threading
import time
import traceback
import functools

import botconfig
import src.settings as var
from src import decorators, wolfgame, events, channels, hooks, users, errlog as log, stream_handler as alog
from src.messages import messages
from src.utilities import reply, list_participants, get_role, get_templates
from src.dispatcher import MessageDispatcher
from src.decorators import handle_error

cmd = decorators.cmd
hook = decorators.hook

@handle_error
def on_privmsg(cli, rawnick, chan, msg, *, notice=False, force_role=None):
    if notice and "!" not in rawnick or not rawnick: # server notice; we don't care about those
        return

    user = users._get(rawnick, allow_none=True) # FIXME

    if users.equals(chan, users.Bot.nick): # PM
        target = users.Bot
    else:
        target = channels.get(chan, allow_none=True)

    if user is None or target is None:
        return

    wrapper = MessageDispatcher(user, target)

    if wrapper.public and botconfig.IGNORE_HIDDEN_COMMANDS and not chan.startswith(tuple(hooks.Features["CHANTYPES"])):
        return

    if (notice and ((wrapper.public and not botconfig.ALLOW_NOTICE_COMMANDS) or
                    (wrapper.private and not botconfig.ALLOW_PRIVATE_NOTICE_COMMANDS))):
        return  # not allowed in settings

    if force_role is None: # if force_role isn't None, that indicates recursion; don't fire these off twice
        for fn in decorators.COMMANDS[""]:
            fn.caller(cli, rawnick, chan, msg)

    parts = msg.split(sep=" ", maxsplit=1)
    key = parts[0].lower()
    if len(parts) > 1:
        message = parts[1].lstrip()
    else:
        message = ""

    if wrapper.public and not key.startswith(botconfig.CMD_CHAR):
        return # channel message but no prefix; ignore

    if key.startswith(botconfig.CMD_CHAR):
        key = key[len(botconfig.CMD_CHAR):]

    if not key: # empty key ("") already handled above
        return

    # Don't change this into decorators.COMMANDS[key] even though it's a defaultdict,
    # as we don't want to insert bogus command keys into the dict.
    cmds = []
    phase = var.PHASE
    if user.nick in list_participants():
        roles = {get_role(user.nick)} | set(get_templates(user.nick))
        if force_role is not None:
            roles &= {force_role} # only fire off role commands for the forced role

        common_roles = set(roles) # roles shared by every eligible role command
        have_role_cmd = False
        for fn in decorators.COMMANDS.get(key, []):
            if not fn.roles:
                cmds.append(fn)
                continue
            if roles.intersection(fn.roles):
                have_role_cmd = True
                cmds.append(fn)
                common_roles.intersection_update(fn.roles)

        if force_role is not None and not have_role_cmd:
            # Trying to force a non-role command with a role.
            # We allow non-role commands to execute if a role is forced if a role
            # command is also executed, as this would allow (for example) a bot admin
            # to add extra effects to all "kill" commands without needing to continually
            # update the list of roles which can use "kill". However, we don't want to
            # allow things like "wolf pstats" because that just doesn't make sense.
            return

        if not common_roles:
            # getting here means that at least one of the role_cmds is disjoint
            # from the others. For example, augur see vs seer see when a bare see
            # is executed. In this event, display a helpful error message instructing
            # the user to resolve the ambiguity.
            common_roles = set(roles)
            info = [0,0]
            for fn in cmds:
                fn_roles = roles.intersection(fn.roles)
                if not fn_roles:
                    continue
                for role1 in common_roles:
                    info[0] = role1
                    break
                for role2 in fn_roles:
                    info[1] = role2
                    break
                common_roles &= fn_roles
                if not common_roles:
                    break
            wrapper.pm(messages["ambiguous_command"].format(key, info[0], info[1]))
            return
    elif force_role is None:
        cmds = decorators.COMMANDS.get(key, [])

    for fn in cmds:
        if phase == var.PHASE:
            # FIXME: pass in var, wrapper, message instead of cli, rawnick, chan, message
            fn.caller(cli, rawnick, chan, message)

def unhandled(cli, prefix, cmd, *args):
    for fn in decorators.HOOKS.get(cmd, []):
        fn.caller(cli, prefix, *args)

def ping_server(cli):
    cli.send("PING :{0}".format(time.time()))

@cmd("latency", pm=True)
def latency(cli, nick, chan, rest):
    ping_server(cli)

    @hook("pong", hookid=300)
    def latency_pong(cli, server, target, ts):
        lat = round(time.time() - float(ts), 3)
        reply(cli, nick, chan, messages["latency"].format(lat, "" if lat == 1 else "s"))
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

        channels.Main = channels.add(botconfig.CHANNEL, cli)
        channels.Dummy = channels.add("*", cli)

        if botconfig.ALT_CHANNELS:
            for chan in botconfig.ALT_CHANNELS.split(","):
                channels.add(chan, cli)

        if botconfig.DEV_CHANNEL:
            channels.Dev = channels.add(botconfig.DEV_CHANNEL, cli)

        if var.LOG_CHANNEL:
            channels.add(var.LOG_CHANNEL, cli)

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

    request_caps = {"account-notify", "extended-join", "multi-prefix"}

    if botconfig.SASL_AUTHENTICATION:
        request_caps.add("sasl")

    supported_caps = set()

    @hook("cap")
    def on_cap(cli, svr, mynick, cmd, caps, star=None):
        if cmd == "LS":
            if caps == "*":
                # Multi-line LS
                supported_caps.update(star.split())
            else:
                supported_caps.update(caps.split())

                if botconfig.SASL_AUTHENTICATION and "sasl" not in supported_caps:
                    alog("Server does not support SASL authentication")
                    cli.quit()

                common_caps = request_caps & supported_caps

                if common_caps:
                    cli.send("CAP REQ " ":{0}".format(" ".join(common_caps)))
        elif cmd == "ACK":
            if "sasl" in caps:
                cli.send("AUTHENTICATE PLAIN")
            else:
                cli.send("CAP END")
        elif cmd == "NAK":
            # This isn't supposed to happen. The server claimed to support a
            # capability but now claims otherwise.
            alog("Server refused capabilities: {0}".format(" ".join(caps)))

    if botconfig.SASL_AUTHENTICATION:
        @hook("authenticate")
        def auth_plus(cli, something, plus):
            if plus == "+":
                account = (botconfig.USERNAME or botconfig.NICK).encode("utf-8")
                password = botconfig.PASS.encode("utf-8")
                auth_token = base64.b64encode(b"\0".join((account, account, password))).decode("utf-8")
                cli.send("AUTHENTICATE " + auth_token)

        @hook("903")
        def on_successful_auth(cli, blah, blahh, blahhh):
            cli.send("CAP END")

        @hook("904")
        @hook("905")
        @hook("906")
        @hook("907")
        def on_failure_auth(cli, *etc):
            alog("Authentication failed.  Did you fill the account name "
                 "in botconfig.USERNAME if it's different from the bot nick?")
            cli.quit()

    users.Bot = users.BotUser(cli, botconfig.NICK)

# vim: set sw=4 expandtab:
