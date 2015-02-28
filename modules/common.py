# The bot commands implemented in here are present no matter which module is loaded

import botconfig
from tools import decorators
import tools.moduleloader as ld
import traceback
from base64 import b64encode
from oyoyo.parse import parse_nick
import imp
from tools import logger
import socket
import settings.wolfgame as var

log = logger("errors.log")
alog = logger(None)


def notify_error(cli, chan, target_logger):
    msg = "An error has occurred and has been logged."

    tb = traceback.format_exc()

    target_logger(tb)

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
    currmod = ld.MODULES[ld.CURRENT_MODULE]

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

    if currmod and "" in currmod.COMMANDS.keys():
        for fn in currmod.COMMANDS[""]:
            try:
                fn(cli, rawnick, chan, msg)
            except Exception:
                if botconfig.DEBUG_MODE:
                    raise
                else:
                    notify_error(cli, chan, log)


    for x in set(list(COMMANDS.keys()) + (list(currmod.COMMANDS.keys()) if currmod else list())):
        if chan != parse_nick(rawnick)[0] and not msg.lower().startswith(botconfig.CMD_CHAR):
            break # channel message but no prefix; ignore
        if msg.lower().startswith(botconfig.CMD_CHAR+x):
            h = msg[len(x)+len(botconfig.CMD_CHAR):]
        elif not x or msg.lower().startswith(x):
            h = msg[len(x):]
        else:
            continue
        if not h or h[0] == " ":
            for fn in COMMANDS.get(x, []) + (currmod.COMMANDS.get(x, []) if currmod else []):
                try:
                    fn(cli, rawnick, chan, h.lstrip())
                except Exception:
                    if botconfig.DEBUG_MODE:
                        raise
                    else:
                        notify_error(cli, chan, log)

    
def __unhandled__(cli, prefix, cmd, *args):
    currmod = ld.MODULES[ld.CURRENT_MODULE]

    if cmd in set(list(HOOKS.keys())+(list(currmod.HOOKS.keys()) if currmod else list())):
        largs = list(args)
        for i,arg in enumerate(largs):
            if isinstance(arg, bytes): largs[i] = arg.decode('ascii')
        for fn in HOOKS.get(cmd, [])+(currmod.HOOKS.get(cmd, []) if currmod else []):
            try:
                fn(cli, prefix, *largs)
            except Exception as e:
                if botconfig.DEBUG_MODE:
                    raise e
                else:
                    notify_error(cli, botconfig.CHANNEL, log)

    
COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True, permissions=False)

def connect_callback(cli):

    def prepare_stuff(*args):    
        cli.join(botconfig.CHANNEL)
        cli.join(botconfig.ALT_CHANNELS)
        cli.join(",".join(chan.lstrip("".join(var.STATUSMSG_PREFIXES)) for chan in botconfig.DEV_CHANNEL.split(",")))
        cli.msg("ChanServ", "op "+botconfig.CHANNEL)
        
        cli.cap("REQ", "extended-join")
        cli.cap("REQ", "account-notify")
        
        try:
            ld.MODULES[ld.CURRENT_MODULE].connect_callback(cli)
        except AttributeError:
            pass # no connect_callback for this one
        
        cli.nick(botconfig.NICK)  # very important (for regain/release)
        
    prepare_stuff = hook("endofmotd", hookid=294)(prepare_stuff)

    def mustregain(cli, *blah):
        if not botconfig.PASS:
            return
        cli.ns_regain()                    
                    
    def mustrelease(cli, *rest):
        if not botconfig.PASS:
            return # prevents the bot from trying to release without a password
        cli.ns_release()
        cli.nick(botconfig.NICK)

    @hook("unavailresource", hookid=239)
    @hook("nicknameinuse", hookid=239)
    def must_use_temp_nick(cli, *etc):
        cli.nick(botconfig.NICK+"_")
        cli.user(botconfig.NICK, "")
        
        decorators.unhook(HOOKS, 239)
        hook("unavailresource")(mustrelease)
        hook("nicknameinuse")(mustregain)
        
    if botconfig.SASL_AUTHENTICATION:
    
        @hook("authenticate")
        def auth_plus(cli, something, plus):
            if plus == "+":
                nick_b = bytes(botconfig.USERNAME if botconfig.USERNAME else botconfig.NICK, "utf-8")
                pass_b = bytes(botconfig.PASS, "utf-8")
                secrt_msg = b'\0'.join((nick_b, nick_b, pass_b))
                cli.send("AUTHENTICATE " + b64encode(secrt_msg).decode("utf-8"))
    
        @hook("cap")
        def on_cap(cli, svr, mynick, ack, cap):
            if ack.upper() == "ACK" and "sasl" in cap:
                cli.send("AUTHENTICATE PLAIN")
                
        @hook("903")
        def on_successful_auth(cli, blah, blahh, blahhh):
            cli.cap("END")
            
        @hook("904")
        @hook("905")
        @hook("906")
        @hook("907")
        def on_failure_auth(cli, *etc):
            cli.quit()
            alog("Authentication failed.  Did you fill the account name "+
                  "in botconfig.USERNAME if it's different from the bot nick?")
               
        
        
@hook("ping")
def on_ping(cli, prefix, server):
    cli.send('PONG', server)

if botconfig.DEBUG_MODE:
    @cmd("module", admin_only = True)
    def ch_module(cli, nick, chan, rest):
        rest = rest.strip()
        if rest in ld.MODULES.keys():
            ld.CURRENT_MODULE = rest
            ld.MODULES[rest].connect_callback(cli)
            cli.msg(chan, "Module {0} is now active.".format(rest))
        else:
            cli.msg(chan, "Module {0} does not exist.".format(rest))
