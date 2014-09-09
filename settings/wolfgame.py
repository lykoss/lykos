from collections import defaultdict

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
TIME_RATE_LIMIT = 10
SHOTS_MULTIPLIER = .12  # ceil(shots_multiplier * len_players) = bullets given
SHARPSHOOTER_MULTIPLIER = 0.06
MIN_PLAYERS = 4
MAX_PLAYERS = 24
DRUNK_SHOTS_MULTIPLIER = 3
NIGHT_TIME_LIMIT = 120
NIGHT_TIME_WARN = 90  # should be less than NIGHT_TIME_LIMIT
DAY_TIME_LIMIT = 720
DAY_TIME_WARN = 600   # should be less than DAY_TIME_LIMIT
JOIN_TIME_LIMIT = 3600
# May only be set if the above are also set
SHORT_DAY_PLAYERS = 6 # Number of players left to have a short day
SHORT_DAY_LIMIT = 520
SHORT_DAY_WARN = 400
# If time lord dies, the timers get set to this instead (60s day, 30s night)
TIME_LORD_DAY_LIMIT = 60
TIME_LORD_DAY_WARN = 45
TIME_LORD_NIGHT_LIMIT = 30
TIME_LORD_NIGHT_WARN = 20
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

ABSTAIN_ENABLED = True # whether village can !abstain in order to not vote anyone during day
LIMIT_ABSTAIN = True # if true, village will be limited to successfully !abstaining a vote only once
SELF_LYNCH_ALLOWED = True
HIDDEN_TRAITOR = True
HIDDEN_AMNESIAC = False # amnesiac still shows as amnesiac if killed even after turning
HIDDEN_CLONE = False
GUARDIAN_ANGEL_CAN_GUARD_SELF = True
START_WITH_DAY = False
WOLF_STEALS_GUN = True  # at night, the wolf can steal steal the victim's bullets
ROLE_REVEAL = True
LOVER_WINS_WITH_FOOL = False # if fool is lynched, does their lover win with them?

# Minimum number of players needed for mad scientist to skip over dead people when determining who is next to them
# Set to 0 to always skip over dead players. Note this is number of players that !joined, NOT number of players currently alive
MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 99 

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

#                                     SHAMAN    CRAZED SHAMAN
TOTEM_CHANCES = {       "death": (     1/8     ,     1/15     ),
                   "protection": (     1/8     ,     1/15     ),
                      "silence": (     1/8     ,     1/15     ),
                    "revealing": (     1/8     ,     1/15     ),
                  "desperation": (     1/8     ,     1/15     ),
                   "impatience": (     1/8     ,     1/15     ),
                     "pacifism": (     1/8     ,     1/15     ),
                    "influence": (     1/8     ,     1/15     ),
                   "narcolepsy": (      0      ,     1/15     ),
                     "exchange": (      0      ,     1/15     ),
                  "lycanthropy": (      0      ,     1/15     ),
                         "luck": (      0      ,     1/15     ),
                   "pestilence": (      0      ,     1/15     ),
                  "retribution": (      0      ,     1/15     ),
                 "misdirection": (      0      ,     1/15     ),
                }

GAME_MODES = {}
AWAY = ['services.', 'services.int']  # cloaks of people who are away.
SIMPLE_NOTIFY = []  # cloaks of people who !simple, who don't want detailed instructions
PREFER_NOTICE = []  # cloaks of people who !notice, who want everything /notice'd

STASISED = defaultdict(int)

