from oyoyo.parse import parse_nick
import vars
import botconfig
import decorators
from datetime import datetime, timedelta
import threading
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
    reset_game(cli, nick, botconfig.CHANNEL, None)
    cli.quit("Forced quit from admin")
    raise SystemExit
        
@cmd("!exec", admin_only=True)
def py(cli, nick, chan, rest):
    exec(rest)

@cmd("!ping")
def pinger(cli, nick, chan, rest):
    if (vars.LAST_PING and 
        vars.LAST_PING + timedelta(seconds=300) > datetime.now()):
        cli.notice(nick, ("This command is ratelimited. " +
"Please wait a while before using it again."))
        return
    
    vars.LAST_PING = datetime.now()
    vars.PINGING = True
    TO_PING = []

    @hook("whoreply")
    def on_whoreply(server, dunno, chan, dunno1,
                    dunno2, dunno3, user, status, dunno4):
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
        vars.CAN_START_TIME = datetime.now() + timedelta(seconds=vars.MINIMUM_WAIT)
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
    if len(vars.ROLES["wolf"]) > 1:
        vb = "are"
    else:
        vb = "is"
    cli.msg(chan,
            "{0}: There {verb} {1}, and {2}.".format(nick,
                                                  ", ".join(message[0:-1]),
                                                  message[-1]), verb=vb)

def del_player(cli, nick, died_in_game = True):
    cli.mode(botconfig.CHANNEL, "-v", "{0} {0}!*@*".format(nick))
    if vars.PHASE != "join" and died_in_game:
        cli.mode(botconfig.CHANNEL, "+q", "{0} {0}!*@*".format(nick))
    vars.DEAD.append(nick)
    vars.del_player(nick)
                                                  
def leave(cli, what, nick):
    if nick not in vars.list_players():  # not playing
        return
    msg = ""
    if what in ("!quit", "!leave"):
        msg = ("\u0002{0}\u0002 died of an unknown disease. "+
               "S/He was a \u0002{1}\u0002.")
        died_in_game = True
    elif what == "part":
        msg = ("\u0002{0}\u0002 died due to eating poisonous berries. "+
               "Appears (s)he was a \u0002{1}\u0002.")
    elif what == "quit":
        msg = ("\u0002{0}\u0002 died due to a fatal attack by wild animals. "+
               "Appears (s)he was a \u0002{1}\u0002.")
    elif what == "kick":
        msg = ("\u0002{0}\u0002 died due to falling off a cliff. "+
               "Appears (s)he was a \u0002{1}\u0002.")
    msg = msg.format(nick, vars.get_role(nick))
    cli.msg(botconfig.CHANNEL, msg)
    del_player(cli, nick, died_in_game)

cmd("!leave")(lambda cli, nick, chan, *rest: leave(cli, "!leave", nick))
cmd("!quit")(lambda cli, nick, chan, *rest: leave(cli, "!quit", nick))
hook("part")(lambda cli, nick, chan, *rest: leave(cli, "part", nick))
hook("quit")(lambda cli, nick, chan, *rest: leave(cli, "quit", nick))
    
def transition_day(cli):
    chan = botconfig.CHANNEL

    vars.PHASE = "day"
    vars.DAY_START_TIME = datetime.now()
    td = vars.DAY_START_TIME - vars.NIGHT_START_TIME
    vars.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60
    
    message = "Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. \
The villagers awake, thankful for surviving the night, \
and search the village... ".format(min, sec)
    if not vars.VICTIM:
        message += random.choice(vars.NO_VICTIMS_MESSAGES)
        cli.msg(chan, message);
        return
    # TODO: check if visited is harlot
    
    dead = []
    
    message += "The dead body of \u0002{0}\u0002, a \
\u0002{1}\u0002, is found. Those remaining mourn his/her \
death.".format(vars.VICTIM, vars.get_role(vars.VICTIM))
    dead.append(vars.VICTIM)
    # TODO: check if harlot also died
    cli.msg(chan, message)
    
    for deadperson in dead:
        del_player(cli, deadperson, True)
        
        
    
    
def chk_nightdone(cli):
    if (len(vars.SEEN) == len(vars.ROLES["seer"]) and 
        vars.VICTIM and vars.PHASE == "night"):
        if vars.TIMERS[0]:
            vars.TIMERS[0].cancel()  # cancel timer
            vars.TIMERS[0] = None
        transition_day(cli)        
    
    
@pmcmd("!kill")
@pmcmd("kill")
def kill(cli, nick, rest):
    if vars.PHASE == "none":
        cli.msg(nick, "No game is currently running.")
        return
    if not nick in vars.list_players():
        cli.msg(nick, "You're currently playing")
        return
    if not (vars.is_role(nick, "wolf") or vars.is_role(nick, "traitor")):
        cli.msg(nick, "Only a wolf may use this command")
        return
    if vars.PHASE != "night":
        cli.msg(nick, "You may only kill people at night.")
        return
    victim = rest.split(" ")[0].strip()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if victim not in vars.list_players():
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if victim == nick:
        cli.msg(nick, "Suicide is bad.  Don't do it.")
        return
    if victim in vars.ROLES["wolf"]:
        cli.msg(nick, "You may only kill villagers, not other wolves")
        return
    vars.VICTIM = victim
    cli.msg(nick, "You have selected \u0002{0}\u0002 to be killed".format(victim))
    chk_nightdone(cli)
    
@pmcmd("see")
@pmcmd("!see")
def see(cli, nick, rest):
    if vars.PHASE == "none":
        cli.msg(nick, "No game is currently running.")
        return
    if not nick in vars.list_players():
        cli.msg(nick, "You're currently playing")
        return
    if not vars.is_role(nick, "seer"):
        cli.msg(nick, "Only a seer may use this command")
        return
    if vars.PHASE != "night":
        cli.msg(nick, "You may have visions at night.")
        return
    if nick in vars.SEEN:
        cli.msg(nick, "You may only have one vision per round.")
    victim = rest.split(" ")[0].strip()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if victim not in vars.list_players():
        cli.msg(nick,"\u0002{0}\u0002 is \
currently not playing.".format(victim))
        return
    if vars.CURSED == nick:
        role = "wolf"
    elif vars.TRAITOR == nick:
        role = "villager"
    else:
        role = vars.get_role(victim)
    cli.msg(nick, "You have a vision; in this vision, \
you see that \u0002{0}\u0002 is a \u0002{1}\u0002!".format(victim,
                                                          role))
    vars.SEEN.append(nick)
    chk_nightdone(cli)
    
@pmcmd("")
def relay(cli, nick, rest):
    badguys = vars.ROLES.get("wolf", []) + vars.ROLES.get("traitor", [])
    if len(badguys) > 1:
        if vars.is_role(nick, "wolf") or vars.is_role(nick, "traitor"):
            badguys.remove(nick)  #  remove self from list
            for badguy in badguys:
                cli.msg(badguy, "{0} says: {1}".format(nick, rest))

def transition_night(cli):
    vars.PHASE = "night"
    vars.VICTIM = ""  # nickname of cursed villager
    vars.SEEN = []  # list of seers that have had visions
    vars.NIGHT_START_TIME = datetime.now()
    
    chan = botconfig.CHANNEL
    cli.msg(chan, "It is now nighttime. All players \
check for PMs from me for instructions. If you did not receive \
one, simply sit back, relax, and wait patiently for morning.")
    
    t = threading.Timer(vars.NIGHT_TIME_LIMIT, transition_day, [cli])
    vars.TIMERS[0] = t
    t.start()
    
    # send PMs
    pl = vars.list_players()
    for wolf in vars.ROLES["wolf"]:
        cli.msg(wolf, 'You are a \u0002wolf\u0002. It is your job to kill all the \
villagers. Use "kill <nick>" to kill a villager. Also, if \
you send a PM to me, it will be relayed to all other wolves.')
        _pl = pl[:]
        _pl.remove(wolf)  # remove self from list
        for i, player in enumerate(_pl):
            if vars.is_role(player, "wolf"):
                _pl[i] = player + " (wolf)"
            elif vars.is_role(player, "traitor"):
                _pl[i] = player + " (traitor)"
        cli.msg(wolf, "Players: "+", ".join(_pl))

    for seer in vars.ROLES["seer"]:
        _pl = pl[:]
        _pl.remove(seer)  # remove self from list
        cli.msg(seer, 'You are a \u0002seer\u0002. \
It is your job to detect the wolves, you may have a vision once per night. \
Use "see <nick>" to see the role of a player.')
        cli.msg(seer, "Players: "+", ".join(_pl))

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
    now = datetime.now()
    dur = int((vars.CAN_START_TIME - now).total_seconds())
    if dur > 0:
        cli.msg(chan, "Please wait at least {0} more seconds.".format(dur))
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
    ntraitor = 0

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
        vars.CURSED = random.choice(vars.ROLES["villager"] + \
                                    vars.ROLES.get("harlot", []) +\
                                    vars.ROLES.get("village drunk", []))
    if ntraitor:
        possible = vars.ROLES["villager"]
        if ncursed:
            possible.remove(vars.CURSED)  # Cursed traitors are not allowed
        vars.TRAITOR = random.choice(possible)
    
    cli.msg(chan, "{0}: Welcome to Werewolf, the popular detective/social \
party game (a theme of Mafia).".format(", ".join(vars.list_players())))
    cli.mode(chan, "+m")
    
    vars.ORIGINAL_ROLES = dict(vars.ROLES)  # Make a copy
    vars.DAY_TIMEDELTA = timedelta(0)
    vars.NIGHT_TIMEDELTA = timedelta(0)
    vars.DEAD = []
    transition_night(cli)

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

    now = datetime.now()
    if now > vars.CAN_START_TIME:
        vars.CAN_START_TIME = now + timedelta(seconds=vars.EXTRA_WAIT)
    else:
        vars.CAN_START_TIME += timedelta(seconds=vars.EXTRA_WAIT)
    vars.WAITED += 1
    cli.msg(chan, "{0} increased the wait \
time by {1} seconds.".format(nick, vars.EXTRA_WAIT))

@cmd("!reset", admin_only = True)
def reset_game(cli, nick, chan, rest):
    vars.PHASE = "none"
    
    if vars.TIMERS[0]:
        vars.TIMERS[0].cancel()
        vars.TIMERS[0] = None
    cli.mode(chan, "-m")
    for plr in vars.list_players():
        cli.mode(chan, "-v", "{0} {0}!*@*".format(plr))
    for deadguy in vars.DEAD:
        cli.mode(chan, "-q", "{0} {0}!*@*".format(deadguy))
        
    vars.ROLES = {"person" : []}
    vars.ORIGINAL_ROLES = None
    vars.CURSED = ""
    vars.CAN_START_TIME = timedelta(0)
    vars.GUNNERS = {}
    vars.WAITED = 0
    vars.VICTIM = ""
    