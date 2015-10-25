import fnmatch
import sqlite3
import re
from collections import defaultdict, OrderedDict

import botconfig

MINIMUM_WAIT = 60
EXTRA_WAIT = 30
EXTRA_WAIT_JOIN = 0 # Add this many seconds to the waiting time for each !join
WAIT_AFTER_JOIN = 25 # Wait at least this many seconds after the last join
# !wait uses a token bucket
WAIT_TB_INIT  = 2   # initial number of tokens
WAIT_TB_DELAY = 240 # wait time between adding tokens
WAIT_TB_BURST = 3   # maximum number of tokens that can be accumulated
STATS_RATE_LIMIT = 60
VOTES_RATE_LIMIT = 60
ADMINS_RATE_LIMIT = 300
GSTATS_RATE_LIMIT = 0
PSTATS_RATE_LIMIT = 0
TIME_RATE_LIMIT = 10
START_RATE_LIMIT = 10  # (per-user)
WAIT_RATE_LIMIT = 10  # (per-user)
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
PM_WARN_IDLE_TIME = 240
PART_GRACE_TIME = 30
QUIT_GRACE_TIME = 30
ACC_GRACE_TIME = 30
START_QUIT_DELAY = 10
#  controls how many people it does in one /msg; only works for messages that are the same
MAX_PRIVMSG_TARGETS = 4
# how many mode values can be specified at once; used only as fallback
MODELIMIT = 3
LEAVE_STASIS_PENALTY = 1
IDLE_STASIS_PENALTY = 1
PART_STASIS_PENALTY = 1
ACC_STASIS_PENALTY = 1
QUIET_DEAD_PLAYERS = False
DEVOICE_DURING_NIGHT = False
QUIET_MODE = "q" # "q" or "b"
QUIET_PREFIX = "" # "" or "~q:"
# The bot will automatically toggle those modes of people joining
AUTO_TOGGLE_MODES = ""

DYNQUIT_DURING_GAME = False # are dynamic quit messages used while a game is in progress? Note that true will break certain stats scrapers

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
ROLE_REVEAL = "on" # on/off/team - what role information is shown on death
STATS_TYPE = "default" # default/accurate/team/disabled - what role information is shown when doing !stats
LOVER_WINS_WITH_FOOL = False # if fool is lynched, does their lover win with them?
DEFAULT_SEEN_AS_VILL = True # non-wolves are seen as villager regardless of the default role

START_VOTES_SCALE = 0.3
START_VOTES_MAX = 4

# Debug mode settings, whether or not timers and stasis should apply during debug mode
DISABLE_DEBUG_MODE_TIMERS = True
DISABLE_DEBUG_MODE_TIME_LORD = False
DISABLE_DEBUG_MODE_REAPER = True
DISABLE_DEBUG_MODE_STASIS = True

# Minimum number of players needed for mad scientist to skip over dead people when determining who is next to them
# Set to 0 to always skip over dead players. Note this is number of players that !joined, NOT number of players currently alive
MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 16

CARE_BOLD = False
CARE_COLOR = False
KILL_COLOR = False
KILL_BOLD = False

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
FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE = 1/2

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night
ALPHA_WOLF_NIGHTS = 3 # alpha wolf turns the target into a wolf after this many nights (note the night they are bitten is considered night 1)

DOCTOR_IMMUNIZATION_MULTIPLIER = 0.135 # ceil(num_players * multiplier) = number of immunizations

TOTEM_ORDER   =                  (   "shaman"  , "crazed shaman" )
TOTEM_CHANCES = {       "death": (      1      ,        1        ),
                   "protection": (      1      ,        1        ),
                      "silence": (      1      ,        1        ),
                    "revealing": (      1      ,        1        ),
                  "desperation": (      1      ,        1        ),
                   "impatience": (      1      ,        1        ),
                     "pacifism": (      1      ,        1        ),
                    "influence": (      1      ,        1        ),
                   "narcolepsy": (      0      ,        1        ),
                     "exchange": (      0      ,        1        ),
                  "lycanthropy": (      0      ,        1        ),
                         "luck": (      0      ,        1        ),
                   "pestilence": (      0      ,        1        ),
                  "retribution": (      0      ,        1        ),
                 "misdirection": (      0      ,        1        ),
                }

