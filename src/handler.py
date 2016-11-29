# The bot commands implemented in here are present no matter which module is loaded

import base64
import socket
import sys
import traceback

import botconfig
import src.settings as var
from src import decorators, wolfgame, channels, hooks, users, errlog as log, stream_handler as alog

hook = decorators.hook

def on_privmsg(cli, rawnick, chan, msg, *, notice=False):
    if notice and "!" not in rawnick or not rawnick: # server notice; we don't care about those
        return

    if not users.equals(chan, users.Bot.nick) and botconfig.IGNORE_HIDDEN_COMMANDS and not chan.startswith(tuple(hooks.Features["CHANTYPES"])):
        return

    if (notice and ((not users.equals(chan, users.Bot.nick) and not botconfig.ALLOW_NOTICE_COMMANDS) or
                    (users.equals(chan, users.Bot.nick) and not botconfig.ALLOW_PRIVATE_NOTICE_COMMANDS))):
        return  # not allowed in settings

    for fn in decorators.COMMANDS[""]:
        fn.caller(cli, rawnick, chan, msg)

    phase = var.PHASE
    for x in list(decorators.COMMANDS.keys()):
        if not users.equals(chan, users.Bot.nick) and not msg.lower().startswith(botconfig.CMD_CHAR):
            break # channel message but no prefix; ignore
        if msg.lower().startswith(botconfig.CMD_CHAR+x):
            h = msg[len(x)+len(botconfig.CMD_CHAR):]
        elif not x or msg.lower().startswith(x):
            h = msg[len(x):]
        else:
            continue
        if not h or h[0] == " ":
            for fn in decorators.COMMANDS.get(x, []):
                if phase == var.PHASE:
                    fn.caller(cli, rawnick, chan, h.lstrip())

def unhandled(cli, prefix, cmd, *args):
    for fn in decorators.HOOKS.get(cmd, []):
        fn.caller(cli, prefix, *args)

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
        if not botconfig.SASL_AUTHENTICATION:
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

    def mustregain(cli, server, bot_nick, nick, msg):
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
