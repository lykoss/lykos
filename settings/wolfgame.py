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
GSTATS_RATE_LIMIT = 0
PSTATS_RATE_LIMIT = 0
TIME_RATE_LIMIT = 60
SHOTS_MULTIPLIER = .12  # ceil(shots_multiplier * len_players) = bullets given
SHARPSHOOTER_MULTIPLIER = 0.06
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
# If time lord is lynched, the timers get set to this instead (90s day, 60s night)
TIME_LORD_DAY_WARN = 60
TIME_LORD_DAY_CHANGE = 30
TIME_LORD_NIGHT_LIMIT = 60
TIME_LORD_NIGHT_WARN = 40
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
VENGEFUL_GHOST_KNOWS_ROLES = True
BODYGUARD_CAN_GUARD_SELF = True
START_WITH_DAY = False
WOLF_STEALS_GUN = True  # at night, the wolf can steal steal the victim's bullets
ROLE_REVEAL = True

CARE_BOLD = False
CARE_COLOR = False
KILL_COLOR = False
KILL_BOLD = False

LOG_FILENAME = ""
BARE_LOG_FILENAME = ""

                         #       HIT    MISS    SUICIDE   HEADSHOT
GUN_CHANCES              =   (   5/7  ,  1/7  ,   1/7   ,   2/5   )
WOLF_GUN_CHANCES         =   (   5/7  ,  1/7  ,   1/7   ,   2/5   )
DRUNK_GUN_CHANCES        =   (   2/7  ,  3/7  ,   2/7   ,   2/5   )
SHARPSHOOTER_GUN_CHANCES =   (    1   ,   0   ,    0    ,    1    )

GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE = 1/4
GUARDIAN_ANGEL_DIES_CHANCE = 0
BODYGUARD_DIES_CHANCE = 0
DETECTIVE_REVEALED_CHANCE = 2/5
SHARPSHOOTER_CHANCE = 1/5 # if sharpshooter is enabled, chance that a gunner will become a sharpshooter instead

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night
BUREAUCRAT_VOTES = 2 # bureaucrat votes count for this many normal votes

              #      DEATH      PROTECTION     REVEALING     NARCOLEPSY     SILENCE     DESPERATION
TOTEM_CHANCES = (     1/6     ,     1/6     ,     1/6     ,     1/6     ,     1/6     ,     1/6     )

GAME_MODES = {}
AWAY = ['services.', 'services.int']  # cloaks of people who are away.
SIMPLE_NOTIFY = []  # cloaks of people who !simple, who want everything /notice'd

# TODO: move this to a game mode called "fixed" once we implement a way to randomize roles (and have that game mode be called "random")
DEFAULT_ROLE = "villager"
ROLE_INDEX =                      (   4   ,   6   ,   8   ,  10   ,  12   ,  15   ,  17   ,  18   ,  20   )
ROLE_GUIDE = {# village roles
              "villager"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "seer"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "oracle"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "village drunk"   : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "harlot"          : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "guardian angel"  : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
              "bodyguard"       : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "detective"       : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "village elder"   : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "time lord"       : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "matchmaker"      : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "mad scientist"   : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "hunter"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "shaman"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              # wolf roles
              "wolf"            : (   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   3   ,   3   ,   4   ),
              "traitor"         : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "werecrow"        : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "cultist"         : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "minion"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "hag"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "wolf cub"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "sorcerer"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              # neutral roles
              "lycan"           : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "vengeful ghost"  : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "clone"           : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "crazed shaman"   : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "fool"            : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "monster"         : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              # templates
              "cursed villager" : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
              "gunner"          : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              # NB: for sharpshooter, numbers can't be higher than gunner, since gunners get converted to sharpshooters. This is the MAX number of gunners that can be converted.
              "sharpshooter"    : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "mayor"           : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "assassin"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "amnesiac"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              "bureaucrat"      : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ),
              }

# Harlot dies when visiting, gunner kills when shooting, GA and bodyguard have a chance at dying when guarding
# If every wolf role dies, the game ends and village wins and there are no remaining traitors, the game ends and villagers win
WOLF_ROLES     = ["wolf", "werecrow", "wolf cub"]
# Access to wolfchat, and counted towards the # of wolves vs villagers when determining if a side has won
WOLFCHAT_ROLES = ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer"]
# Wins with the wolves, even if the roles are not necessarily wolves themselves
WOLFTEAM_ROLES = ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer", "minion", "cultist"]
# These roles never win as a team, only ever individually (either instead of or in addition to the regular winners)
TRUE_NEUTRAL_ROLES = ["vengeful ghost", "crazed shaman", "fool"]

# The roles in here are considered templates and will be applied on TOP of other roles. The restrictions are a list of roles that they CANNOT be applied to
# NB: if you want a template to apply to everyone, list it here but make the restrictions an empty list. Templates not listed here are considered full roles instead
TEMPLATE_RESTRICTIONS = {"cursed villager" : ["wolf", "wolf cub", "werecrow", "seer", "oracle", "fool"],
                         "gunner"          : ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer", "minion", "cultist", "fool", "lycan"],
                         "sharpshooter"    : ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer", "minion", "cultist", "fool", "lycan"],
                         "mayor"           : ["fool"],
                         "assassin"        : ["seer", "harlot", "detective", "bodyguard", "guardian angel", "village drunk", "hunter", "shaman", "crazed shaman", "fool", "mayor", "wolf", "werecrow", "wolf cub", "traitor", "lycan"],
                         "amnesiac"        : ["villager", "cultist", "wolf", "wolf cub", "werecrow", "minion", "matchmaker", "village elder", "time lord", "clone", "mad scientist"],
                         "bureaucrat"      : [],
                         }