GAME_MODES = {}
SIMPLE_NOTIFY = set()  # cloaks of people who !simple, who don't want detailed instructions
SIMPLE_NOTIFY_ACCS = set() # same as above, except accounts. takes precedence
PREFER_NOTICE = set()  # cloaks of people who !notice, who want everything /notice'd
PREFER_NOTICE_ACCS = set() # Same as above, except accounts. takes precedence

ACCOUNTS_ONLY = False # If True, will use only accounts for everything
DISABLE_ACCOUNTS = False # If True, all account-related features are disabled. Automatically set if we discover we do not have proper ircd support for accounts
                        # This will override ACCOUNTS_ONLY if it is set

NICKSERV = "NickServ"
NICKSERV_IDENTIFY_COMMAND = "IDENTIFY {account} {password}"
NICKSERV_GHOST_COMMAND = "GHOST {nick}"
NICKSERV_RELEASE_COMMAND = "RELEASE {nick}"
NICKSERV_REGAIN_COMMAND = "REGAIN {nick}"
CHANSERV = "ChanServ"
CHANSERV_OP_COMMAND = "OP {channel}"

STASISED = defaultdict(int)
STASISED_ACCS = defaultdict(int)

# TODO: move this to a game mode called "fixed" once we implement a way to randomize roles (and have that game mode be called "random")
DEFAULT_ROLE = "villager"
ROLE_INDEX =                      (  4  ,  6  ,  7  ,  8  ,  9  , 10  , 11  , 12  , 13  , 15  , 16  , 18  , 20  , 21  , 23  , 24  )
ROLE_GUIDE = OrderedDict([ # This is order-sensitive - many parts of the code rely on this order!
             # wolf roles
             ("wolf"            , (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  3  ,  3  ,  3  )),
             ("alpha wolf"      , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("werecrow"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("werekitten"      , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("wolf mystic"     , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("fallen angel"    , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("wolf cub"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("traitor"         , (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("hag"             , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  )),
             ("sorcerer"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  )),
             ("warlock"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("minion"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("cultist"         , (  0  ,  0  ,  1  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             # villager roles
             ("seer"            , (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("oracle"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("harlot"          , (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("shaman"          , (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("hunter"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("augur"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  )),
             ("detective"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("guardian angel"  , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("bodyguard"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("doctor"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("mad scientist"   , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("mystic"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("matchmaker"      , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("village drunk"   , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("time lord"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("villager"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             # neutral roles
             ("jester"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("fool"            , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("crazed shaman"   , (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("monster"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("piper"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("amnesiac"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  )),
             ("turncoat"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("clone"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("lycan"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("vengeful ghost"  , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             # templates
             ("cursed villager" , (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  )),
             ("gunner"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  )),
             # NB: for sharpshooter, numbers can't be higher than gunner, since gunners get converted to sharpshooters. This is the MAX number of gunners that can be converted.
             ("sharpshooter"    , (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("mayor"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  )),
             ("assassin"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("bureaucrat"      , (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ])

# Harlot dies when visiting, seer sees as wolf, gunner kills when shooting, GA and bodyguard have a chance at dying when guarding
# If every wolf role dies, and there are no remaining traitors, the game ends and villagers win (monster may steal win)
WOLF_ROLES = frozenset({"wolf", "alpha wolf", "werecrow", "wolf cub", "werekitten", "wolf mystic", "fallen angel"})
# Access to wolfchat, and counted towards the # of wolves vs villagers when determining if a side has won
WOLFCHAT_ROLES = WOLF_ROLES | {"traitor", "hag", "sorcerer", "warlock"}
# Wins with the wolves, even if the roles are not necessarily wolves themselves
WOLFTEAM_ROLES = WOLFCHAT_ROLES | {"minion", "cultist"}
# These roles either steal away wins or can otherwise win with any team
TRUE_NEUTRAL_ROLES = frozenset({"crazed shaman", "fool", "jester", "monster", "clone", "piper", "turncoat"})
# These are the roles that will NOT be used for when amnesiac turns, everything else is fair game! (var.DEFAULT_ROLE is also added if not in this set)
AMNESIAC_BLACKLIST = frozenset({"monster", "minion", "matchmaker", "clone", "doctor", "villager", "cultist", "piper"})
# These roles are seen as wolf by the seer/oracle
SEEN_WOLF = WOLF_ROLES | {"monster", "mad scientist"}
# These are seen as the default role (or villager) when seen by seer (this overrides SEEN_WOLF)
SEEN_DEFAULT = frozenset({"traitor", "hag", "sorcerer", "time lord", "villager", "cultist", "minion", "turncoat", "amnesiac",
                          "vengeful ghost", "lycan", "clone", "fool", "jester", "werekitten", "warlock", "piper"})

# The roles in here are considered templates and will be applied on TOP of other roles. The restrictions are a list of roles that they CANNOT be applied to
# NB: if you want a template to apply to everyone, list it here but make the restrictions an empty set. Templates not listed here are considered full roles instead
TEMPLATE_RESTRICTIONS = {"cursed villager" : SEEN_WOLF | {"seer", "oracle", "fool", "jester"},
                         "gunner"          : WOLFTEAM_ROLES | {"fool", "lycan", "jester"},
                         "sharpshooter"    : frozenset(), # the above gets automatically added to the set. this set is the list of roles that can be gunner but not sharpshooter
                         "mayor"           : frozenset({"fool", "jester", "monster"}),
                         "assassin"        : WOLF_ROLES | {"traitor", "seer", "augur", "oracle", "harlot", "detective", "bodyguard", "guardian angel", "lycan"},
                         "bureaucrat"      : frozenset(),
                        }

# make sharpshooter restrictions at least the same as gunner
TEMPLATE_RESTRICTIONS["sharpshooter"] |= TEMPLATE_RESTRICTIONS["gunner"]

# fallen angel can be assassin even though they are a wolf role
TEMPLATE_RESTRICTIONS["assassin"] -= {"fallen angel"}

# Roles listed here cannot be used in !fgame roles=blah. If they are defined in ROLE_GUIDE they may still be used.
DISABLED_ROLES = frozenset()

NO_VICTIMS_MESSAGES = ("The body of a young penguin pet is found.",
                       "Paw prints are found circling around the village.",
                       "A pool of blood and wolf paw prints are found.",
                       "The body of a slain cat is found.",
                       "Some house doors have been opened, but nothing has changed.",
                       "A scent much like that of a wolf permeates the air.",
                       "Half-buried wolf droppings are found.",
                       "Traces of wolf fur are found.")
LYNCH_MESSAGES = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002, who turned out to be... a{1} \u0002{2}\u0002.",
                  "After a prolonged struggle, \u0002{0}\u0002 is forced to the gallows, and is discovered after death to be a{1} \u0002{2}\u0002.",
                  "The villagers choose to hang \u0002{0}\u0002; however, the rope stretches and breaks, and the ensuing fall kills the \u0002{2}\u0002.",
                  "The villagers, heavy with the pain of death, reluctantly lynch \u0002{0}\u0002, a{1} \u0002{2}\u0002.",
                  "Compliant with the will of the village, the gallows prove effective in killing \u0002{0}\u0002, a{1} \u0002{2}\u0002.",
                  "Galvanized by fear, the mob puts \u0002{0}\u0002 to death. After inspection, they find that they have killed a{1} \u0002{2}\u0002.",
                  "In a fit of hysteria, the villagers lynch \u0002{0}\u0002, killing a{1} \u0002{2}\u0002.",
                  "Believing their fellow neighbor and friend to be dangerous, the mob puts \u0002{0}\u0002, a{1} \u0002{2}\u0002, to death.",
                  "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002, who turned out to be... a{1} \u0002{2}\u0002.",
                  "Despite protests, the mob drags their victim to the hanging tree. \u0002{0}\u0002 succumbs to the will of the horde, and is hanged. The villagers have killed a{1} \u0002{2}\u0002.",
                  "Resigned to the inevitable, \u0002{0}\u0002 is led to the gallows. Once the twitching stops, it is discovered that the village lynched a{1} \u0002{2}\u0002.",
                  "Before the rope is pulled, \u0002{0}\u0002, a{1} \u0002{2}\u0002, pulls the pin on a grenade. They hesitate, and it explodes, killing them.",
                  "Before the rope is pulled, \u0002{0}\u0002, a{1} \u0002{2}\u0002, throws a grenade at the mob. The grenade explodes early.")
LYNCH_MESSAGES_NO_REVEAL = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002.",
                            "After a prolonged struggle, \u0002{0}\u0002 is forced to the gallows.",
                            "The villagers choose to hang \u0002{0}\u0002; however, the rope stretches and breaks, and the ensuing fall kills them.",
                            "The villagers, heavy with the pain of death, reluctantly lynch \u0002{0}\u0002.",
                            "Compliant with the will of the village, the gallows prove effective in killing \u0002{0}\u0002.",
                            "Galvanized by fear, the mob puts \u0002{0}\u0002 to death.",
                            "In a fit of hysteria, the villagers lynch \u0002{0}\u0002.",
                            "Believing their fellow neighbor and friend to be dangerous, the mob puts \u0002{0}\u0002 to death.",
                            "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002.",
                            "Despite protests, the mob drags their victim to the hanging tree. \u0002{0}\u0002 succumbs to the will of the horde, and is hanged.",
                            "Resigned to the inevitable, \u0002{0}\u0002 is led to the gallows.",
                            "Before the rope is pulled, \u0002{0}\u0002 pulls the pin on a grenade. They hesitate, and it explodes, killing them.",
                            "Before the rope is pulled, \u0002{0}\u0002 throws a grenade at the mob. The grenade explodes early.")
QUIT_MESSAGES= ("\u0002{0}\u0002, a{1} \u0002{2}\u0002, suddenly falls over dead before the astonished villagers.",
                "While wearing a fake pair of antlers, \u0002{0}\u0002, a{1} \u0002{2}\u0002, is shot dead by a hunter.",
                "Standing under a tree, \u0002{0}\u0002, a{1} \u0002{2}\u0002, is killed by a falling branch.",
                "\u0002{0}\u0002, a{1} \u0002{2}\u0002, is killed by lightning before the villagers' eyes. The air smells of burnt flesh.",
                "Rampaging through the village, a bull gores \u0002{0}\u0002, a{1} \u0002{2}\u0002.",
                "\u0002{0}\u0002, a{1} \u0002{2}\u0002, falls into a vat of molasses and drowns.",
                "A pack of wild animals sets upon \u0002{0}\u0002. Soon the \u0002{2}\u0002 is only a pile of bones and a lump in the beasts' stomachs.",
                "\u0002{0}\u0002, a{1} \u0002{2}\u0002, fell off the roof of their house and is now dead.",
                "\u0002{0}\u0002 is crushed to death by a falling tree. The villagers desperately try to save the \u0002{2}\u0002, but it is too late.",
                "\u0002{0}\u0002 suddenly bursts into flames and is now all but a memory. The survivors bury the \u0002{2}\u0002's ashes.")
QUIT_MESSAGES_NO_REVEAL = ("\u0002{0}\u0002 suddenly falls over dead before the astonished villagers.",
                           "While wearing a fake pair of antlers, \u0002{0}\u0002 is shot dead by a hunter.",
                           "Standing under a tree, \u0002{0}\u0002 is killed by a falling branch.",
                           "\u0002{0}\u0002 is killed by lightning before the villagers' eyes. The air smells of burnt flesh.",
                           "Rampaging through the village, a bull gores \u0002{0}\u0002.",
                           "\u0002{0}\u0002 falls into a vat of molasses and drowns.",
                           "A pack of wild animals sets upon \u0002{0}\u0002. Soon they are only a pile of bones and a lump in the beasts' stomachs.",
                           "\u0002{0}\u0002 fell off the roof of their house and is now dead.",
                           "\u0002{0}\u0002 is crushed to death by a falling tree. The villagers desperately try to save them, but it is too late.",
                           "\u0002{0}\u0002 suddenly bursts into flames and is now all but a memory.")
PING_MESSAGES = ("Pong!", "Ping!", "Sure thing.", "No.", "!gniP", "!gnoP", "Segmentation fault", "Segmentation fault (core dumped)",
                 "{0}.exe has stopped working. Windows is checking for a solution to the problem...".format(botconfig.NICK), "HTTP Error 418: I'm a teapot",
                 "An error has pinged and has been ponged.", "I'm here!", "I refuse!", "What?", "Don't you mean \u0002{0}ping\u0002?".format(botconfig.CMD_CHAR),
                 "skynet.exe has stopped working. Windows is checking for a solution to the problem...", "No ping received for 1337 seconds.",
                 "Congratulations! You're the 1337th person to use {0}ping. You win a goat!".format(botconfig.CMD_CHAR), "PING! {nick}",
                 "I'm sorry Dave, I'm afraid I can't do that.", "Give me a ping, Vasily. One ping only, please.")


GIF_CHANCE = 1/50
FORTUNE_CHANCE = 1/25


RULES = (botconfig.CHANNEL + " channel rules: http://wolf.xnrand.com/rules")
DENY = {}
ALLOW = {}

DENY_ACCOUNTS = {}
ALLOW_ACCOUNTS = {}

# pingif-related mappings

PING_IF_PREFS = {}
PING_IF_PREFS_ACCS = {}

PING_IF_NUMS = {}
PING_IF_NUMS_ACCS = {}

is_role = lambda plyr, rol: rol in ROLES and plyr in ROLES[rol]

def match_hostmask(hostmask, nick, ident, host):
    # support n!u@h, u@h, or just h by itself
    matches = re.match('(?:(?:(.*?)!)?(.*?)@)?(.*)', hostmask.lower())

    if ((not matches.group(1) or fnmatch.fnmatch(nick.lower(), matches.group(1))) and
            (not matches.group(2) or fnmatch.fnmatch(ident.lower(), matches.group(2))) and
            fnmatch.fnmatch(host.lower(), matches.group(3))):
        return True

    return False


def check_priv(priv):
    assert priv in ("owner", "admin")

    # Owners can do everything
    hosts = set(botconfig.OWNERS)
    accounts = set(botconfig.OWNERS_ACCOUNTS)

    if priv == "admin":
        hosts.update(botconfig.ADMINS)
        accounts.update(botconfig.ADMINS_ACCOUNTS)

    def do_check(nick, ident=None, host=None, acc=None):
        if nick in USERS.keys():
            if not ident:
                ident = USERS[nick]["ident"]
            if not host:
                host = USERS[nick]["host"]
            if not acc:
                acc = USERS[nick]["account"]

        if not DISABLE_ACCOUNTS and acc and acc != "*":
            for pattern in accounts:
                if fnmatch.fnmatch(acc.lower(), pattern.lower()):
                    return True

        if host:
            for hostmask in hosts:
                if match_hostmask(hostmask, nick, ident, host):
                    return True

        return False

    return do_check

is_admin = check_priv("admin")
is_owner = check_priv("owner")

def irc_lower(nick):
    mapping = {
        "[": "{",
        "]": "}",
        "\\": "|",
        "^": "~",
    }

    if CASEMAPPING == "strict-rfc1459":
        mapping.pop("^")
    elif CASEMAPPING == "ascii":
        mapping = {}

    return nick.lower().translate(str.maketrans(mapping))

def irc_equals(nick1, nick2):
    return irc_lower(nick1) == irc_lower(nick2)

def plural(role):
    bits = role.split()
    bits[-1] = {"person": "people", "wolf": "wolves"}.get(bits[-1], bits[-1] + "s")
    return " ".join(bits)

def list_players(roles = None):
    if roles == None:
        roles = ROLES.keys()
    pl = set()
    for x in roles:
        if x in TEMPLATE_RESTRICTIONS.keys():
            continue
        for p in ROLES.get(x, ()):
            pl.add(p)
    return [p for p in ALL_PLAYERS if p in pl]

def list_players_and_roles():
    plr = {}
    for x in ROLES.keys():
        if x in TEMPLATE_RESTRICTIONS.keys():
            continue # only get actual roles
        for p in ROLES[x]:
            plr[p] = x
    return plr

def get_role(p):
    for role, pl in ROLES.items():
        if role in TEMPLATE_RESTRICTIONS.keys():
            continue # only get actual roles
        if p in pl:
            return role

def get_reveal_role(nick):
    if HIDDEN_TRAITOR and get_role(nick) == "traitor":
        role = DEFAULT_ROLE
    elif HIDDEN_AMNESIAC and nick in ORIGINAL_ROLES["amnesiac"]:
        role = "amnesiac"
    elif HIDDEN_CLONE and nick in ORIGINAL_ROLES["clone"]:
        role = "clone"
    else:
        role = get_role(nick)

    if ROLE_REVEAL != "team":
        return role

    if role in WOLFTEAM_ROLES:
        return "wolf"
    elif role in TRUE_NEUTRAL_ROLES:
        return "neutral player"
    else:
        return "villager"

def del_player(pname):
    prole = get_role(pname)
    ROLES[prole].remove(pname)
    tpls = get_templates(pname)
    for t in tpls:
        ROLES[t].remove(pname)
    if pname in BITTEN:
        del BITTEN[pname]
    if pname in BITTEN_ROLES:
        del BITTEN_ROLES[pname]
    if pname in CHARMED:
        CHARMED.remove(pname)

def get_templates(nick):
    tpl = []
    for x in TEMPLATE_RESTRICTIONS.keys():
        try:
            if nick in ROLES[x]:
                tpl.append(x)
        except KeyError:
            pass

    return tpl

role_order = lambda: ROLE_GUIDE

def break_long_message(phrases, joinstr = " "):
    message = []
    count = 0
    for phrase in phrases:
        # IRC max is 512, but freenode splits around 380ish, make 300 to have plenty of wiggle room
        if count + len(joinstr) + len(phrase) > 300:
            message.append("\n" + phrase)
            count = len(phrase)
        else:
            if not message:
                count = len(phrase)
            else:
                count += len(joinstr) + len(phrase)
            message.append(phrase)
    return joinstr.join(message)

class InvalidModeException(Exception): pass

# Persistence

conn = sqlite3.connect("data.sqlite3", check_same_thread = False)
c = conn.cursor()

def init_db():
    with conn:

        c.execute('CREATE TABLE IF NOT EXISTS simple_role_notify (cloak TEXT)') # people who understand each role (hostmasks - backup)

        c.execute('CREATE TABLE IF NOT EXISTS simple_role_accs (acc TEXT)') # people who understand each role (accounts - primary)

        c.execute('CREATE TABLE IF NOT EXISTS prefer_notice (cloak TEXT)') # people who prefer /notice (hostmasks - backup)

        c.execute('CREATE TABLE IF NOT EXISTS prefer_notice_acc (acc TEXT)') # people who prefer /notice (accounts - primary)

        c.execute('CREATE TABLE IF NOT EXISTS stasised (cloak TEXT, games INTEGER, UNIQUE(cloak))') # stasised people (cloaks)

        c.execute('CREATE TABLE IF NOT EXISTS stasised_accs (acc TEXT, games INTEGER, UNIQUE(acc))') # stasised people (accounts - takes precedence)

        c.execute('CREATE TABLE IF NOT EXISTS denied (cloak TEXT, command TEXT, UNIQUE(cloak, command))') # DENY

        c.execute('CREATE TABLE IF NOT EXISTS denied_accs (acc TEXT, command TEXT, UNIQUE(acc, command))') # DENY_ACCOUNTS

        c.execute('CREATE TABLE IF NOT EXISTS allowed (cloak TEXT, command TEXT, UNIQUE(cloak, command))') # ALLOW

        c.execute('CREATE TABLE IF NOT EXISTS allowed_accs (acc TEXT, command TEXT, UNIQUE(acc, command))') # ALLOW_ACCOUNTS

        c.execute('CREATE TABLE IF NOT EXISTS pingif_prefs (user TEXT, is_account BOOLEAN, players INTEGER, PRIMARY KEY(user, is_account))') # pingif player count preferences
        c.execute('CREATE INDEX IF NOT EXISTS ix_ping_prefs_pingif ON pingif_prefs (players ASC)') # index apparently makes it faster

        c.execute('PRAGMA table_info(pre_restart_state)')
        try:
            next(c)
        except StopIteration:
            c.execute('CREATE TABLE pre_restart_state (players TEXT)')
            c.execute('INSERT INTO pre_restart_state (players) VALUES (NULL)')

        c.execute('SELECT * FROM simple_role_notify')
        for row in c:
            SIMPLE_NOTIFY.add(row[0])

        c.execute('SELECT * FROM simple_role_accs')
        for row in c:
            SIMPLE_NOTIFY_ACCS.add(row[0])

        c.execute('SELECT * FROM prefer_notice')
        for row in c:
            PREFER_NOTICE.add(row[0])

        c.execute('SELECT * FROM prefer_notice_acc')
        for row in c:
            PREFER_NOTICE_ACCS.add(row[0])

        c.execute('SELECT * FROM stasised')
        for row in c:
            STASISED[row[0]] = row[1]

        c.execute('SELECT * FROM stasised_accs')
        for row in c:
            STASISED_ACCS[row[0]] = row[1]

        c.execute('SELECT * FROM denied')
        for row in c:
            if row[0] not in DENY:
                DENY[row[0]] = set()
            DENY[row[0]].add(row[1])

        c.execute('SELECT * FROM denied_accs')
        for row in c:
            if row[0] not in DENY_ACCOUNTS:
                DENY_ACCOUNTS[row[0]] = set()
            DENY_ACCOUNTS[row[0]].add(row[1])

        c.execute('SELECT * FROM allowed')
        for row in c:
            if row[0] not in ALLOW:
                ALLOW[row[0]] = set()
            ALLOW[row[0]].add(row[1])

        c.execute('SELECT * FROM allowed_accs')
        for row in c:
            if row[0] not in ALLOW_ACCOUNTS:
                ALLOW_ACCOUNTS[row[0]] = set()
            ALLOW_ACCOUNTS[row[0]].add(row[1])

        c.execute('SELECT * FROM pingif_prefs')
        for row in c:
            # is an account
            if row[1]:
                if row[0] not in PING_IF_PREFS_ACCS:
                    PING_IF_PREFS_ACCS[row[0]] = row[2]
                if row[2] not in PING_IF_NUMS_ACCS:
                    PING_IF_NUMS_ACCS[row[2]] = set()
                PING_IF_NUMS_ACCS[row[2]].add(row[0])
            # is a host
            else:
                if row[0] not in PING_IF_PREFS:
                    PING_IF_PREFS[row[0]] = row[2]
                if row[2] not in PING_IF_NUMS:
                    PING_IF_NUMS[row[2]] = set()
                PING_IF_NUMS[row[2]].add(row[0])

        # populate the roles table
        c.execute('DROP TABLE IF EXISTS roles')
        c.execute('CREATE TABLE roles (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT)')

        for x in list(ROLE_GUIDE):
            c.execute("INSERT OR REPLACE INTO roles (role) VALUES (?)", (x,))


        c.execute(('CREATE TABLE IF NOT EXISTS rolestats (player TEXT, role TEXT, '+
            'teamwins SMALLINT, individualwins SMALLINT, totalgames SMALLINT, '+
            'UNIQUE(player, role))'))


        c.execute(('CREATE TABLE IF NOT EXISTS gamestats (gamemode TEXT, size SMALLINT, villagewins SMALLINT, ' +
            'wolfwins SMALLINT, monsterwins SMALLINT, foolwins SMALLINT, piperwins SMALLINT, totalgames SMALLINT, UNIQUE(gamemode, size))'))


def remove_simple_rolemsg(clk):
    with conn:
        c.execute('DELETE from simple_role_notify where cloak=?', (clk,))

def add_simple_rolemsg(clk):
    with conn:
        c.execute('INSERT into simple_role_notify VALUES (?)', (clk,))

def remove_simple_rolemsg_acc(acc):
    with conn:
        c.execute('DELETE from simple_role_accs where acc=?', (acc,))

def add_simple_rolemsg_acc(acc):
    with conn:
        c.execute('INSERT into simple_role_accs VALUES (?)', (acc,))

def remove_prefer_notice(clk):
    with conn:
        c.execute('DELETE from prefer_notice where cloak=?', (clk,))

def add_prefer_notice(clk):
    with conn:
        c.execute('INSERT into prefer_notice VALUES (?)', (clk,))

def remove_prefer_notice_acc(acc):
    with conn:
        c.execute('DELETE from prefer_notice_acc where acc=?', (acc,))

def add_prefer_notice_acc(acc):
    with conn:
        c.execute('INSERT into prefer_notice_acc VALUES (?)', (acc,))

def set_stasis(clk, games):
    with conn:
        if games <= 0:
            c.execute('DELETE FROM stasised WHERE cloak=?', (clk,))
        else:
            c.execute('INSERT OR REPLACE INTO stasised VALUES (?,?)', (clk, games))

def set_stasis_acc(acc, games):
    with conn:
        if games <= 0:
            c.execute('DELETE FROM stasised_accs WHERE acc=?', (acc,))
        else:
            c.execute('INSERT OR REPLACE INTO stasised_accs VALUES (?,?)', (acc, games))

def add_deny(clk, command):
    with conn:
        c.execute('INSERT OR IGNORE INTO denied VALUES (?,?)', (clk, command))

def remove_deny(clk, command):
    with conn:
        c.execute('DELETE FROM denied WHERE cloak=? AND command=?', (clk, command))

def add_deny_acc(acc, command):
    with conn:
        c.execute('INSERT OR IGNORE INTO denied_accs VALUES (?,?)', (acc, command))

def remove_deny_acc(acc, command):
    with conn:
        c.execute('DELETE FROM denied_accs WHERE acc=? AND command=?', (acc, command))

def add_allow(clk, command):
    with conn:
        c.execute('INSERT OR IGNORE INTO allowed VALUES (?,?)', (clk, command))

def remove_allow(clk, command):
    with conn:
        c.execute('DELETE FROM allowed WHERE cloak=? AND command=?', (clk, command))

def add_allow_acc(acc, command):
    with conn:
        c.execute('INSERT OR IGNORE INTO allowed_accs VALUES (?,?)', (acc, command))

def remove_allow_acc(acc, command):
    with conn:
        c.execute('DELETE FROM allowed_accs WHERE acc=? AND command=?', (acc, command))

def set_pingif_status(user, is_account, players):
    with conn:
        c.execute('DELETE FROM pingif_prefs WHERE user=? AND is_account=?', (user, is_account))
        if players != 0:
            c.execute('INSERT OR REPLACE INTO pingif_prefs VALUES (?,?,?)', (user, is_account, players))

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

def update_game_stats(gamemode, size, winner):
    with conn:
        vwins, wwins, mwins, fwins, pwins, total = 0, 0, 0, 0, 0, 0

        c.execute("SELECT villagewins, wolfwins, monsterwins, foolwins, totalgames "+
                    "FROM gamestats WHERE gamemode=? AND size=?", (gamemode, size))
        row = c.fetchone()
        if row:
            vwins, wwins, mwins, fwins, total = row

        if winner == "wolves":
            wwins += 1
        elif winner == "villagers":
            vwins += 1
        elif winner == "monsters":
            mwins += 1
        elif winner == "pipers":
            pwins += 1
        elif winner.startswith("@"):
            fwins += 1
        total += 1

        c.execute("INSERT OR REPLACE INTO gamestats VALUES (?,?,?,?,?,?,?,?)",
                    (gamemode, size, vwins, wwins, mwins, fwins, pwins, total))

def get_player_stats(acc, role):
    if role.lower() not in [k.lower() for k in ROLE_GUIDE.keys()] and role != "lover":
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
            role_tmp = defaultdict(int)
            totalgames = 0
            while True:
                row = c.fetchone()
                if row:
                    role_tmp[row[0]] += row[1]
                    if row[0] not in TEMPLATE_RESTRICTIONS and row[0] != "lover":
                        totalgames += row[1]
                else:
                    break
            order = role_order()
            #ordered role stats
            role_totals = ["\u0002{0}\u0002: {1}".format(role, role_tmp[role]) for role in order if role in role_tmp]
            #lover or any other special stats
            role_totals += ["\u0002{0}\u0002: {1}".format(role, count) for role, count in role_tmp.items() if role not in order]
            return "\u0002{0}\u0002's totals | \u0002{1}\u0002 games | {2}".format(player[0], totalgames, break_long_message(role_totals, ", "))
        else:
            return "\u0002{0}\u0002 has not played any games.".format(acc)

def get_game_stats(gamemode, size):
    with conn:
        for row in c.execute("SELECT * FROM gamestats WHERE gamemode=? AND size=?", (gamemode, size)):
            msg = "\u0002%d\u0002 player games | Village wins: %d (%d%%), Wolf wins: %d (%d%%)" % (row[1], row[2], round(row[2]/row[7] * 100), row[3], round(row[3]/row[7] * 100))
            if row[4] > 0:
                msg += ", Monster wins: %d (%d%%)" % (row[4], round(row[4]/row[7] * 100))
            if row[5] > 0:
                msg += ", Fool wins: %d (%d%%)" % (row[5], round(row[5]/row[7] * 100))
            if row[6] > 0:
                msg += ", Piper wins: %d (%d%%)" % (row[6], round(row[6]/row[7] * 100))
            return msg + ", Total games: {0}".format(row[7])
        else:
            return "No stats for \u0002{0}\u0002 player games.".format(size)

def get_game_totals(gamemode):
    size_totals = []
    total = 0
    with conn:
        for size in range(MIN_PLAYERS, MAX_PLAYERS + 1):
            c.execute("SELECT size, totalgames FROM gamestats WHERE gamemode=? AND size=?", (gamemode, size))
            row = c.fetchone()
            if row:
                size_totals.append("\u0002{0}p\u0002: {1}".format(*row))
                total += row[1]

    if len(size_totals) == 0:
        return "No games have been played in the {0} game mode.".format(gamemode)
    else:
        return "Total games ({0}) | {1}".format(total, ", ".join(size_totals))

# vim: set expandtab:sw=4:ts=4:
