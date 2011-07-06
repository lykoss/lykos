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



@cmd("!say")
def say(cli, nick, rest):  # To be removed later
    cli.msg(botconfig.CHANNEL, "{0} says: {1}".format(nick, rest))



def reset(cli):
    chan = botconfig.CHANNEL
    vars.PHASE = "none"

    if vars.TIMERS[0]:
        vars.TIMERS[0].cancel()
        vars.TIMERS[0] = None
    if vars.TIMERS[1]:
        vars.TIMERS[1].cancel()
        vars.TIMERS[1] = None

    cli.mode(chan, "-m")
    for plr in vars.list_players():
        cli.mode(chan, "-v", "{0} {0}!*@*".format(plr))
    for deadguy in vars.DEAD:
        cli.mode(chan, "-q", "{0} {0}!*@*".format(deadguy))

    vars.ROLES = {"person" : []}
    vars.CURSED = ""
    vars.CAN_START_TIME = timedelta(0)
    vars.GUNNERS = {}
    vars.WAITED = 0
    vars.VICTIM = ""
    vars.VOTES = {}



@pmcmd("!bye", admin_only=True)
@cmd("!bye", admin_only=True)
def forced_exit(cli, nick, *rest):  # Admin Only
    reset_game(cli, nick, botconfig.CHANNEL, None)
    cli.quit("Forced quit from admin")
    raise SystemExit



@cmd("!exec", admin_only=True)
def py(cli, nick, chan, rest):
    exec(rest)



# A decorator for standard game commands
def checks(f):
    def inner(*args):
        cli = args[0]
        nick = args[1]
        if vars.PHASE in ("none", "join"):
            cli.notice(nick, "No game is currently running.")
            return
        elif nick not in vars.list_players():
            cli.notice(nick, "You're not currently playing.")
            return
        f(*args)
    return inner



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
    def on_whoreply(cli, server, dunno, chan, dunno1,
                    dunno2, dunno3, user, status, dunno4):
        if not vars.PINGING: return
        if user in (botconfig.NICK, nick): return  # Don't ping self.

        if vars.PINGING and 'G' not in status and '+' not in status:
            # TODO: check if the user has AWAY'D himself
            TO_PING.append(user)



    @hook("endofwho")
    def do_ping(*args):
        if not vars.PINGING: return

        cli.msg(chan, "PING! "+" ".join(TO_PING))
        vars.PINGING = False

        HOOKS.pop("whoreply")
        HOOKS.pop("endofwho")

    cli.send("WHO "+chan)



@cmd("!sudo ping", admin_only=True)
def fpinger(cli, nick, chan, rest):
    vars.LAST_PING = None
    pinger(cli, nick, chan, rest)



@cmd("!join")
def join(cli, nick, chan, rest):
    if vars.PHASE == "none":
        cli.mode(chan, "+v", nick, nick+"!*@*")
        vars.ROLES["person"].append(nick)
        vars.PHASE = "join"
        vars.CAN_START_TIME = datetime.now() + timedelta(seconds=vars.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Werewolf. '+
                      'Type "!join" to join. Type "!start" to start the game. '+
                      'Type "!wait" to increase join wait time.').format(nick))
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
    cli.msg(chan, "{0}: There {3} {1}, and {2}.".format(nick,
                                                           ", ".join(message[0:-1]),
                                                           message[-1]),
                                                           vb)
                                                           
                                                      
                                                      
def hurry_up(cli):
    if vars.PHASE != "day": return

    chan = botconfig.CHANNEL
    pl = vars.list_players()
    avail = len(pl) - len(vars.WOUNDED)
    votesneeded = avail // 2 + 1
    
    found_dup = False
    max = (0, "")
    for votee, voters in iter(vars.VOTES.items()):
        if len(voters) > max[0]:
            max = (len(voters), votee)
            found_dup = False
        elif len(voters) == max[0]:
            found_dup = True
    if max[0] > 0 and not found_dup:
        vars.VOTES[max[1]] = [None] * votesneeded
        chk_decision(cli)  # Induce a lynch
    else:
        cli.msg(chan, "The sun is almost setting.")
        for plr in pl:
            vars.VOTES[plr] = [None] * (votesneeded - 1)
        