# TODO: move this to a game mode called "fixed" once we implement a way to randomize roles (and have that game mode be called "random")
DEFAULT_ROLE = "villager"
ROLE_INDEX =                      (  4  ,  6  ,  7  ,  8  ,  9  , 10  , 11  , 12  , 13  , 15  , 16  , 18  , 20  , 21  , 23  , 24  )
ROLE_GUIDE = {# village roles
              "villager"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "seer"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "oracle"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "augur"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ),
              "village drunk"   : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "harlot"          : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "guardian angel"  : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "bodyguard"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "detective"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "village elder"   : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "time lord"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "matchmaker"      : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "mad scientist"   : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "hunter"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "shaman"          : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # wolf roles
              "wolf"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  3  ,  3  ,  3  ),
              "traitor"         : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "werecrow"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "cultist"         : (  0  ,  0  ,  1  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "minion"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "hag"             : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ),
              "wolf cub"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "sorcerer"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ),
              # neutral roles
              "lycan"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "vengeful ghost"  : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "clone"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "crazed shaman"   : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "fool"            : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "jester"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "monster"         : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "amnesiac"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ),
              # templates
              "cursed villager" : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ),
              "gunner"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ),
              # NB: for sharpshooter, numbers can't be higher than gunner, since gunners get converted to sharpshooters. This is the MAX number of gunners that can be converted.
              "sharpshooter"    : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "mayor"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ),
              "assassin"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "bureaucrat"      : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              }

# Harlot dies when visiting, gunner kills when shooting, GA and bodyguard have a chance at dying when guarding
# If every wolf role dies, the game ends and village wins and there are no remaining traitors, the game ends and villagers win
WOLF_ROLES     = ["wolf", "werecrow", "wolf cub"]
# Access to wolfchat, and counted towards the # of wolves vs villagers when determining if a side has won
WOLFCHAT_ROLES = ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer"]
# Wins with the wolves, even if the roles are not necessarily wolves themselves
WOLFTEAM_ROLES = ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer", "minion", "cultist"]
# These roles never win as a team, only ever individually (either instead of or in addition to the regular winners)
TRUE_NEUTRAL_ROLES = ["crazed shaman", "fool", "jester", "monster", "clone"]
# These are the roles that will NOT be used for when amnesiac turns, everything else is fair game!
AMNESIAC_BLACKLIST = ["monster", "amnesiac", "minion", "matchmaker", "clone"]

# The roles in here are considered templates and will be applied on TOP of other roles. The restrictions are a list of roles that they CANNOT be applied to
# NB: if you want a template to apply to everyone, list it here but make the restrictions an empty list. Templates not listed here are considered full roles instead
TEMPLATE_RESTRICTIONS = {"cursed villager" : ["wolf", "wolf cub", "werecrow", "seer", "oracle", "augur", "fool", "jester", "mad scientist"],
                         "gunner"          : ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer", "minion", "cultist", "fool", "lycan", "jester"],
                         "sharpshooter"    : ["wolf", "traitor", "werecrow", "hag", "wolf cub", "sorcerer", "minion", "cultist", "fool", "lycan", "jester"],
                         "mayor"           : ["fool", "jester", "monster"],
                         "assassin"        : ["seer", "augur", "oracle", "harlot", "detective", "bodyguard", "guardian angel", "village drunk", "hunter", "shaman", "crazed shaman", "fool", "mayor", "wolf", "werecrow", "wolf cub", "traitor", "lycan"],
                         "bureaucrat"      : [],
                         }

# Roles listed here cannot be used in !fgame roles=blah. If they are defined in ROLE_GUIDE they may still be used.
DISABLED_ROLES = []

NO_VICTIMS_MESSAGES = ("The body of a young penguin pet is found.",
                       "A pool of blood and wolf paw prints are found.",
                       "Traces of wolf fur are found.")
LYNCH_MESSAGES = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002, who turned out to be... a{1} \u0002{2}\u0002.",
                  "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002, who turned out to be... a{1} \u0002{2}\u0002.",
                  "Despite protests, the mob drags their victim to the hanging tree. \u0002{0}\u0002 succumbs to the will of the horde, and is hanged. The villagers have killed a{1} \u0002{2}\u0002.",
                  "Resigned to the inevitable, \u0002{0}\u0002 is led to the gallows. Once the twitching stops, it is discovered that the village lynched a{1} \u0002{2}\u0002.",
                  "Before the rope is pulled, \u0002{0}\u0002, a{1} \u0002{2}\u0002, throws a grenade at the mob. The grenade explodes early.")
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
        if x in TEMPLATE_RESTRICTIONS.keys():
            continue
        for p in ROLES[x]:
            pl.append(p)
    return pl

def list_players_and_roles():
    plr = {}
    for x in ROLES.keys():
        if x in TEMPLATE_RESTRICTIONS.keys():
            continue # only get actual roles
        for p in ROLES[x]:
            plr[p] = x
    return plr

get_role = lambda plyr: list_players_and_roles()[plyr]

def get_reveal_role(nick):
    if HIDDEN_TRAITOR and get_role(nick) == "traitor":
        return DEFAULT_ROLE
    elif HIDDEN_AMNESIAC and nick in ORIGINAL_ROLES["amnesiac"]:
        return "amnesiac"
    elif HIDDEN_CLONE and nick in ORIGINAL_ROLES["clone"]:
        return "clone"
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

def break_long_message(phrases, joinstr = " "):
    message = ""
    count = 0
    for phrase in phrases:
        # IRC max is 512, but freenode splits around 380ish, make 300 to have plenty of wiggle room
        if count + len(joinstr) + len(phrase) > 300:
            message += "\n" + phrase
            count = len(phrase)
        elif message == "":
            message = phrase
            count = len(phrase)
        else:
            message += joinstr + phrase
            count += len(joinstr) + len(phrase)
    return message

class InvalidModeException(Exception): pass
def game_mode(name):
    def decor(c):
        GAME_MODES[name] = c
        return c
    return decor

def reset_roles(index):
    newguide = {}
    for role in ROLE_GUIDE:
        newguide[role] = tuple([0 for i in index])
    return newguide

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
                if role.lower() in DISABLED_ROLES:
                    raise InvalidModeException("The role \u0002{0}\u0002 has been disabled.".format(role))
                elif role.lower() in self.ROLE_GUIDE:
                    self.ROLE_GUIDE[role.lower()] = tuple([int(num)] * len(ROLE_INDEX))
                elif role.lower() == "default" and num.lower() in self.ROLE_GUIDE:
                    if num.lower() == "villager" or num.lower() == "cultist":
                        self.DEFAULT_ROLE = num.lower()
                    else:
                        raise InvalidModeException("The default role must be either \u0002villager\u0002 or \u0002cultist\u0002.")
                elif role.lower() == "role reveal" or role.lower() == "reveal roles":
                    num = num.lower()
                    if num == "on" or num == "true" or num == "yes" or num == "1":
                        self.ROLE_REVEAL = True
                    elif num == "off" or num == "false" or num == "no" or num == "0":
                        self.ROLE_REVEAL = False
                    else:
                        raise InvalidModeException("Did not recognize value \u0002{0}\u0002 for role reveal.".format(num))
                else:
                    raise InvalidModeException(("The role \u0002{0}\u0002 "+
                                                "is not valid.").format(role))
            except ValueError:
                raise InvalidModeException("A bad value was used in mode roles.")

@game_mode("default")
class DefaultMode(object):
    def __init__(self):
        # No extra settings, just an explicit way to revert to default settings
        pass

@game_mode("evilvillage")
class EvilVillageMode(object):
    def __init__(self):
        self.MIN_PLAYERS = 6
        self.MAX_PLAYERS = 18
        self.DEFAULT_ROLE = "cultist"
        self.ROLE_INDEX =         (   6   ,  10   ,  15   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "oracle"          : (   1   ,   1   ,   0   ),
              "seer"            : (   0   ,   0   ,   1   ),
              "guardian angel"  : (   0   ,   1   ,   1   ),
              "shaman"          : (   1   ,   1   ,   1   ),
              "hunter"          : (   0   ,   0   ,   1   ),
              "villager"        : (   0   ,   0   ,   1   ),
              # wolf roles
              "wolf"            : (   1   ,   1   ,   2   ),
              "minion"          : (   0   ,   1   ,   1   ),
              # neutral roles
              "fool"            : (   0   ,   1   ,   1   ),
              })

@game_mode("classic")
class ClassicMode(object):
    def __init__(self):
        self.MIN_PLAYERS = 4
        self.MAX_PLAYERS = 21
        self.ROLE_INDEX =         (   4   ,   6   ,   8   ,  10   ,  12   ,  15   ,  17   ,  18   ,  20   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "seer"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "village drunk"   : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "harlot"          : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "bodyguard"       : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
              "detective"       : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              # wolf roles
              "wolf"            : (   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   3   ,   3   ,   4   ),
              "traitor"         : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "werecrow"        : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              # templates
              "cursed villager" : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
              "gunner"          : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              })

