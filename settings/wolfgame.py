PING_WAIT = 300  # Seconds
PING_MIN_WAIT = 30 # How long !start has to wait after a !ping
MINIMUM_WAIT = 60
EXTRA_WAIT = 20
EXTRA_WAIT_JOIN = 0 # Add this many seconds to the waiting time for each !join
WAIT_AFTER_JOIN = 10 # Wait at least this many seconds after the last join
MAXIMUM_WAITED = 3  # limit for amount of !wait's
STATS_RATE_LIMIT = 60
VOTES_RATE_LIMIT = 60
ADMINS_RATE_LIMIT = 300
GSTATS_RATE_LIMIT = 15
PSTATS_RATE_LIMIT = 15
TIME_RATE_LIMIT = 60
SHOTS_MULTIPLIER = .12  # ceil(shots_multiplier * len_players) = bullets given
MIN_PLAYERS = 4
MAX_PLAYERS = 21
DRUNK_SHOTS_MULTIPLIER = 3
NIGHT_TIME_LIMIT = 120
NIGHT_TIME_WARN = 90  # should be less than NIGHT_TIME_LIMIT
DAY_TIME_LIMIT_WARN = 600
DAY_TIME_LIMIT_CHANGE = 120  # seconds after DAY_TIME_LIMIT_WARN has passed
JOIN_TIME_LIMIT = 3600
# May only be set if the above are also set
SHORT_DAY_PLAYERS = 6 # Number of players left to have a short day
SHORT_DAY_LIMIT_WARN = 400
SHORT_DAY_LIMIT_CHANGE = 120
KILL_IDLE_TIME = 300
WARN_IDLE_TIME = 180
PART_GRACE_TIME = 30
QUIT_GRACE_TIME = 30
#  controls how many people it does in one /msg; only works for messages that are the same
MAX_PRIVMSG_TARGETS = 4
LEAVE_STASIS_PENALTY = 1
IDLE_STASIS_PENALTY = 1
PART_STASIS_PENALTY = 1

GOAT_HERDER = True

SELF_LYNCH_ALLOWED = True
HIDDEN_TRAITOR = True

CARE_BOLD = False
CARE_COLOR = False
KILL_COLOR = False
KILL_BOLD = False

LOG_FILENAME = ""
BARE_LOG_FILENAME = ""

                    #       HIT    MISS    SUICIDE
GUN_CHANCES         =   (   5/7  ,  1/7  ,   1/7   )
DRUNK_GUN_CHANCES   =   (   2/7  ,  3/7  ,   2/7   )
MANSLAUGHTER_CHANCE =       2/5  # ACCIDENTAL HEADSHOT (FATAL)

GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE = 1/4
GUARDIAN_ANGEL_DIES_CHANCE = 1/2
DETECTIVE_REVEALED_CHANCE = 2/5

#################################################################################################################
#   ROLE INDEX:   PLAYERS   SEER    WOLF   CURSED   DRUNK   HARLOT  TRAITOR  GUNNER   CROW    ANGEL DETECTIVE  ##
#################################################################################################################
ROLES_GUIDE = {    4    : (   1   ,   1   ,   0   ,   0   ,   0   ,    0   ,   0   ,   0    ,   0   ,   0   ), ##
                   6    : (   1   ,   1   ,   1   ,   0   ,   0   ,    0   ,   0   ,   0    ,   0   ,   0   ), ##
                   8    : (   1   ,   1   ,   1   ,   1   ,   1   ,    1   ,   0   ,   0    ,   0   ,   0   ), ##
                   10   : (   1   ,   2   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0    ,   0   ,   0   ), ##
                   12   : (   1   ,   2   ,   1   ,   1   ,   1   ,    1   ,   1   ,   1    ,   0   ,   1   ), ##
                   15   : (   1   ,   3   ,   1   ,   1   ,   1   ,    1   ,   1   ,   1    ,   0   ,   1   ), ##
                   17   : (   1   ,   3   ,   1   ,   1   ,   1   ,    1   ,   1   ,   1    ,   1   ,   1   ), ##
                   18   : (   1   ,   3   ,   2   ,   1   ,   1   ,    1   ,   1   ,   1    ,   1   ,   1   ), ##
                   20   : (   1   ,   4   ,   2   ,   1   ,   1   ,    1   ,   1   ,   1    ,   1   ,   1   ), ##
                   None : (   0   ,   0   ,   0   ,   0   ,   0   ,    0   ,   0   ,   0    ,   0   ,   0   )} ##
#################################################################################################################
#   Notes:                                                                                                     ##
#################################################################################################################

GAME_MODES = {}
AWAY = ['services.', 'services.int']  # cloaks of people who are away.
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
                  "Despite protests, the mob drags their victim to the hanging tree. \u0002{0}\u0002 succumbs to the will of the horde, and is hanged. The villagers have killed a \u0002{1}\u0002.",
                  "Resigned to the inevitable, \u0002{0}\u0002 is led to the gallows. Once the twitching stops, it is discovered that the village lynched a \u0002{1}\u0002.",
                  "Before the rope is pulled, \u0002{0}\u0002, the \u0002{1}\u0002, throws a grenade at the mob. The grenade explodes early.")

import botconfig

RULES = (botconfig.CHANNEL + " channel rules: http://wolf.xnrand.com/rules")

# Other settings:
START_WITH_DAY = False
WOLF_STEALS_GUN = True  # at night, the wolf can steal steal the victim's bullets

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

def get_reveal_role(nick):
    if HIDDEN_TRAITOR and get_role(nick) == "traitor":
        return "villager"
    else:
        return get_role(nick)

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

        
    c.execute(('CREATE TABLE IF NOT EXISTS gamestats (size SMALLINT, villagewins SMALLINT, ' +
        'wolfwins SMALLINT, totalgames SMALLINT, UNIQUE(size))'))
        
        
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
        wins, iwins, total = 0, 0, 0

        c.execute(("SELECT teamwins, individualwins, totalgames FROM rolestats "+
                   "WHERE player=? AND role=?"), (acc, role))
        row = c.fetchone()
        if row:
            wins, iwins, total = row

        if won:
            wins += 1
        if iwon:
            iwins += 1
        total += 1

        c.execute("INSERT OR REPLACE INTO rolestats VALUES (?,?,?,?,?)",
                  (acc, role, wins, iwins, total))

def update_game_stats(size, winner):
    with conn:
        vwins, wwins, total = 0, 0, 0
        
        c.execute("SELECT villagewins, wolfwins, totalgames FROM gamestats "+
                   "WHERE size=?", (size,))
        row = c.fetchone()
        if row:
            vwins, wwins, total = row
        
        if winner == "wolves":
            wwins += 1
        elif winner == "villagers":
            vwins += 1
        total += 1
        
        c.execute("INSERT OR REPLACE INTO gamestats VALUES (?,?,?,?)",
                    (size, vwins, wwins, total))
        
def get_player_stats(acc, role):
    if role.lower() not in ["villager"] + [v.lower() for k, v in ROLE_INDICES.items()]:
        return "No such role: {0}".format(role)
    with conn:
        c.execute("SELECT player FROM rolestats WHERE player=? COLLATE NOCASE", (acc,))
        player = c.fetchone()
        if player:
            for row in c.execute("SELECT * FROM rolestats WHERE player=? COLLATE NOCASE AND role=? COLLATE NOCASE", (acc, role)):
                msg = "\u0002{0}\u0002 as \u0002{1}\u0002 | Team wins: {2} (%d%%), Individual wins: {3} (%d%%), Total games: {4}".format(*row)
                return msg % (round(row[2]/row[4] * 100), round(row[3]/row[4] * 100))
            else:
                return "No stats for {0} as {1}.".format(player[0], role)
        return "{0} has not played any games.".format(acc)

def get_player_totals(acc):
    role_totals = []
    with conn:
        c.execute("SELECT player FROM rolestats WHERE player=? COLLATE NOCASE", (acc,))
        player = c.fetchone()
        if player:
            for role in ["villager"] + [v for k, v in ROLE_INDICES.items()]:
                c.execute("SELECT totalgames FROM rolestats WHERE player=? COLLATE NOCASE AND role=? COLLATE NOCASE", (acc, role))
                row = c.fetchone()
                if row:
                    role_totals.append("\u0002{0}\u0002: {1}".format(role, *row))
            return "\u0002{0}\u0002's totals | {1}".format(player[0], ", ".join(role_totals))
        else:
            return "{0} has not played any games.".format(acc)
            
def get_game_stats(size):
    with conn:
        for row in c.execute("SELECT * FROM gamestats WHERE size=?", (size,)):
            msg = "\u0002{0}\u0002 player games | Village wins: {1} (%d%%),  Wolf wins: {2} (%d%%), Total games: {3}".format(*row)
            return msg % (round(row[1]/row[3] * 100), round(row[2]/row[3] * 100))
        else:
            return "No stats for \u0002{0}\u0002 player games.".format(size)

def get_game_totals():
    size_totals = []
    total = 0
    with conn:
        for size in range(MIN_PLAYERS, MAX_PLAYERS + 1):
            c.execute("SELECT size, totalgames FROM gamestats WHERE size=?", (size,))
            row = c.fetchone()
            if row:
                size_totals.append("\u0002{0}p\u0002: {1}".format(*row))
                total += row[1]
    
    if len(size_totals) == 0:
        return "No games have been played."
    else:
        return "Total games ({0}) | {1}".format(total, ", ".join(size_totals))
