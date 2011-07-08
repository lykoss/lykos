from oyoyo.parse import parse_nick
import var
import botconfig
import decorators
from datetime import datetime, timedelta
import threading
import random
import copy
from time import sleep
import re
import logging

COMMANDS = {}
PM_COMMANDS = {}
HOOKS = {}

cmd = decorators.generate(COMMANDS)
pmcmd = decorators.generate(PM_COMMANDS)
hook = decorators.generate(HOOKS, raw_nick=True)

# Game Logic Begins:

def connect_callback(cli):
    cli.identify(botconfig.PASS)
    cli.join(botconfig.CHANNEL)
    cli.msg("ChanServ", "op "+botconfig.CHANNEL)

    var.LAST_PING = 0  # time of last !ping
    var.ROLES = {"person" : []}
    var.PHASE = "none"  # "join", "day", or "night"
    var.TIMERS = [None, None]
    var.DEAD = []
    
    var.ORIGINAL_SETTINGS = {}
    var.DENIED_SETTINGS_CHANGE = []
    var.SETTINGS_CHANGE_OPPOSITION = []
    var.SETTINGS_CHANGE_REQUESTER = None



@cmd("!say")
def say(cli, nick, rest):  # To be removed later
    cli.msg(botconfig.CHANNEL, "{0} says: {1}".format(nick, rest))

    

def mass_mode(cli, md):
    """ Example: mass_mode((('+v', 'asdf'), ('-v','wobosd'))) """
    lmd = len(md)  # store how many mode changes to do
    for start_i in range(0, lmd, 4):  # 4 mode-changes at a time
        if start_i + 4 > lmd:  # If this is a remainder (mode-changes < 4)
            z = list(zip(*md[start_i:]))  # zip this remainder
            ei = lmd % 4  # len(z)
        else:
            z = list(zip(*md[start_i:start_i+4])) # zip four
            ei = 4 # len(z)
        # Now z equal something like [('+v', '-v'), ('asdf', 'wobosd')]
        arg1 = "".join(z[0])
        arg2 = " ".join(z[1]) + " " + " ".join([x+"!*@*" for x in z[1]])
        cli.mode(botconfig.CHANNEL, arg1, arg2)    
    


def reset_settings():
    for attr in list(var.ORIGINAL_SETTINGS.keys()):
        setattr(var, attr, var.ORIGINAL_SETTINGS[attr])
    dict.clear(var.ORIGINAL_SETTINGS)
    
    var.ORIGINAL_SETTINGS = {}
    var.DENIED_SETTINGS_CHANGE = []
    var.SETTINGS_CHANGE_OPPOSITION = []
    var.SETTINGS_CHANGE_REQUESTER = None
    
    
def reset(cli):
    chan = botconfig.CHANNEL
    var.PHASE = "none"

    if var.TIMERS[0]:
        var.TIMERS[0].cancel()
        var.TIMERS[0] = None
    if var.TIMERS[1]:
        var.TIMERS[1].cancel()
        var.TIMERS[1] = None

    cli.mode(chan, "-m")
    cmodes = []
    for plr in var.list_players():
        cmodes.append(("-v", plr))
    for deadguy in var.DEAD:
       cmodes.append(("-q", deadguy))
    mass_mode(cli, cmodes)
    var.DEAD = []

    var.ROLES = {"person" : []}
    
    reset_settings()
    var.DENIED_SETTINGS_CHANGE = []
    var.SETTINGS_CHANGE_OPPOSITION = []
    var.SETTINGS_CHANGE_REQUESTER = None
    

@pmcmd("!bye", admin_only=True)
@cmd("!bye", admin_only=True)
def forced_exit(cli, nick, *rest):  # Admin Only
    reset(cli)
    print("Quitting in 5 seconds.")
    dict.clear(COMMANDS)
    dict.clear(PM_COMMANDS)
    dict.clear(PM_COMMANDS)
    sleep(5)
    cli.quit("Forced quit from admin")
    raise SystemExit



@cmd("!exec", admin_only=True)
def py(cli, nick, chan, rest):
    try:
        exec(rest)
    except Exception as e:
        cli.msg(chan, str(type(e))+":"+str(e))



# A decorator for standard game commands
def checks(f):
    def inner(*args):
        cli = args[0]
        nick = args[1]
        if var.PHASE in ("none", "join"):
            cli.notice(nick, "No game is currently running.")
            return
        elif nick not in var.list_players():
            cli.notice(nick, "You're not currently playing.")
            return
        f(*args)
    return inner



@cmd("!ping")
def pinger(cli, nick, chan, rest):
    if (var.LAST_PING and
        var.LAST_PING + timedelta(seconds=300) > datetime.now()):
        cli.notice(nick, ("This command is ratelimited. " +
                          "Please wait a while before using it again."))
        return

    var.LAST_PING = datetime.now()
    var.PINGING = True
    TO_PING = []



    @hook("whoreply")
    def on_whoreply(cli, server, dunno, chan, dunno1,
                    dunno2, dunno3, user, status, dunno4):
        if not var.PINGING: return
        if user in (botconfig.NICK, nick): return  # Don't ping self.

        if var.PINGING and 'G' not in status and '+' not in status:
            # TODO: check if the user has !AWAY'D himself
            TO_PING.append(user)



    @hook("endofwho")
    def do_ping(*args):
        if not var.PINGING: return

        cli.msg(chan, "PING! "+" ".join(TO_PING))
        var.PINGING = False

        HOOKS.pop("whoreply")
        HOOKS.pop("endofwho")

    cli.send("WHO "+chan)