@game_mode("rapidfire")
class RapidFireMode(object):
    def __init__(self):
        self.MIN_PLAYERS = 6
        self.MAX_PLAYERS = 25
        self.SHARPSHOOTER_CHANCE = 1
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.ROLE_INDEX =         (   6   ,   8   ,  10   ,  12   ,  15   ,  18   ,  22   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "mad scientist"     : (   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "matchmaker"        : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   2   ),
            "hunter"            : (   0   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "augur"             : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "time lord"         : (   0   ,   0   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   4   ),
            "wolf cub"          : (   0   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ),
            "traitor"           : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "vengeful ghost"    : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   2   ),
            "amnesiac"          : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "assassin"          : (   0   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "sharpshooter"      : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            })

@game_mode("noreveal")
class NoRevealMode(object):
    def __init__(self):
        self.MIN_PLAYERS = 4
        self.MAX_PLAYERS = 21
        self.ROLE_REVEAL = False
        self.ROLE_INDEX =         (   4   ,   6   ,   8   ,  10   ,  12   ,  15   ,  17   ,  19   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "guardian angel"    : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "shaman"            : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "village elder"     : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "detective"         : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "hunter"            : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   3   ),
            "traitor"           : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "minion"            : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # neutral roles
            "crazed shaman"     : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "clone"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "lycan"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ),
            "amnesiac"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            })

# Persistence


# Load saved settings
import sqlite3

conn = sqlite3.connect("data.sqlite3", check_same_thread = False)

with conn:
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS away (nick TEXT)')  # whoops, i mean cloak, not nick

    c.execute('CREATE TABLE IF NOT EXISTS simple_role_notify (cloak TEXT)') # people who understand each role

    c.execute('CREATE TABLE IF NOT EXISTS prefer_notice (cloak TEXT)') # people who prefer /notice

    c.execute('CREATE TABLE IF NOT EXISTS stasised (cloak TEXT, games INTEGER, UNIQUE(cloak))') # stasised people

    c.execute('SELECT * FROM away')
    for row in c:
        AWAY.append(row[0])

    c.execute('SELECT * FROM simple_role_notify')
    for row in c:
        SIMPLE_NOTIFY.append(row[0])

    c.execute('SELECT * FROM prefer_notice')
    for row in c:
        PREFER_NOTICE.append(row[0])

    c.execute('SELECT * FROM stasised')
    for row in c:
        STASISED[row[0]] = row[1]

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

def remove_prefer_notice(clk):
    with conn:
        c.execute('DELETE from prefer_notice where cloak=?', (clk,))

def add_prefer_notice(clk):
    with conn:
        c.execute('INSERT into prefer_notice VALUES (?)', (clk,))

def remove_ping(clk):
    with conn:
        c.execute('DELETE from ping where cloak=?', (clk,))

def add_ping(clk):
    with conn:
        c.execute('INSERT into ping VALUES (?)', (clk,))

def set_stasis(clk, games):
    with conn:
        if games <= 0:
            c.execute('DELETE FROM stasised WHERE cloak=?', (clk,))
        else:
            c.execute('INSERT OR REPLACE INTO stasised VALUES (?,?)', (clk, games))


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
            c.execute("SELECT role, totalgames FROM rolestats WHERE player=? COLLATE NOCASE ORDER BY totalgames DESC", (acc,))
            while True:
                row = c.fetchone()
                if row:
                    role_totals.append("\u0002{0}\u0002: {1}".format(row[0], row[1]))
                else:
                    break
            c.execute("SELECT SUM(totalgames) from rolestats WHERE player=? COLLATE NOCASE AND role!='cursed villager' AND role!='gunner'", (acc,))
            row = c.fetchone()
            return "\u0002{0}\u0002's totals | \u0002{1}\u0002 games | {2}".format(player[0], row[0], break_long_message(role_totals, ", "))
        else:
            return "\u0002{0}\u0002 has not played any games.".format(acc)

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