NO_VICTIMS_MESSAGES = ("The body of a young penguin pet is found.",
                       "A pool of blood and wolf paw prints are found.",
                       "Traces of wolf fur are found.")
LYNCH_MESSAGES = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002, who turned out to be... a \u0002{1}\u0002.",
                  "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002, who turned out to be... a \u0002{1}\u0002.",
                  "Despite protests, the mob drags their victim to the hanging tree. \u0002{0}\u0002 succumbs to the will of the horde, and is hanged. The villagers have killed a \u0002{1}\u0002.",
                  "Resigned to the inevitable, \u0002{0}\u0002 is led to the gallows. Once the twitching stops, it is discovered that the village lynched a \u0002{1}\u0002.",
                  "Before the rope is pulled, \u0002{0}\u0002, the \u0002{1}\u0002, throws a grenade at the mob. The grenade explodes early.")
LYNCH_MESSAGES_NO_REVEAL = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002.",
                            "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002.",
                            "Despite protests, the mob drags their victim to the hanging tree. \u0002{0}\u0002 succumbs to the will of the horde, and is hanged.",
                            "Resigned to the inevitable, \u0002{0}\u0002 is led to the gallows.",
                            "Before the rope is pulled, \u0002{0}\u0002 throws a grenade at the mob. The grenade explodes early.")

import botconfig

RULES = (botconfig.CHANNEL + " channel rules: http://wolf.xnrand.com/rules")

# Other settings:

OPT_IN_PING = False  # instead of !away/!back, users can opt-in to be pinged
PING_IN = []  # cloaks of users who have opted in for ping

is_role = lambda plyr, rol: rol in ROLES and plyr in ROLES[rol]

def plural(role):
    if role == "wolf": return "wolves"
    elif role == "person": return "people"
    else: return role + "s"

def list_players(roles = None):
    if roles == None:
        roles = ROLES.keys()
    pl = []
    for x in roles:
        if x != "amnesiac" and x in TEMPLATE_RESTRICTIONS.keys():
            continue
        for p in ROLES[x]:
            pl.append(p)
    return pl

def list_players_and_roles():
    plr = {}
    for x in ROLES.keys():
        if x != "amnesiac" and x in TEMPLATE_RESTRICTIONS.keys():
            continue # only get actual roles
        for p in ROLES[x]:
            plr[p] = x
    return plr

get_role = lambda plyr: list_players_and_roles()[plyr]

def get_reveal_role(nick):
    if HIDDEN_TRAITOR and get_role(nick) == "traitor":
        return DEFAULT_ROLE
    else:
        return get_role(nick)

def del_player(pname):
    prole = get_role(pname)
    ROLES[prole].remove(pname)
    tpls = get_templates(pname)
    for t in tpls:
        ROLES[t].remove(pname)

def get_templates(nick):
    tpl = []
    for x in TEMPLATE_RESTRICTIONS.keys():
        try:
            if nick in ROLES[x]:
                tpl.append(x)
        except KeyError:
            pass

    return tpl

class InvalidModeException(Exception): pass
def game_mode(name):
    def decor(c):
        GAME_MODES[name] = c
        return c
    return decor


# TODO: implement more game modes
@game_mode("roles")
class ChangedRolesMode(object):
    """Example: !fgame roles=wolf:1,seer:0,guardian angel:1"""

    def __init__(self, arg = ""):
        self.ROLE_GUIDE = ROLE_GUIDE.copy()
        self.ROLE_INDEX = (MIN_PLAYERS,)
        pairs = arg.split(",")
        if not pairs:
            raise InvalidModeException("Invalid syntax for mode roles. arg={0}".format(arg))
        
        for role in self.ROLE_GUIDE.keys():
            self.ROLE_GUIDE[role] = (0,)
        for pair in pairs:
            change = pair.split(":")
            if len(change) != 2:
                raise InvalidModeException("Invalid syntax for mode roles. arg={0}".format(arg))
            role, num = change
            try:
                num = int(num)
                if role.lower() in self.ROLE_GUIDE:
                    self.ROLE_GUIDE[role.lower()] = tuple([num] * len(ROLE_INDEX))
                else:
                    raise InvalidModeException(("The role \u0002{0}\u0002 "+
                                                "is not valid.").format(role))
            except ValueError:
                raise InvalidModeException("A bad value was used in mode roles.")

@game_mode("evilvillage")
class EvilVillageMode(object):
    def __init__(self):
        self.MIN_PLAYERS = 6
        self.MAX_PLAYERS = 12
        self.DEFAULT_ROLE = "cultist"
        self.ROLE_INDEX =                (   6   ,  10   )
        self.ROLE_GUIDE = {# village roles
                           "oracle"    : (   1   ,   1   ),
                           "shaman"    : (   1   ,   1   ),
                           "bodyguard" : (   0   ,   1   ),
                           # wolf roles
                           "wolf"      : (   1   ,   1   ),
                           "minion"    : (   0   ,   1   ),
                           }

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

    for x in list(ROLE_GUIDE.keys()):
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
    if role.lower() not in [k.lower() for k in ROLE_GUIDE.keys()]:
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
            for role in [k.lower() for k in ROLE_GUIDE.keys()]:
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

# vim: set expandtab:sw=4:ts=4:
