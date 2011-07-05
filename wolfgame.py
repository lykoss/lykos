from oyoyo.parse import parse_nick
import vars
import botconfig
import decorators
import time
import random

COMMANDS = {}
PM_COMMANDS = {}
HOOKS = {}    

cmd = decorators.generate(COMMANDS)
pmcmd = decorators.generate(PM_COMMANDS)
hook = decorators.generate(HOOKS)

# Game Logic Begins:

def connect_callback(cli):
    cli.identify(botconfig.PASS)
    cli.join(botconfig.CHANNEL)
    cli.msg("ChanServ", "op "+botconfig.CHANNEL)

def reset_game():
    vars.ROLES = {"person" : []}
    vars.PHASE = "none"

# Command Handlers:
@cmd("!say")
def say(cli, nick, rest):  # To be removed later
    cli.msg(botconfig.CHANNEL, "{0} says: {1}".format(nick, rest))
    
    
@pmcmd("!bye", admin_only=True)
@cmd("!bye", admin_only=True)
def forced_exit(cli, nick, *rest):  # Admin Only
    reset_game(cli, nick, rest[0], None)
    cli.quit("Forced quit from admin")
    raise SystemExit
        
@cmd("!exec")
def py(cli, nick, chan, rest):
    if nick in botconfig.ADMINS:
        exec(rest)

@cmd("!ping")
def pinger(cli, nick, chan, rest):
    if vars.LAST_PING + 300 > time.time():
        cli.notice(nick, "This command is ratelimited.  \
Please wait a while before using it again.")
        return
    
    vars.LAST_PING = time.time()
    vars.PINGING = True
    TO_PING = []

    @hook("whoreply")
    def on_whoreply(server, dunno, chan, dunno1, dunno2, dunno3, user, status, dunno4):
        if not vars.PINGING: return
        if user in (botconfig.NICK, nick): return  # Don't ping self.
        
        if vars.PINGING and 'G' not in status and '+' not in status:
            # TODO: check if the user has AWAY'D himself
            TO_PING.append(user)

    @hook("endofwho")
    def do_ping(*args):
        if not vars.PINGING: return
        
        chan = args[2]
        cli.msg(chan, "PING! "+" ".join(TO_PING))
        vars.PINGING = False
        
        HOOKS.pop("whoreply")
        HOOKS.pop("endofwho")
    
    cli.send("WHO "+chan)
        
@cmd("!join")
def join(cli, nick, chan, rest):
    if vars.PHASE == "none":
        cli.mode(chan, "+v", nick, nick+"!*@*")
        vars.ROLES["person"].append(nick)
        vars.PHASE = "join"
        vars.CAN_START_TIME = time.time() + vars.MINIMUM_WAIT
        cli.msg(chan, '\u0002{0}\u0002 has started a game of Werewolf. \
Type "!join" to join. Type "!start" to start the game. \
Type "!wait" to increase join wait time.'.format(nick))
    elif nick in vars.list_players():
        cli.notice(nick, "You're already playing!")
    elif vars.PHASE != "join":
        cli.notice(nick, "Sorry but the game is already running.  Try again next time.")
    else:
        cli.mode(chan, "+v", nick, nick+"!*@*")
        vars.ROLES["person"].append(nick)
        cli.msg(chan, '\u0002{0}\u0002 has joined the game.'.format(nick))

@cmd("!stats")
def stats(cli, nick, chan, rest):
    if vars.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
        
    pl = vars.list_players()
    if len(pl) > 1:
        cli.msg(chan, '{0}: \u0002{1}\u0002 players: {2}'.format(nick,
            len(pl), ", ".join(pl)))
    else:
        cli.msg(chan, '{0}: \u00021\u0002 player: {1}'.format(nick, pl[0]))
    
    if vars.PHASE == "join":
        return
    
    message = []
    for role in ("wolf", "seer", "harlot"):
        count = len(vars.ROLES.get(role,[]))
        if count > 1:
            message.append("\u0002(0}\u0002 {1}".format(count, vars.plural(role)))
        else:
            message.append("\u0002{0}\u0002 {1}".format(count, role))
    cli.msg(chan,
            "{0}: There are {1}, and {2}.".format(nick,
                                                  ", ".join(message[0:-1]),
                                                  message[-1]))

def transition_night(cli, chan):
    vars.PHASE = "night"
        
@cmd("!start")
def start(cli, nick, chan, rest):
    pl = vars.list_players()
    if vars.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if vars.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    now = time.time()
    if vars.CAN_START_TIME > now:
        cli.msg(chan, "Please wait at least {0} more seconds.".format(
                int(vars.CAN_START_TIME - now)))
        return
    
    if len(pl) < 4:
        cli.msg(chan, "{0}: Four or more players are required to play.".format(nick))
        return

    vars.ROLES = {}
    nharlots = 0
    nseers = 0
    nwolves = 0
    ndrunk = 0
    ncursed = 0

    if len(pl) >= 8:
        nharlots = 1
        nseers = 1
        nwolves = 2
        ndrunk = 1
        ncursed = 1
    elif(len(pl)) >= 6:
        nseers = 1
        nwolves = 1
        ndrunk = 1
        ncursed = 1
    else:
        nseers = 1
        nwolves = 1
    
    seer = random.choice(pl)
    vars.ROLES["seer"] = [seer]
    pl.remove(seer)
    if nharlots:
        harlots = random.sample(pl, nharlots)
        vars.ROLES["harlot"] = harlots
        for h in harlots:
            pl.remove(h)
    if nwolves:
        wolves = random.sample(pl, nwolves)
        vars.ROLES["wolf"] = wolves
        for w in wolves:
            pl.remove(w)
    if ndrunk:
        drunk = random.choice(pl)
        vars.ROLES["village drunk"] = [drunk]
        pl.remove(drunk)
    vars.ROLES["villager"] = pl
    
    if ncursed:
        CURSED = random.choice(var.ROLES["villager"] + \
                               var.ROLES.get("harlot", []) +\
                               var.ROLES.get("village drunk", []))
    
    cli.msg(chan, "{0}: Welcome to Werewolf, the popular detective/social \
party game (a theme of Mafia).".format(", ".join(vars.list_players())))
    cli.mode(chan, "+m")
    
    vars.GAME_START_TIME = time.time()
    vars.ORIGINAL_ROLES = dict(vars.ROLES)  # Make a copy
    transition_night(cli, chan)

@cmd("!wait")
def wait(cli, nick, chan, rest):
    pl = vars.list_players()
    if vars.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if vars.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    if vars.WAITED >= vars.MAXIMUM_WAITED:
        cli.msg(chan, "Limit has already been reached for extending the wait time.")
        return

    now = time.time()
    if now > vars.CAN_START_TIME:
        vars.CAN_START_TIME = now + vars.EXTRA_WAIT
    else:
        vars.CAN_START_TIME += vars.EXTRA_WAIT
    vars.WAITED += 1
    cli.msg(chan, "{0} increased the wait \
time by {1} seconds.".format(nick, vars.EXTRA_WAIT))

@cmd("!reset", admin_only = True)
def reset_game(cli, nick, chan, rest):
    vars.PHASE = "none"
    cli.mode(chan, "-m")
    for pl in vars.list_players():
        cli.mode(chan, "-v", pl)

    vars.ROLES = {"person" : []}
    vars.ORIGINAL_ROLES = None
    vars.CURSED = ""
    vars.GAME_START_TIME = 0
    vars.CAN_START_TIME = 0
    vars.GUNNERS = {}
    vars.WAITED = 0
    