#def chk_bed
    
    
    
@cmd("!sudo ping", admin_only=True)
def fpinger(cli, nick, chan, rest):
    var.LAST_PING = None
    pinger(cli, nick, chan, rest)



@cmd("!join")
def join(cli, nick, chan, rest):
    if var.PHASE == "none":
        cli.mode(chan, "+v", nick, nick+"!*@*")
        var.ROLES["person"].append(nick)
        var.PHASE = "join"
        var.WAITED = 0
        var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.MINIMUM_WAIT)
        cli.msg(chan, ('\u0002{0}\u0002 has started a game of Werewolf. '+
                      'Type "!join" to join. Type "!start" to start the game. '+
                      'Type "!wait" to increase join wait time.').format(nick))
    elif nick in var.list_players():
        cli.notice(nick, "You're already playing!")
    elif var.PHASE != "join":
        cli.notice(nick, "Sorry but the game is already running.  Try again next time.")
    else:
        cli.mode(chan, "+v", nick, nick+"!*@*")
        var.ROLES["person"].append(nick)
        cli.msg(chan, '\u0002{0}\u0002 has joined the game.'.format(nick))



@cmd("!stats")
def stats(cli, nick, chan, rest):
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return

    pl = var.list_players()
    if len(pl) > 1:
        cli.msg(chan, '{0}: \u0002{1}\u0002 players: {2}'.format(nick,
            len(pl), ", ".join(pl)))
    else:
        cli.msg(chan, '{0}: \u00021\u0002 player: {1}'.format(nick, pl[0]))

    if var.PHASE == "join":
        return

    message = []
    f = False
    l1 = [k for k in var.ROLES.keys()
          if var.ROLES[k]]
    l2 = [k for k in var.ORIGINAL_ROLES.keys()
          if var.ORIGINAL_ROLES[k]]
    for role in set(l1+l2):
        count = len(var.ROLES[role])
        if not f and count>1:
            vb = "are"
            f = True
        else:
            vb = "is"
        if count > 1:
            message.append("\u0002{0}\u0002 {1}".format(count, var.plural(role)))
        else:
            message.append("\u0002{0}\u0002 {1}".format(count if count else "no", role))
    cli.msg(chan, "{0}: There {3} {1}, and {2}.".format(nick,
                                                        ", ".join(message[0:-1]),
                                                        message[-1],
                                                        vb))



def hurry_up(cli):
    if var.PHASE != "day": return

    chan = botconfig.CHANNEL
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1

    found_dup = False
    maxfound = (0, "")
    for votee, voters in iter(var.VOTES.items()):
        if len(voters) > maxfound[0]:
            maxfound = (len(voters), votee)
            found_dup = False
        elif len(voters) == maxfound[0]:
            found_dup = True
    if maxfound[0] > 0 and not found_dup:
        cli.msg(chan, "The sun sets.")
        var.VOTES[maxfound[1]] = [None] * votesneeded
        chk_decision(cli)  # Induce a lynch
    else:
        cli.msg(chan, "The sun is almost setting.")
        for plr in pl:
            var.VOTES[plr] = [None] * (votesneeded - 1)

def chk_decision(cli):
    chan = botconfig.CHANNEL
    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1
    for votee, voters in iter(var.VOTES.items()):
        if len(voters) >= votesneeded:
            cli.msg(botconfig.CHANNEL,
                    random.choice(var.LYNCH_MESSAGES).format(
                    votee, var.get_role(votee)))
            if del_player(cli, votee, True):
                transition_night(cli)



@checks
@cmd("!votes")
def show_votes(cli, nick, chan, rest):
    if var.PHASE != "day":
        cli.notice(nick, "Voting is only during the day.")
        return
    elif not var.VOTES.values():
        cli.msg(chan, nick+": No votes yet.")
        return
    if None in [x for voter in var.VOTES.values() for x in voter]:
        cli.msg(chan, (nick+": Tiebreaker conditions.  Whoever "+
                      "receives the next vote will be lynched."))
        return

    votelist = ["{0}: {1} ({2})".format(votee,
                                        len(var.VOTES[votee]),
                                        " ".join(var.VOTES[votee]))
                for votee in var.VOTES.keys()]
    cli.msg(chan, "{0}: {1}".format(nick, ", ".join(votelist)))

    pl = var.list_players()
    avail = len(pl) - len(var.WOUNDED)
    votesneeded = avail // 2 + 1
    cli.msg(chan, ("{0}: \u0002{1}\u0002 players, \u0002{2}\u0002 votes "+
                   "required to lynch, \u0002{3}\u0002 players available " +
                   "to vote.").format(nick, len(pl), votesneeded, avail))



def chk_traitor(cli):
    for tt in var.ROLES["traitor"]:
        var.ROLES["wolf"].append(tt)
        var.ROLES["traitor"].remove(tt)
        cli.msg(tt, ('HOOOOOOOOOWL. You have become... a wolf!\n'+
                     'It is up to you to avenge your fallen leaders!'))

                     

def chk_win(cli):
    """ Returns True if someone won """

    chan = botconfig.CHANNEL
    lpl = len(var.list_players())
    if lpl == 0:
        cli.msg(chan, "No more players remaining. Game ended.")
        reset(cli)
        return True
    if var.PHASE == "join":
        return False
    elif (len(var.ROLES["wolf"])+
          len(var.ROLES["traitor"])+
          len(var.ROLES["werecrow"])) >= lpl / 2:
        cli.msg(chan, ("Game over! There are the same number of wolves as "+
                       "villagers. The wolves eat everyone, and win."))
    elif (not var.ROLES["wolf"] and
          not var.ROLES["traitor"] and 
          not var.ROLES["werecrow"]):
        cli.msg(chan, ("Game over! All the wolves are dead! The villagers "+
                       "chop them up, BBQ them, and have a hearty meal."))
    elif not len(var.ROLES["wolf"]) and var.ROLES["traitor"]:
        chk_traitor(cli)
        cli.msg(chan, ('\u0002The villagers, during their celebrations, are '+
                       'frightened as they hear a loud howl. The wolves are '+
                       'not gone!\u0002'))
        return False
    else:
        return False

    if var.DAY_START_TIME:
        now = datetime.now()
        td = now - var.DAY_START_TIME
        var.DAY_TIMEDELTA += td
    if var.NIGHT_START_TIME:
        now = datetime.now()
        td = now - var.NIGHT_START_TIME
        var.NIGHT_TIMEDELTA += td

    daymin, daysec = var.DAY_TIMEDELTA.seconds // 60, var.DAY_TIMEDELTA.seconds % 60
    nitemin, nitesec = var.NIGHT_TIMEDELTA.seconds // 60, var.NIGHT_TIMEDELTA.seconds % 60
    total = var.DAY_TIMEDELTA + var.NIGHT_TIMEDELTA
    tmin, tsec = total.seconds // 60, total.seconds % 60
    cli.msg(chan, ("Game lasted \u0002{0:0>2}:{1:0>2}\u0002. " +
                   "\u0002{2:0>2}:{3:0>2}\u0002 was day. " +
                   "\u0002{4:0>2}:{5:0>2}\u0002 was night. ").format(tmin, tsec,
                                                                     daymin, daysec,
                                                                     nitemin, nitesec))

    roles_msg = []
    var.ORIGINAL_ROLES["cursed villager"] = var.CURSED
    for role in var.ORIGINAL_ROLES.keys():
        if len(var.ORIGINAL_ROLES[role]) == 0 or role == "villager":
            continue
        elif len(var.ORIGINAL_ROLES[role]) == 2:
            msg = "The {1} were \u0002{0[0]}\u0002 and \u0002{0[1]}\u0002."
            roles_msg.append(msg.format(var.ORIGINAL_ROLES[role], var.plural(role)))
        elif len(var.ORIGINAL_ROLES[role]) == 1:
            roles_msg.append("The {1} was \u0002{0[0]}\u0002.".format(var.ORIGINAL_ROLES[role],
                                                                      role))
        else:
            msg = "The {2} were {0}, and \u0002{1}\u0002."
            nickslist = ["\u0002"+x+"\u0002" for x in var.ORIGINAL_ROLES[role][0:-1]]
            roles_msg.append(msg.format(", ".join(nickslist),
                                                  var.ORIGINAL_ROLES[role][-1],
                                                  var.plural(role)))
    cli.msg(chan, " ".join(roles_msg))

    reset(cli)
    # TODO: Reveal roles here
    return True



def del_player(cli, nick, forced_death = False):
    """
    Returns: False if one side won.
    arg: forced_death = True when lynched.
    """

    cmode = []
    cmode.append(("-v", nick))
    var.del_player(nick)
    ret = True
    if var.PHASE == "join":
        # Died during the joining process as a person
        mass_mode(cli, cmode)
        return not chk_win(cli)
    if var.PHASE != "join" and ret:
        # Died during the game, so quiet!
        cmode.append(("+q", nick))
        mass_mode(cli, cmode)
        var.DEAD.append(nick)
        ret = not chk_win(cli)
    if var.PHASE in ("night", "day") and ret:
        # remove him from variables if he is in there
        if var.VICTIM == nick:
            var.VICTIM = ""
        for x in (var.OBSERVED, var.HVISITED):
            keys = list(x.keys())
            for k in keys:
                if k == nick:
                    del x[k]
                elif x[k] == nick:
                    del x[k]
        if nick in var.GUNNERS.keys():
            del var.GUNNERS[nick]
        if nick in var.CURSED:
            var.CURSED.remove(nick)
    if var.PHASE == "day" and not forced_death and ret:  # didn't die from lynching
        if nick in var.VOTES.keys():
            del var.VOTES[nick]  #  Delete his votes
        for k in var.VOTES.keys():
            if nick in var.VOTES[k]:
                var.VOTES[k].remove(nick)
        chk_decision(cli)
    return ret
    
    
@hook("ping")
def on_ping(cli, prefix, server):
    cli.send('PONG', server)    
    
@hook("nick")
def on_nick(cli, prefix, nick):
    prefix = parse_nick(prefix)[0]
    if prefix in var.list_players():
        r = var.ROLES[var.get_role(prefix)]
        r.append(nick)
        r.remove(prefix)
        
        if var.PHASE in ("night", "day"):
            if var.VICTIM == prefix:
                var.VICTIM = nick
            kvp = []
            for dictvar in (var.HVISITED, var.OBSERVED):
                for a,b in dictvar.items():
                    if a == prefix:
                        a = nick
                    if b == prefix:
                        b = nick
                    kvp.append((a,b))
                dictvar.update(kvp)
                if prefix in dictvar.keys():
                    del dictvar[prefix]
            if prefix in var.SEEN:
                var.SEEN.remove(prefix)
                var.SEEN.append(nick)
            if nick in var.GUNNERS.keys():
                del var.GUNNERS[nick]
            if nick in var.CURSED:
                var.CURSED.remove(nick)
                
        if var.PHASE == "day":
            if prefix in var.WOUNDED:
                var.WOUNDED.remove(prefix)
                var.WOUNDED.append(nick)
            if prefix in var.VOTES:
                var.VOTES[nick] = var.VOTES.pop(prefix)
            for v in var.VOTES.values():
                if prefix in v:
                    v.remove(prefix)
                    v.append(nick)
    else:
        return
    
    
def leave(cli, what, nick):
    if var.PHASE == "none" and what.startswith("!"):
        cli.notice(nick, "No game is currently running.")
        return
    elif var.PHASE == "none":
        return
    if nick not in var.list_players() and what.startswith("!"):  # not playing
        cli.notice(nick, "You're not currently playing.")
        return
    elif nick not in var.list_players():
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
    msg = msg.format(nick, var.get_role(nick))
    cli.msg(botconfig.CHANNEL, msg)
    del_player(cli, nick)

cmd("!leave")(lambda cli, nick, *rest: leave(cli, "!leave", nick))
cmd("!quit")(lambda cli, nick, *rest: leave(cli, "!quit", nick))
#Functions decorated with hook do not parse the nick by default
hook("part")(lambda cli, nick, *reset: leave(cli, "part", parse_nick(nick)[0]))
hook("quit")(lambda cli, nick, *rest: leave(cli, "quit", parse_nick(nick)[0]))
hook("kick")(lambda cli, nick, *rest: leave(cli, "kick", parse_nick(nick)[0]))



def begin_day(cli):
    chan = botconfig.CHANNEL
    
    # Reset nighttime variables
    var.VICTIM = ""  # nickname of kill victim
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    
    cli.msg(chan, ("The villagers must now vote for whom to lynch. "+
                   'Use "!lynch <nick>" to cast your vote. 3 votes '+
                   'are required to lynch.'))

    if var.DAY_TIME_LIMIT > 0:  # Time limit enabled
        t = threading.Timer(var.DAY_TIME_LIMIT, hurry_up, [cli])
        var.TIMERS[1] = t
        t.start()
        
        
        
def transition_day(cli):
    var.PHASE = "day"
    chan = botconfig.CHANNEL

    # Reset daytime variables
    var.VOTES = {}
    var.WOUNDED = []
    var.DAY_START_TIME = datetime.now()
    if not var.NIGHT_START_TIME:
        for plr in var.list_players():
            cli.msg(plr, "You are a \u0002{0}\u0002.".format(var.get_role(plr)))
        begin_day(cli)
        return
    
    td = var.DAY_START_TIME - var.NIGHT_START_TIME
    var.NIGHT_START_TIME = None
    var.NIGHT_TIMEDELTA += td
    min, sec = td.seconds // 60, td.seconds % 60

    message = [("Night lasted \u0002{0:0>2}:{1:0>2}\u0002. It is now daytime. "+
               "The villagers awake, thankful for surviving the night, "+
               "and search the village... ").format(min, sec)]
    dead = []
    crowonly = var.ROLES["werecrow"] and not var.ROLES["wolf"]
    for crow, target in iter(var.OBSERVED.items()):
        if target in var.ROLES["harlot"]+var.ROLES["seer"]:
            cli.msg(crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was not in "+
                          "bed at night, and you fly back to your house.").format(target))
        elif target not in var.ROLES["village drunk"]:
            cli.msg(crow, ("As the sun rises, you conclude that \u0002{0}\u0002 was sleeping "+
                          "all night long, and you fly back to your house.").format(target))
    if not var.VICTIM:
        message.append(random.choice(var.NO_VICTIMS_MESSAGES) + 
                    " All villagers, however, have survived.")
    elif var.VICTIM in var.ROLES["harlot"]:  # Attacked harlot, yay no deaths
        if var.HVISITED.get(var.VICTIM):
            message.append("The wolves' selected victim was a harlot, "+
                           "but she wasn't home.")
    if var.VICTIM and (var.VICTIM not in var.ROLES["harlot"] or   # not a harlot
                          not var.HVISITED.get(var.VICTIM)):   # harlot stayed home
        message.append(("The dead body of \u0002{0}\u0002, a "+
                        "\u0002{1}\u0002, is found. Those remaining mourn his/her "+
                        "death.").format(var.VICTIM, var.get_role(var.VICTIM)))
        dead.append(var.VICTIM)
    if var.VICTIM in var.HVISITED.values():  #  victim was visited by some harlot
        for hlt in var.HVISITED.keys():
            if var.HVISITED[hlt] == var.VICTIM:
                message.append(("\u0002{0}\u0002, a harlot, made the unfortunate mistake of "+
                                "visiting the victim's house last night and is "+
                                "now dead.").format(hlt))
                dead.append(hlt)
    # TODO: check if harlot also died
    for harlot in var.ROLES["harlot"]:
        if var.HVISITED.get(harlot) in var.ROLES["wolf"]:
            message.append(("\u0002{0}\u0002, a harlot, made the unfortunate mistake of "+
                            "visiting a wolf's house last night and is "+
                            "now dead.").format(harlot))
            dead.append(harlot)
    for crow, target in iter(var.OBSERVED.items()):
        if (target in var.ROLES["harlot"] and 
            target in var.HVISITED.keys() and 
            target not in dead):
            # Was visited by a crow
            cli.msg(target, ("You suddenly remember that you were startled by the loud "+
                            "sound of the flapping of wings during the walk back home."))
        elif target in var.ROLES["village drunk"]:
            # Crow dies because of tiger (HANGOVER)
            cli.msg(chan, ("The bones of \u0002{0}\u0002, a werecrow, "+
                           "were found near the village drunk's house. "+
                           "The drunk's pet tiger probably ate him.").format(crow))
            dead.append(crow)
    for deadperson in dead:
        if not del_player(cli, deadperson):
            return
    cli.msg(chan, "\n".join(message))
    begin_day(cli)
    

def chk_nightdone(cli):
    if (len(var.SEEN) == len(var.ROLES["seer"]) and  # Seers have seen.
        len(var.HVISITED.keys()) == len(var.ROLES["harlot"]) and  # harlots have visited.
            (var.VICTIM or 
                (var.ROLES["werecrow"] == 1 and  # Wolves have done their stuff
                    not var.ROLES["wolf"] and var.OBSERVED) or
            (not var.ROLES["wolf"] + var.ROLES["werecrow"])) and
         var.PHASE == "night"):  # no wolves
        if var.TIMERS[0]:
            var.TIMERS[0].cancel()  # cancel timer
            var.TIMERS[0] = None
        if var.PHASE == "night":  # Double check
            transition_day(cli)


@checks
@cmd("!lynch", "!vote")
def vote(cli, nick, chan, rest):
    if var.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    pl = var.list_players()
    pl_l = [x.strip().lower() for x in pl]
    rest = re.split("\s+",rest)[0].strip().lower()
    if rest in pl_l:
        if nick in var.WOUNDED:
            cli.msg(chan, ("{0}: You are wounded and resting, "+
                          "thus you are unable to vote for the day."))
        voted = pl[pl_l.index(rest)]
        lcandidates = list(var.VOTES.keys())
        for voters in lcandidates:  # remove previous vote
            if nick in var.VOTES[voters]:
                var.VOTES[voters].remove(nick)
                if not var.VOTES.get(voters) and voters != voted:
                    del var.VOTES[voters]
                break
        if voted not in var.VOTES.keys():
            var.VOTES[voted] = [nick]
        else:
            var.VOTES[voted].append(nick)
        cli.msg(chan, ("\u0002{0}\u0002 votes for "+
                       "\u0002{1}\u0002.").format(nick, rest))
        chk_decision(cli)
    elif not rest:
        cli.notice(nick, "Not enough parameters.")
    else:
        cli.notice(nick, "\u0002{0}\u0002 is currently not playing.".format(rest))



@checks
@cmd("!retract")
def retract(cli, nick, chan, rest):
    if var.PHASE != "day":
        cli.notice(nick, ("Lynching is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return

    candidates = var.VOTES.keys()
    for voter in list(candidates):
        if nick in var.VOTES[voter]:
            var.VOTES[voter].remove(nick)
            if not var.VOTES[voter]:
                del var.VOTES[voter]
            cli.msg(chan, "\u0002{0}\u0002 retracted his/her vote.".format(nick))
            break
    else:
        cli.notice(nick, "You haven't voted yet.")



@checks
@cmd("!shoot", "shoot")
def shoot(cli, nick, chan, rest):
    if var.PHASE != "day":
        cli.notice(nick, ("Shooting is only allowed during the day. "+
                          "Please wait patiently for morning."))
        return
    if nick not in var.GUNNERS.keys():
        cli.msg(nick, "You don't have a gun.")
        return
    elif not var.GUNNERS[nick]:
        cli.msg(nick, "You don't have any more bullets.")
        return
    victim = re.split("\s+",rest)[0].strip().lower()
    if not victim:
        cli.notice(nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.notice(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]
    rand = random.random()
    if nick in var.ROLES["village drunk"]:
        chances = var.DRUNK_GUN_CHANCES
    else:
        chances = var.GUN_CHANCES
    if rand <= chances[0]:
        cli.msg(chan, ("\u0002{0}\u0002 shoots \u0002{1}\u0002 with "+
                       "a silver bullet!").format(nick, victim))
        victimrole = var.get_role(victim)
        if victimrole in ("wolf", "werecrow"):
            cli.msg(chan, ("\u0002{0}\u0002 is a wolf, and is dying from "+
                           "the silver bullet.").format(victim))
            if not del_player(cli, victim):
                return
        elif random.random() <= var.MANSLAUGHTER_CHANCE:
            cli.msg(chan, ("\u0002{0}\u0002 is a not a wolf "+
                           "but was accidentally fatally injured.").format(victim))
            cli.msg(chan, "Appears (s)he was a \u0002{0}\u0002.".format(victimrole))
            if not del_player(cli, victim):
                return
        else:
            cli.msg(chan, ("\u0002{0}\u0002 is a villager and is injured but "+
                          "will have a full recovery. S/He will be resting "+
                          "for the day.").format(victim))
            var.WOUNDED.append(victim)
            chk_decision(cli)
    elif rand <= chances[0] + chances[1]:
        cli.msg(chan, "\u0002{0}\u0002 is a lousy shooter.  S/He missed!".format(nick))
        var.GUNNERS[nick] -= 1
    else:
        cli.msg(chan, ("\u0002{0}\u0002 should clean his/her weapons more often. "+
                      "The gun exploded and killed him/her!").format(nick))
        cli.msg(chan, "Appears that (s)he was a \u0002{0}\u0002.".format(var.get_role(nick)))
        if not del_player(cli, nick):
            return  # Someone won.
        
@checks
@pmcmd("!kill", "kill")
def kill(cli, nick, rest):
    role = var.get_role(nick)
    if role not in ('wolf', 'werecrow'):
        cli.msg(nick, "Only a wolf may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only kill people at night.")
        return
    victim = re.split("\s+",rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if role == "werecrow":  # Check if flying to observe
        if var.OBSERVED.get(nick):
            cli.msg(nick, ("You are flying to \u0002{0}'s\u0002 house, and "+
                          "therefore you don't have the time "+
                          "and energy to kill a villager.").format(var.OBSERVED[nick]))
            return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if victim == nick.lower():
        cli.msg(nick, "Suicide is bad.  Don't do it.")
        return
    if victim in var.ROLES["wolf"]:
        cli.msg(nick, "You may only kill villagers, not other wolves")
        return
    var.VICTIM = pl[pll.index(victim)]
    cli.msg(nick, "You have selected \u0002{0}\u0002 to be killed".format(var.VICTIM))
    chk_nightdone(cli)



@checks
@pmcmd("observe", "!observe")
def observe(cli, nick, rest):
    if not var.is_role(nick, "werecrow"):
        cli.msg(nick, "Only a werecrow may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only transform into a crow at night.")
        return
    victim = re.split("\s+", rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if victim not in pll:
        cli.msg(nick, "\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]
    if victim == nick.lower():
        cli.msg(nick, "Instead of doing that, you should probably go kill someone.")
        return
    if var.get_role(victim) in ("werecrow", "traitor", "wolf"):
        cli.msg(nick, "Flying to another wolf's house is a waste of time.")
        return
    var.OBSERVED[nick] = victim
    cli.msg(nick, ("You transform into a large crow and start your flight "+
                   "to \u0002{0}'s\u0002 house. You will return after "+
                  "collecting your observations when day begins.").format(victim))
        
    
    
@checks
@pmcmd("visit", "!visit")
def hvisit(cli, nick, rest):
    if not var.is_role(nick, "harlot"):
        cli.msg(nick, "Only a harlot may use this command.")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only visit someone at night.")
        return
    if var.HVISITED.get(nick):
        cli.msg(nick, ("You are already spending the night "+
                      "with \u0002{0}\u0002.").format(var.HVISITED[nick]))
        return
    victim = re.split("\s+",rest)[0].strip().lower()
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    pl = [x.lower() for x in var.list_players()]
    if victim not in pl:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    if nick.lower() == victim:  # Staying home
        var.HVISITED[nick] = None
        cli.msg(nick, "You have chosen to stay home for the night.")
    else:
        var.HVISITED[nick] = var.list_players()[pl.index(victim)]
        cli.msg(nick, ("You are spending the night with \u0002{0}\u0002. "+
                      "Have a good time!").format(victim))
        if var.HVISITED[nick] not in var.ROLES["wolf"]:
            cli.msg(var.HVISITED[nick], ("You are spending the night with \u0002{0}"+
                                          "\u0002. Have a good time!").format(nick))
    chk_nightdone(cli)
    
    

@checks
@pmcmd("see", "!see")
def see(cli, nick, rest):
    if not var.is_role(nick, "seer"):
        cli.msg(nick, "Only a seer may use this command")
        return
    if var.PHASE != "night":
        cli.msg(nick, "You may only have visions at night.")
        return
    if nick in var.SEEN:
        cli.msg(nick, "You may only have one vision per round.")
    victim = re.split("\s+",rest)[0].strip().lower()
    pl = var.list_players()
    pll = [x.lower() for x in pl]
    if not victim:
        cli.msg(nick, "Not enough parameters")
        return
    if victim not in pll:
        cli.msg(nick,"\u0002{0}\u0002 is currently not playing.".format(victim))
        return
    victim = pl[pll.index(victim)]
    if nick in var.CURSED:
        role = "wolf"
    elif var.get_role(victim) == "traitor":
        role = "villager"
    else:
        role = var.get_role(victim)
    cli.msg(nick, ("You have a vision; in this vision, "+
                    "you see that \u0002{0}\u0002 is a "+
                    "\u0002{1}\u0002!").format(victim, role))
    var.SEEN.append(nick)
    chk_nightdone(cli)



@pmcmd("")
def relay(cli, nick, rest):
    if var.PHASE != "night":
        return
    badguys = var.ROLES["wolf"] + var.ROLES["traitor"] + var.ROLES["werecrow"]
    if len(badguys) > 1:
        if var.get_role(nick) in ("wolf","traitor","werecrow"):
            badguys.remove(nick)  #  remove self from list
            for badguy in badguys:
                cli.msg(badguy, "{0} says: {1}".format(nick, rest))



def transition_night(cli):
    var.PHASE = "night"

    if var.TIMERS[1]:  # cancel daytime-limit timer
        var.TIMERS[1].cancel()
        var.TIMERS[1] = None

    # Reset nighttime variables
    var.VICTIM = ""  # nickname of kill victim
    var.KILLER = ""  # nickname of who chose the victim
    var.SEEN = []  # list of seers that have had visions
    var.OBSERVED = {}  # those whom werecrows have observed
    var.HVISITED = {}
    var.NIGHT_START_TIME = datetime.now()

    daydur_msg = ""

    if var.NIGHT_TIMEDELTA or var.START_WITH_DAY:  #  transition from day
        td = var.NIGHT_START_TIME - var.DAY_START_TIME
        var.DAY_START_TIME = None
        var.DAY_TIMEDELTA += td
        min, sec = td.seconds // 60, td.seconds % 60
        daydur_msg = "Day lasted \u0002{0:0>2}:{1:0>2}\u0002. ".format(min,sec)

    chan = botconfig.CHANNEL

    if var.NIGHT_TIME_LIMIT > 0:
        t = threading.Timer(var.NIGHT_TIME_LIMIT, transition_day, [cli])
        var.TIMERS[0] = t
        t.start()

    # send PMs
    ps = var.list_players()
    wolves = var.ROLES["wolf"]+var.ROLES["traitor"]+var.ROLES["werecrow"]
    for wolf in wolves:
        if wolf in var.ROLES["wolf"]:
            cli.msg(wolf, ('You are a \u0002wolf\u0002. It is your job to kill all the '+
                           'villagers. Use "kill <nick>" to kill a villager.'))
        elif wolf in var.ROLES["traitor"]:
            cli.msg(wolf, ('You are a \u0002traitor\u0002. You are exactly like a '+
                           'villager and not even a seer can see your true identity. '+
                           'Only detectives can. '))
        else:
            cli.msg(wolf, ('You are a \u0002werecrow\u0002.  You are able to fly at night. '+
                           'Use "kill <nick>" to kill a a villager.  Alternatively, you can '+
                           'use "observe <nick>" to check if someone is in bed or not. '+
                           'Observing will prevent you participating in a killing.'))
        if len(wolves) > 1:
            cli.msg(wolf, 'Also, if you PM me, your message will be relayed to other wolves.')
        pl = ps[:]
        pl.remove(wolf)  # remove self from list
        for i, player in enumerate(pl):
            if player in var.ROLES["wolf"]:
                pl[i] = player + " (wolf)"
            elif player in var.ROLES["traitor"]:
                pl[i] = player + " (traitor)"
            elif player in var.ROLES["werecrow"]:
                pl[i] = player + " (werecrow)"
        cli.msg(wolf, "\u0002Players:\u0002 "+", ".join(pl))

    for seer in var.ROLES["seer"]:
        pl = ps[:]
        pl.remove(seer)  # remove self from list
        cli.msg(seer, ('You are a \u0002seer\u0002. '+
                      'It is your job to detect the wolves, you '+
                      'may have a vision once per night. '+
                      'Use "see <nick>" to see the role of a player.'))
        cli.msg(seer, "Players: "+", ".join(pl))

    for harlot in var.ROLES["harlot"]:
        pl = ps[:]
        pl.remove(harlot)
        cli.msg(harlot, ('You are a \u0002harlot\u0002. '+
                         'You may spend the night with one person per round. '+
                         'If you visit a victim of a wolf, or visit a wolf, '+
                         'you will die. Use !visit to visit a player.'))
        cli.msg(harlot, "Players: "+", ".join(pl))
        
    for d in var.ROLES["village drunk"]:
        cli.msg(d, 'You have been drinking too much! You are the \u0002village drunk\u0002.')
    
    for g in tuple(var.GUNNERS.keys()):
        gun_msg =  ("You hold a gun that shoots special silver bullets. You may only use it "+
                    "during the day. If you shoot a wolf, (s)he will die instantly, but if you "+
                    "shoot a villager, that villager will likely survive. You get {0}.")
        if var.GUNNERS[g] == 1:
            gun_msg = gun_msg.format("1 bullet")
        elif var.GUNNERS[g] > 1:
            gun_msg = gun_msg.format(str(var.GUNNERS[g]) + " bullets")
        else:
            continue
        cli.msg(g, gun_msg)

    cli.msg(chan, (daydur_msg + "It is now nighttime. All players "+
                   "check for PMs from me for instructions. "+
                   "If you did not receive one, simply sit back, "+
                   "relax, and wait patiently for morning."))
    if not var.ROLES["wolf"]:  # Probably something interesting going on.
        chk_nightdone(cli)
        chk_traitor(cli)  # TODO: Remove this nonsense and add
                          #       a startWithDay custom setting



def cgamemode(cli, *args):
    chan = botconfig.CHANNEL
    for arg in args:
        modeargs = arg.split("=", 1)
        modeargs[0] = modeargs[0].strip()
        if modeargs[0] in var.GAME_MODES.keys():
            md = modeargs.pop(0)
            modeargs[0] = modeargs[0].strip()
            try:
                gm = var.GAME_MODES[md](modeargs[0])
                for attr in dir(gm):
                    val = getattr(gm, attr)
                    if (hasattr(var, attr) and not callable(val) 
                                            and not attr.startswith("_")):
                        var.ORIGINAL_SETTINGS[attr] = getattr(var, attr)
                        setattr(var, attr, val)
                return True
            except var.InvalidModeException as e:
                cli.msg(botconfig.CHANNEL, "Invalid mode: "+str(e))
                return False
        else:
            cli.msg(chan, "Mode \u0002{0}\u0002not found.".format(modeargs[0]))
            

@cmd("!start")
def start(cli, nick, chan, rest):
    villagers = var.list_players()
    
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in villagers:
        cli.notice(nick, "You're currently not playing.")
        return
    now = datetime.now()
    var.GAME_START_TIME = now  # Only used for the idler checker
    dur = int((var.CAN_START_TIME - now).total_seconds())
    if dur > 0:
        cli.msg(chan, "Please wait at least {0} more seconds.".format(dur))
        return

    if len(villagers) < 4:
        cli.msg(chan, "{0}: Four or more players are required to play.".format(nick))
        return
    
    for pcount in range(len(villagers), 3, -1):
        addroles = var.ROLES_GUIDE.get(pcount)
        if addroles:
            break
    
    if var.ORIGINAL_SETTINGS:  # Custom settings
        while True:
            wvs = (addroles[var.INDEX_OF_ROLE["wolf"]] + 
                  addroles[var.INDEX_OF_ROLE["traitor"]])
            if len(villagers) < sum(addroles):
                cli.msg(chan, "There are too few players in the "+
                              "game to use the custom roles.")
            elif not wvs:
                cli.msg(chan, "There has to be at least one wolf!")
            elif wvs > (len(villagers) / 2):
                cli.msg(chan, "Too many wolves.")
            else:
                break
            reset_settings()
            cli.msg(chan, "The default settings have been restored.  Please !start again.")
            var.PHASE = "join"
            return
    
    
    var.ROLES = {}
    var.CURSED = []
    var.GUNNERS = {}

    villager_roles = ("gunner", "cursed")
    for i, count in enumerate(addroles):
        role = var.ROLE_INDICES[i]
        if role in villager_roles:
            var.ROLES[role] = [None] * count
            continue # We deal with those later, see below
        selected = random.sample(villagers, count)
        var.ROLES[role] = selected
        for x in selected:
            villagers.remove(x)
        
    # Now for the villager roles
    # Select cursed (just a villager)
    if var.ROLES["cursed"]:
        var.CURSED = random.sample((villagers +  # harlot and drunk can be cursed
                                     var.ROLES["harlot"] +
                                     var.ROLES["village drunk"]),
                                     len(var.ROLES["cursed"]))
    del var.ROLES["cursed"]
    # Select gunner (also a villager)
    if var.ROLES["gunner"]:
        possible = (villagers +
                   var.ROLES["harlot"] +
                   var.ROLES["village drunk"] +
                   var.ROLES["seer"])
        for csd in var.CURSED:
            if csd in possible:
                possible.remove(csd)
        for gnr in random.sample(possible, len(var.ROLES["gunner"])):
            if var.ROLES["village drunk"] == gnr:
                var.GUNNERS[gnr] = var.DRUNK_SHOTS_MULTIPLIER * var.MAX_SHOTS
            else:
                var.GUNNERS[gnr] = var.MAX_SHOTS
    del var.ROLES["gunner"]

    var.ROLES["villager"] = villagers

    cli.msg(chan, ("{0}: Welcome to Werewolf, the popular detective/social party "+
                   "game (a theme of Mafia).").format(", ".join(var.list_players())))
    cli.mode(chan, "+m")

    var.ORIGINAL_ROLES = copy.deepcopy(var.ROLES)  # Make a copy
    var.DAY_TIMEDELTA = timedelta(0)
    var.NIGHT_TIMEDELTA = timedelta(0)
    var.DAY_START_TIME = None
    var.NIGHT_START_TIME = None

    if not var.START_WITH_DAY:
        transition_night(cli)
    else:
        transition_day(cli)


    
@cmd("!game")
def game(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    if nick in var.DENIED_SETTINGS_CHANGE:
        cli.notice(nick, "You cannot vote because your previous "+
                         "settings change was denied by vote.")
        return
    if var.SETTINGS_CHANGE_REQUESTER:
        cli.notice(nick, "There is already an existing "+
                         "settings change request.")
        return
    rest = rest.strip().lower()
    if rest:
        if cgamemode(cli, *rest.split(" ")):
            var.SETTINGS_CHANGE_REQUESTER = nick
            cli.msg(chan, ("\u0002{0}\u0002 has changed the "+
                            "game settings successfully. To "+
                            'oppose this change, use "!no".').format(nick))
            if var.CAN_START_TIME > datetime.now():
                var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT) * 2
            else:
                var.CAN_START_TIME = datetime.now() + timedelta(seconds=var.EXTRA_WAIT) * 2
            cli.msg(chan, "The wait time has also been extended.")

                            
@cmd("!no")
def nay(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE != "join" or not var.SETTINGS_CHANGE_REQUESTER:
        cli.notice(nick, "This command is only allowed if there is "+
                   "a game settings change request in effect.")
        return
    if nick not in pl:
        cli.notice(nick, "You're not currently playing.")
        return
    if var.SETTINGS_CHANGE_REQUESTER in pl:
        pl.remove(var.SETTINGS_CHANGE_REQUESTER)
    if nick in var.SETTINGS_CHANGE_OPPOSITION:
        cli.notice(nick, "You are already in the opposition.")
        return
    var.SETTINGS_CHANGE_OPPOSITION.append(nick)
    needed = len(pl)//2 + 1
    if len(var.SETTINGS_CHANGE_OPPOSITION) >= needed:
        cli.msg(chan, "The settings change request has been downvoted "+
                      "to oblivion.  The default settings are restored.")
        reset_settings()
    else:
        cli.msg(chan, ("\u0002{0}\u0002 has voted \u0002no\u0002. {1} more "+
                      "vote{2} are needed to deny the change.").format(nick,
                             needed - len(var.SETTINGS_CHANGE_OPPOSITION),
                             "s" if needed > 1 else ""))

                             
                             
@cmd("!wait")
def wait(cli, nick, chan, rest):
    pl = var.list_players()
    if var.PHASE == "none":
        cli.notice(nick, "No game is currently running.")
        return
    if var.PHASE != "join":
        cli.notice(nick, "Werewolf is already in play.")
        return
    if nick not in pl:
        cli.notice(nick, "You're currently not playing.")
        return
    if var.WAITED >= var.MAXIMUM_WAITED:
        cli.msg(chan, "Limit has already been reached for extending the wait time.")
        return

    now = datetime.now()
    if now > var.CAN_START_TIME:
        var.CAN_START_TIME = now + timedelta(seconds=var.EXTRA_WAIT)
    else:
        var.CAN_START_TIME += timedelta(seconds=var.EXTRA_WAIT)
    var.WAITED += 1
    cli.msg(chan, ("\u0002{0}\u0002 increased the wait time by "+
                  "{1} seconds.").format(nick, var.EXTRA_WAIT))



@cmd("!reset", admin_only = True)
def reset_game(cli, nick, chan, rest):
    reset(cli)