def chk_decision(cli):
    chan = botconfig.CHANNEL
    pl = vars.list_players()
    avail = len(pl) - len(vars.WOUNDED)
    votesneeded = avail // 2 + 1
    for votee, voters in iter(vars.VOTES.items()):
        if len(voters) >= votesneeded:
            cli.msg(botconfig.CHANNEL,
                    random.choice(vars.LYNCH_MESSAGES).format(
                    votee, vars.get_role(votee)))
            if del_player(cli, votee, True):
                transition_night(cli)



@checks
@cmd("!votes")
def show_votes(cli, nick, chan, rest):
    if not vars.VOTES.values():
        cli.msg(chan, nick+": No votes yet.")
        return
    elif vars.PHASE != "day":
        cli.notice(nick, "Voting is only during the day.")
        return
    if None in [x for voter in vars.VOTES.values() for x in voter]:
        cli.msg(chan, (nick+": Tiebreaker conditions.  Whoever "+
                      "receives the next vote will be lynched."))
        return
    
    votelist = ["{0}: {1} ({2})".format(votee,
                                        len(vars.VOTES[votee]),
                                        " ".join(vars.VOTES[votee]))
                for votee in votes_copy.keys()]
    cli.msg(chan, "{0}: {1}".format(nick, ", ".join(votelist)))

    pl = vars.list_players()
    avail = len(pl) - len(vars.WOUNDED)
    votesneeded = avail // 2 + 1
    cli.msg(chan, ("{0}: \u0002{1}\u0002 players, \u0002{2}\u0002 votes "+
                   "required to lynch, \u0002{3}\u0002 players available " +
                   "to vote.").format(nick, len(pl), votesneeded, avail))



def del_player(cli, nick, forced_death):
    cli.mode(botconfig.CHANNEL, "-v", "{0} {0}!*@*".format(nick))
    if vars.PHASE != "join":
        cli.mode(botconfig.CHANNEL, "+q", "{0} {0}!*@*".format(nick))
        vars.DEAD.append(nick)
    vars.del_player(nick)
    if vars.PHASE == "day" and not forced_death:  # didn't die from lynching
        chk_decision(cli)
    return True



def leave(cli, what, nick):
    if nick not in vars.list_players():  # not playing
        return
    msg = ""
    if what in ("!quit", "!leave"):
        msg = ("\u0002{0}\u0002 died of an unknown disease. "+
               "S/He was a \u0002{1}\u0002.")
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
    del_player(cli, nick, False)

cmd("!leave")(lambda cli, nick, *rest: leave(cli, "!leave", nick))
cmd("!quit")(lambda cli, nick, *rest: leave(cli, "!quit", nick))
hook("part")(lambda cli, nick, *rest: leave(cli, "part", nick))
hook("quit")(lambda cli, nick, *rest: leave(cli, "quit", nick))
hook("kick")(lambda cli, nick, *rest: leave(cli, "kick", nick))



def transition_day(cli):
    vars.PHASE = "day"
    chan = botconfig.CHANNEL

    vars.DAY_START_TIME = datetime.now()
    td = vars.DAY_START_TIME - vars.NIGHT_START_TIME
    vars.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    message = ("Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. "+
               "The villagers awake, thankful for surviving the night, "+
               "and search the village... ").format(min, sec)
    dead = []
    if not vars.VICTIM:
        message += random.choice(vars.NO_VICTIMS_MESSAGES)
        message += " All villagers, however, have survived."
        cli.msg(chan, message);
    # TODO: check if visited is harlot
    else:
        message += ("The dead body of \u0002{0}\u0002, a "+
                    "\u0002{1}\u0002, is found. Those remaining mourn his/her "+
                    "death.").format(vars.VICTIM, vars.get_role(vars.VICTIM))
        dead.append(vars.VICTIM)
        cli.msg(chan, message)
    # TODO: check if harlot also died

    for deadperson in dead:
        if not del_player(cli, deadperson, True):
            return

    cli.msg(chan, ("The villagers must now vote for whom to lynch. "+
                   'Use "!lynch <nick>" to cast your vote. 3 votes '+
                   'are required to lynch.'))
    
    if vars.DAY_TIME_LIMIT > 0:  # Time limit enabled
        t = threading.Timer(vars.DAY_TIME_LIMIT, hurry_up, [cli])
        vars.TIMERS[1] = t
        t.start()


def chk_nightdone(cli):
    if (len(vars.SEEN) == len(vars.ROLES["seer"]) and
        vars.VICTIM and vars.PHASE == "night"):
        if vars.TIMERS[0]:
            vars.TIMERS[0].cancel()  # cancel timer
            vars.TIMERS[0] = None
        if vars.PHASE == "night":  # Double check
            transition_day(cli)


@checks
@cmd("!lynch", "!vote")
def vote(cli, nick, chan, rest):
    if vars.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    pl = vars.list_players()
    pl_l = [x.strip().lower() for x in pl]
    rest = rest.split(" ")[0].strip().lower()
    if rest in pl_l:
        voted = pl[pl_l.index(rest)]
        candidates = vars.VOTES.keys()
        for voters in list(candidates):  # remove previous vote
            if nick in vars.VOTES[voters]:
                vars.VOTES[voters].remove(nick)
                if not vars.VOTES[voters] and voters != voted:
                    del vars.VOTES[voters]
        if voted not in vars.VOTES.keys():
            vars.VOTES[voted] = [nick]
        else:
            vars.VOTES[voted].append(nick)
        cli.msg(chan, ("\u0002{0}\u0002 votes for "+
                       "\u0002{1}\u0002.").format(nick, rest))
        chk_decision(cli)
    elif not rest:
        cli.notice(nick, "Not enough parameters.")
    else:
        cli.notice(nick, "\u0002{0}\u0002 is currently not playing.".format(rest))



@checks
@pmcmd("!kill", "kill")
def kill(cli, nick, rest):
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


@checks
@pmcmd("see", "!see")
def see(cli, nick, rest):
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
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if vars.CURSED == nick:
        role = "wolf"
    elif vars.TRAITOR == nick:
        role = "villager"
    else:
        role = vars.get_role(victim)
    cli.msg(nick, ("You have a vision; in this vision, "+
                    "you see that \u0002{0}\u0002 is a "+
                    "\u0002{1}\u0002!").format(victim, role))
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
    
    # Reset daytime variables
    vars.VOTES = {}
    if vars.TIMERS[1]:  # cancel daytime-limit timer
        vars.TIMERS[1].cancel()
        vars.TIMERS[1] = None
    vars.WOUNDED = ""
    
    # Reset nighttime variables
    vars.VICTIM = ""  # nickname of cursed villager
    vars.SEEN = []  # list of seers that have had visions
    vars.NIGHT_START_TIME = datetime.now()

    chan = botconfig.CHANNEL
    cli.msg(chan, ("It is now nighttime. All players "+
                   "check for PMs from me for instructions. "+
                   "If you did not receive one, simply sit back, "+
                   "relax, and wait patiently for morning."))
    
    if vars.NIGHT_TIME_LIMIT > 0:
        t = threading.Timer(vars.NIGHT_TIME_LIMIT, transition_day, [cli])
        vars.TIMERS[0] = t
        t.start()

    # send PMs
    ps = vars.list_players()
    for wolf in vars.ROLES["wolf"]:
        cli.msg(wolf, ('You are a \u0002wolf\u0002. It is your job to kill all the '+
                       'villagers. Use "kill <nick>" to kill a villager. Also, if '+
                       'you send a PM to me, it will be relayed to all other wolves.'))
        pl = ps[:]
        pl.remove(wolf)  # remove self from list
        for i, player in enumerate(pl):
            if vars.is_role(player, "wolf"):
                pl[i] = player + " (wolf)"
            elif vars.is_role(player, "traitor"):
                pl[i] = player + " (traitor)"
        cli.msg(wolf, "Players: "+", ".join(pl))

    for seer in vars.ROLES["seer"]:
        pl = ps[:]
        pl.remove(seer)  # remove self from list
        cli.msg(seer, ('You are a \u0002seer\u0002. '+
                      'It is your job to detect the wolves, you '+
                      'may have a vision once per night. '+
                      'Use "see <nick>" to see the role of a player.'))
        cli.msg(seer, "Players: "+", ".join(pl))



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

    for pcount in range(4, len(pl)+1):
        addroles = vars.ROLES_GUIDE.get(pcount)
        if addroles:
            nseers += addroles[0]
            nwolves += addroles[1]
            ncursed += addroles[2]
            ndrunk += addroles[3]
            nharlots += addroles[4]
            ntraitor += addroles[5]

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

    cli.msg(chan, ("{0}: Welcome to Werewolf, the popular detective/social party "+
                  "game (a theme of Mafia).").format(", ".join(vars.list_players())))
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
    cli.msg(chan, ("\u0002{0}\u0002 increased the wait time by "+
                  "{1} seconds.").format(nick, vars.EXTRA_WAIT))



@cmd("!reset", admin_only = True)
def reset_game(cli, nick, chan, rest):
    reset(cli)