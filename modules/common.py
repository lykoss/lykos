# The bot commands implemented in here are present no matter which module is loaded

import botconfig
from tools import decorators
import logging
import tools.moduleloader as ld
import traceback
from settings import common as var

def on_privmsg(cli, rawnick, chan, msg):
    currmod = ld.MODULES[ld.CURRENT_MODULE]
    
    if botconfig.IGNORE_HIDDEN_COMMANDS and (chan.startswith("@#") or chan.startswith("+#")):
        return
           
    if chan != botconfig.NICK:  #not a PM
        if currmod and "" in currmod.COMMANDS.keys():
            for fn in currmod.COMMANDS[""]:
                try:
                    fn(cli, rawnick, chan, msg)
                except Exception as e:
                    if botconfig.DEBUG_MODE:
                        raise e
                    else:
                        logging.error(traceback.format_exc())
                        cli.msg(chan, "An error has occurred and has been logged.")
            # Now that is always called first.
        for x in set(list(COMMANDS.keys()) + (list(currmod.COMMANDS.keys()) if currmod else list())):
            if x and msg.lower().startswith(botconfig.CMD_CHAR+x):
                h = msg[len(x)+1:]
                if not h or h[0] == " " or not x:
                    for fn in COMMANDS.get(x,[])+(currmod.COMMANDS.get(x,[]) if currmod else []):
                        try:
                            fn(cli, rawnick, chan, h.lstrip())
                        except Exception as e:
                            if botconfig.DEBUG_MODE:
                                raise e
                            else:
                                logging.error(traceback.format_exc())
                                cli.msg(chan, "An error has occurred and has been logged.")
            
    else:
        for x in set(list(PM_COMMANDS.keys()) + (list(currmod.PM_COMMANDS.keys()) if currmod else list())):
            if msg.lower().startswith(botconfig.CMD_CHAR+x):
                h = msg[len(x)+1:]
            elif not x or msg.lower().startswith(x):
                h = msg[len(x):]
            else:
                continue
            if not h or h[0] == " " or not x:
                for fn in PM_COMMANDS.get(x, [])+(currmod.PM_COMMANDS.get(x,[]) if currmod else []):
                    try:
                        fn(cli, rawnick, h.lstrip())
                    except Exception as e:
                        if botconfig.DEBUG_MODE:
                            raise e
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
PM_COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
pmcmd = decorators.generate(PM_COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True, permissions=False)

def connect_callback(cli):

    identified = False
    need_ghost = False

    def prepare_stuff(*args):    
        cli.join(botconfig.CHANNEL)
        cli.msg("ChanServ", "op "+botconfig.CHANNEL)
        
        cli.cap("REQ", "extended-join")
        cli.cap("REQ", "account-notify")
        
        ld.MODULES[ld.CURRENT_MODULE].connect_callback(cli)
        
        cli.nick(botconfig.NICK)  # just in case
        
    if botconfig.JOIN_AFTER_CLOAKED:
        prepare_stuff = hook("event_hosthidden", hookid=294)(prepare_stuff)
    else:
        prepare_stuff = hook("event_hosthidden", hookid=294)(prepare_stuff)
    
    @hook("mode")
    def check_if_identified(cli, spam, egg, m, *etc):
        if m == "+i":
            identified = True

    @hook("nicknameinuse")
    def mustghost(cli, *blah):
        cli.ns_identify(cli.password)
        cli.nick(botconfig.NICK+"_")
        if identified:
            cli.ns_ghost()
            cli.nick(botconfig.NICK)
        else:
            @hook("mode")
            def do_ghost(cli, spam, egg, m, *etc):
                if m == "+i":
                    cli.ns_ghost()
                                  
                    if not botconfig.JOIN_AFTER_CLOAKED:
                        prepare_stuff(cli)
                    
            @hook("quit", hookid=232)
            def after_ghost(cli, nick, reason):
                if nick == botconfig.NICK and reason == "Disconnected by services":
                    cli.nick(botconfig.NICK)
                    
                    decorators.unhook(HOOKS, 232)

    @hook("unavailresource")
    def mustrelease(cli, *blah):
        cli.ns_identify(cli.password)
        cli.nick(botconfig.NICK+"_")
        if identified:
            cli.ns_release()
            cli.nick(botconfig.NICK)
        else:
            @hook("mode")
            def do_release(cli, spam, egg, m, *etc):
                if m == "+i":
                    cli.ns_release()
                    
                    if not botconfig.JOIN_AFTER_CLOAKED:
                        prepare_stuff(cli)
                    
            @hook("notice", hookid=233)
            def after_release(cli, *etc):  #hopefully this works
                cli.nick(botconfig.NICK)
                    
                decorators.unhook(HOOKS, 233)
        
    if not botconfig.JOIN_AFTER_CLOAKED:  # join immediately
        pass
        # prepare_stuff(cli)
        
        
        
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
