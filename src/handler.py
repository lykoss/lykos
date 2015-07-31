# The bot commands implemented in here are present no matter which module is loaded

import base64
import imp
import socket
import traceback

from oyoyo.parse import parse_nick

import botconfig
import src.settings as var
from src import decorators, logger, wolfgame

log = logger("errors.log")
alog = logger(None)

hook = decorators.hook

def notify_error(cli, chan, target_logger):
    msg = "An error has occurred and has been logged."

    tb = traceback.format_exc()

    target_logger(tb)

    if (not botconfig.PASTEBIN_ERRORS) or (chan != botconfig.DEV_CHANNEL):
        # Don't send a duplicate message if DEV_CHANNEL is the current channel.
        cli.msg(chan, msg)

    if botconfig.PASTEBIN_ERRORS and botconfig.DEV_CHANNEL:
        try:
            with socket.socket() as sock:
                sock.connect(("termbin.com", 9999))
                sock.send(tb.encode("utf-8", "replace") + b"\n")
                url = sock.recv(1024).decode("utf-8")
        except socket.error:
            target_logger(traceback.format_exc())
        else:
            cli.msg(botconfig.DEV_CHANNEL, " ".join((msg, url)))


def on_privmsg(cli, rawnick, chan, msg, notice = False):

    try:
        prefixes = getattr(var, "STATUSMSG_PREFIXES")
    except AttributeError:
        pass
    else:
        if botconfig.IGNORE_HIDDEN_COMMANDS and chan[0] in prefixes:
            return

    if (notice and ((chan != botconfig.NICK and not botconfig.ALLOW_NOTICE_COMMANDS) or
                    (chan == botconfig.NICK and not botconfig.ALLOW_PRIVATE_NOTICE_COMMANDS))):
        return  # not allowed in settings

    if chan == botconfig.NICK:
        chan = parse_nick(rawnick)[0]

    for fn in decorators.COMMANDS[""]:
        try:
            fn.caller(cli, rawnick, chan, msg)
        except Exception:
            if botconfig.DEBUG_MODE:
                raise
            else:
                notify_error(cli, chan, log)


    for x in decorators.COMMANDS:
        if chan != parse_nick(rawnick)[0] and not msg.lower().startswith(botconfig.CMD_CHAR):
            break # channel message but no prefix; ignore
        if msg.lower().startswith(botconfig.CMD_CHAR+x):
            h = msg[len(x)+len(botconfig.CMD_CHAR):]
        elif not x or msg.lower().startswith(x):
            h = msg[len(x):]
        else:
            continue
        if not h or h[0] == " ":
            for fn in decorators.COMMANDS.get(x, []):
                try:
                    fn.caller(cli, rawnick, chan, h.lstrip())
                except Exception:
                    if botconfig.DEBUG_MODE:
                        raise
                    else:
                        notify_error(cli, chan, log)


def unhandled(cli, prefix, cmd, *args):
    if cmd in decorators.HOOKS:
        largs = list(args)
        for i,arg in enumerate(largs):
            if isinstance(arg, bytes): largs[i] = arg.decode('ascii')
        for fn in decorators.HOOKS.get(cmd, []):
            try:
                fn.func(cli, prefix, *largs)
            except Exception as e:
                if botconfig.DEBUG_MODE:
                    raise e
                else:
                    notify_error(cli, botconfig.CHANNEL, log)

def connect_callback(cli):
    @hook("endofmotd", hookid=294)
    @hook("nomotd", hookid=294)
    def prepare_stuff(cli, *args):
        # just in case we haven't managed to successfully auth yet
        if not botconfig.SASL_AUTHENTICATION:
            cli.ns_identify(botconfig.USERNAME or botconfig.NICK,
                            botconfig.PASS,
                            nickserv=var.NICKSERV,
                            command=var.NICKSERV_IDENTIFY_COMMAND)

        channels = {botconfig.CHANNEL}

        if botconfig.ALT_CHANNELS:
            channels.update(botconfig.ALT_CHANNELS.split(","))

        if botconfig.DEV_CHANNEL:
            channels.update(chan.lstrip("".join(var.STATUSMSG_PREFIXES)) for chan in botconfig.DEV_CHANNEL.split(","))

        cli.join(",".join(channels))

        if var.CHANSERV_OP_COMMAND:
            cli.msg(var.CHANSERV, var.CHANSERV_OP_COMMAND.format(channel=botconfig.CHANNEL))

        cli.nick(botconfig.NICK)  # very important (for regain/release)

        wolfgame.connect_callback(cli)

    def mustregain(cli, *blah):
        if not botconfig.PASS:
            return
        cli.ns_regain(nickserv=var.NICKSERV, command=var.NICKSERV_REGAIN_COMMAND)

    def mustrelease(cli, *rest):
        if not botconfig.PASS:
            return # prevents the bot from trying to release without a password
        cli.ns_release(nickserv=var.NICKSERV, command=var.NICKSERV_RELEASE_COMMAND)
        cli.nick(botconfig.NICK)

    @hook("unavailresource", hookid=239)
    @hook("nicknameinuse", hookid=239)
    def must_use_temp_nick(cli, *etc):
        cli.nick(botconfig.NICK+"_")
        cli.user(botconfig.NICK, "")

        hook.unhook(239)
        hook("unavailresource")(mustrelease)
        hook("nicknameinuse")(mustregain)

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
                    cli.cap("REQ", ":{0}".format(" ".join(common_caps)))
        elif cmd == "ACK":
            if "sasl" in caps:
                cli.send("AUTHENTICATE PLAIN")
            else:
                cli.cap("END")
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
            cli.cap("END")

        @hook("904")
        @hook("905")
        @hook("906")
        @hook("907")
        def on_failure_auth(cli, *etc):
            alog("Authentication failed.  Did you fill the account name "
                 "in botconfig.USERNAME if it's different from the bot nick?")
            cli.quit()



@hook("ping")
def on_ping(cli, prefix, server):
    cli.send('PONG', server)

# vim: set expandtab:sw=4:ts=4:
