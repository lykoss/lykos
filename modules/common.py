# The bot commands implemented in here are present no matter which module is loaded

import botconfig
from tools import decorators
import logging
import tools.moduleloader as ld
import traceback
from settings import common as var
from base64 import b64encode
from oyoyo.parse import parse_nick
import imp

def on_privmsg(cli, rawnick, chan, msg, notice = False):
    currmod = ld.MODULES[ld.CURRENT_MODULE]
    
    if botconfig.IGNORE_HIDDEN_COMMANDS and (chan.startswith("@#") or chan.startswith("+#")):
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
            except:
                if botconfig.DEBUG_MODE:
                    raise
                else:
                    logging.error(traceback.format_exc())
                    cli.msg(chan, "An error has occurred and has been logged.")

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
                except:
                    if botconfig.DEBUG_MODE:
                        raise
                    else:
                        logging.error(traceback.format_exc())
                        cli.msg(chan, "An error has occurred and has been logged.")
    
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
                    logging.error(traceback.format_exc())
                    cli.msg(botconfig.CHANNEL, "An error has occurred and has been logged.")
    else:
        logging.debug('Unhandled command {0}({1})'.format(cmd, [arg.decode('utf_8')
                                                              for arg in args
                                                              if isinstance(arg, bytes)]))

    
COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True, permissions=False)

def connect_callback(cli):

    def prepare_stuff(*args):    
        cli.join(botconfig.CHANNEL)
        cli.join(botconfig.ALT_CHANNELS)
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
            print("Authentication failed.  Did you fill the account name "+
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
