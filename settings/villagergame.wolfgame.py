PING_WAIT = 300  # Seconds
PING_MIN_WAIT = 30
MINIMUM_WAIT = 60 
EXTRA_WAIT = 20
MAXIMUM_WAITED = 2  # limit for amount of !wait's
STATS_RATE_LIMIT = 15
VOTES_RATE_LIMIT = 15
ADMINS_RATE_LIMIT = 300
SHOTS_MULTIPLIER = .12  # ceil(shots_multiplier * len_players) = bullets given
MAX_PLAYERS = 30
DRUNK_SHOTS_MULTIPLIER = 3
NIGHT_TIME_LIMIT = 120
NIGHT_TIME_WARN = 0  # should be less than NIGHT_TIME_LIMIT
DAY_TIME_LIMIT_WARN = 600
DAY_TIME_LIMIT_CHANGE = 120  # seconds after DAY_TIME_LIMIT_WARN has passed
KILL_IDLE_TIME = 300
WARN_IDLE_TIME = 180
PART_GRACE_TIME = 7
QUIT_GRACE_TIME = 30
MAX_PRIVMSG_TARGETS = 1

LOG_FILENAME = ""
BARE_LOG_FILENAME = ""

                    #       HIT    MISS    SUICIDE
GUN_CHANCES         =   (   5/7  ,  1/7  ,   1/7   )
DRUNK_GUN_CHANCES   =   (   2/7  ,  4/7  ,   1/7   )
MANSLAUGHTER_CHANCE =       1/5  # ACCIDENTAL HEADSHOT (FATAL)

GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE = 0
GUARDIAN_ANGEL_DIES_CHANCE = 1/2
DETECTIVE_REVEALED_CHANCE = 2/5

#################################################################################################################
#   ROLE INDEX:   PLAYERS   SEER    WOLF   CURSED   DRUNK   HARLOT  TRAITOR  GUNNER   CROW    ANGEL DETECTIVE  ##
#################################################################################################################
ROLES_GUIDE = {    4    : (   1   ,   1   ,   0   ,   0   ,   0   ,    0   ,   0   ,   0    ,   0   ,   0   ), ##
                   6    : (   1   ,   1   ,   1   ,   1   ,   0   ,    0   ,   0   ,   0    ,   0   ,   0   ), ##
                   8    : (   1   ,   2   ,   1   ,   1   ,   1   ,    0   ,   0   ,   0    ,   0   ,   0   ), ##
                   10   : (   1   ,   2   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0    ,   0   ,   0   ), ##
                   11   : (   1   ,   2   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0    ,   1   ,   0   ), ##
                   15   : (   1   ,   3   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0    ,   1   ,   1   ), ##
                   22   : (   1   ,   4   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0    ,   1   ,   1   ), ##
                   29   : (   1   ,   5   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0    ,   1   ,   1   ), ##
                   None : (   0   ,   0   ,   0   ,   0   ,   0   ,    0   ,   0   ,   0    ,   0   ,   0   )} ##
#################################################################################################################
#   Notes:                                                                                                     ##
#################################################################################################################

GAME_MODES = {}
AWAY = []  # cloaks of people who are away.
SIMPLE_NOTIFY = []  # cloaks of people who !simple, who want everything /notice'd

ROLE_INDICES = {0 : "seer",
                1 : "wolf",
                2 : "cursed villager",
                3 : "village drunk",
                4 : "harlot",
                5 : "traitor",
                6 : "gunner",
                7 : "werecrow",
                8 : "guardian angel",
                9 : "detective"}
                
INDEX_OF_ROLE = dict((v,k) for k,v in ROLE_INDICES.items())


NO_VICTIMS_MESSAGES = ("The body of a young penguin pet is found.",
                       "A pool of blood and wolf paw prints are found.",
                       "Traces of wolf fur are found.")
LYNCH_MESSAGES = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002, who turned out to be... a \u0002{1}\u0002.",
                  "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002, who turned out to be... a \u0002{1}\u0002.",
                  "The mob drags a protesting \u0002{0}\u0002 to the hanging tree. S/He succumbs to the will of the horde, and is hanged. It is discovered (s)he was a \u0002{1}\u0002.",
                  "Resigned to his/her fate, \u0002{0}\u0002 is led to the gallows. After death, it is discovered (s)he was a \u0002{1}\u0002.")

import botconfig

RULES = (botconfig.CHANNEL + " channel rules: 1) Be nice to others. 2) Do not share information "+
         "after death. 3) No bots allowed. 4) Do not play with clones.\n"+
         "5) Do not quit unless you need to leave. 6) No swearing and keep it "+
         "family-friendly. 7) Do not paste PM's from the bot during the game. "+
         "8) Use common sense. 9) Waiting for timeouts is discouraged.")                                              

# Other settings:
START_WITH_DAY = False
WOLF_STEALS_GUN = False  # at night, the wolf can steal steal the victim's bullets

OPT_IN_PING = False  # instead of !away/!back, users can opt-in to be pinged
PING_IN = []  # cloaks of users who have opted in for ping

is_role = lambda plyr, rol: rol in ROLES and plyr in ROLES[rol]

def plural(role):
    if role == "wolf": return "wolves"
    elif role == "person": return "people"
    else: return role + "s"
    
def list_players():
    pl = []
    for x in ROLES.values():
        pl.extend(x)
    return pl
    
def list_players_and_roles():
    plr = {}
    for x in ROLES.keys():
        for p in ROLES[x]:
            plr[p] = x
    return plr
    
get_role = lambda plyr: list_players_and_roles()[plyr]


def del_player(pname):
    prole = get_role(pname)
    ROLES[prole].remove(pname)
    

    
class InvalidModeException(Exception): pass
def game_mode(name):
    def decor(c):
        GAME_MODES[name] = c
        return c
    return decor

    
CHANGEABLE_ROLES = { "seers"  : INDEX_OF_ROLE["seer"],
                     "wolves" : INDEX_OF_ROLE["wolf"],
                     "cursed" : INDEX_OF_ROLE["cursed villager"],
                    "drunks"  : INDEX_OF_ROLE["village drunk"],
                   "harlots"  : INDEX_OF_ROLE["harlot"],
                  "traitors"  : INDEX_OF_ROLE["traitor"],
                   "gunners"  : INDEX_OF_ROLE["gunner"],
                 "werecrows"  : INDEX_OF_ROLE["werecrow"],
                 "angels"     : INDEX_OF_ROLE["guardian angel"],
                 "detectives" : INDEX_OF_ROLE["detective"]}
    



# TODO: implement game modes
@game_mode("roles")
class ChangedRolesMode(object):
    """Example: !fgame roles=wolves:1,seers:0,angels:1"""
    
    def __init__(self, arg):
        self.ROLES_GUIDE = ROLES_GUIDE.copy()
        lx = list(ROLES_GUIDE[None])
        pairs = arg.split(",")
        pl = list_players()
        if not pairs:
            raise InvalidModeException("Invalid syntax for mode roles.")
        for pair in pairs:
            change = pair.split(":")
            if len(change) != 2:
                raise InvalidModeException("Invalid syntax for mode roles.")
            role, num = change
            try:
                num = int(num)
                try:
                    lx[CHANGEABLE_ROLES[role.lower()]] = num
                except KeyError:
                    raise InvalidModeException(("The role \u0002{0}\u0002 "+
                                                "is not valid.").format(role))
            except ValueError:
                raise InvalidModeException("A bad value was used in mode roles.")
        for k in ROLES_GUIDE.keys():
            self.ROLES_GUIDE[k] = tuple(lx)

         
# Persistence
         
         
# Load saved settings
import sqlite3
import os

conn = sqlite3.connect("data.sqlite3", check_same_thread = False)

with conn:
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS away (nick TEXT)')  # whoops, i mean cloak, not nick
    
    c.execute('CREATE TABLE IF NOT EXISTS simple_role_notify (cloak TEXT)') # people who understand each role

    c.execute('SELECT * FROM away')
    for row in c:
        AWAY.append(row[0])
        
    c.execute('SELECT * FROM simple_role_notify')
    for row in c:
        SIMPLE_NOTIFY.append(row[0])
    
    # populate the roles table
    c.execute('DROP TABLE IF EXISTS roles')
    c.execute('CREATE TABLE roles (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT)')

    for x in ["villager"]+list(ROLE_INDICES.values()):
        c.execute("INSERT OR REPLACE INTO roles (role) VALUES (?)", (x,))
        
        
    c.execute(('CREATE TABLE IF NOT EXISTS rolestats (player TEXT, role TEXT, '+
        'teamwins SMALLINT, individualwins SMALLINT, totalgames SMALLINT, '+
        'UNIQUE(player, role))'))
        
    if OPT_IN_PING:
        c.execute('CREATE TABLE IF NOT EXISTS ping (cloak text)')

        c.execute('SELECT * FROM ping')
        for row in c:
            PING_IN.append(row[0])
    
    
def remove_away(clk):
    with conn:
        c.execute('DELETE from away where nick=?', (clk,))
    
def add_away(clk):
    with conn:
        c.execute('INSERT into away VALUES (?)', (clk,))
        
def remove_simple_rolemsg(clk):
    with conn:
        c.execute('DELETE from simple_role_notify where cloak=?', (clk,))
    
def add_simple_rolemsg(clk):
    with conn:
        c.execute('INSERT into simple_role_notify VALUES (?)', (clk,))
        
def remove_ping(clk):
    with conn:
        c.execute('DELETE from ping where cloak=?', (clk,))
def add_ping(clk):
    with conn:
        c.execute('INSERT into ping VALUES (?)', (clk,))        


def update_role_stats(acc, role, won, iwon):
    
    with conn:
        wins, iwins, totalgames = 0, 0, 0
        
        c.execute(("SELECT teamwins, individualwins, totalgames FROM rolestats "+
                   "WHERE player=? AND role=?"), (acc, role))
        row = c.fetchone()
        if row:
            wins, iwins, total = row
        else:
            wins, iwins, total = 0,0,0
            
        if won:
            wins += 1
        if iwon:
            iwins += 1
        total += 1
        
        c.execute("INSERT OR REPLACE INTO rolestats VALUES (?,?,?,?,?)",
                  (acc, role, wins, iwins, total))



