import fnmatch
import re
import threading
from collections import defaultdict, OrderedDict

import botconfig

LANGUAGE = 'en'
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
START_RATE_LIMIT = 10 # (per-user)
WAIT_RATE_LIMIT = 10  # (per-user)
GOAT_RATE_LIMIT = 300 # (per-user)
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
QUIT_GRACE_TIME = 60
ACC_GRACE_TIME = 30
START_QUIT_DELAY = 10
#  controls how many people it does in one /msg; only works for messages that are the same
MAX_PRIVMSG_TARGETS = 4
# how many mode values can be specified at once; used only as fallback
MODELIMIT = 3
QUIET_DEAD_PLAYERS = False
DEVOICE_DURING_NIGHT = False
ALWAYS_PM_ROLE = False
QUIET_MODE = "q" # "q" or "b"
QUIET_PREFIX = "" # "" or "~q:"
ACCOUNT_PREFIX = "$a:" # "$a:" or "~a:"
# The bot will automatically toggle those modes of people joining
AUTO_TOGGLE_MODES = ""

DEFAULT_EXPIRY = "30d"
LEAVE_PENALTY = 1
LEAVE_EXPIRY = "30d"
IDLE_PENALTY = 1
IDLE_EXPIRY = "30d"
PART_PENALTY = 1
PART_EXPIRY = "30d"
ACC_PENALTY = 1
ACC_EXPIRY = "30d"

# If True, disallows adding stasis via !fstasis (requires warnings instead)
RESTRICT_FSTASIS = True

# The formatting of this sucks, sorry. This is used to automatically apply sanctions to warning levels
# When a user crosses from below the min threshold to min or above points, the listed sanctions apply
# Sanctions also apply while moving within the same threshold bracket (such as from min to max)
# Valid sanctions are deny, stasis, scalestasis, and tempban
# Scalestasis applies stasis equal to the formula ax^2 + bx + c, where x is the number of warning points
# Tempban number can either be a duration (ending in d, h, or m) or a number meaning it expires when
# warning points fall below that threshold.
AUTO_SANCTION = (
        #min max sanctions
        (4, 6, {"stasis": 1}),
        (7, 19, {"scalestasis": (0, 1, -5)}),
        (20, 20, {"tempban": 10})
        )

# The following is a bitfield, and they can be mixed together
# Defaults to none of these, can be changed on a per-game-mode basis
RESTRICT_WOLFCHAT = 0x00

### DO NOT CHANGE THESE!
### They are for easier code interpretation/modification

RW_DISABLE_NIGHT    = 0x01 # Disable during night (commands are still relayed)
RW_DISABLE_DAY      = 0x02 # Disable during day (commands are still relayed)
RW_ONLY_KILL_CMD    = 0x04 # Only relay kill commands when wolfchat is disabled
RW_ONLY_SAME_CMD    = 0x08 # Only relay commands to other people who have access to the same command
RW_WOLVES_ONLY_CHAT = 0x10 # Non-wolves cannot participate in wolfchat (commands still relayed as applicable)
RW_NO_INTERACTION   = 0x20 # Do not relay commands to/from non-wolves regardless of other settings
RW_REM_NON_WOLVES   = 0x40 # Remove non-wolves from wolfchat entirely (can be killed, do not count towards wolf win condition, do not show in wolflist, etc.)
RW_TRAITOR_NON_WOLF = 0x80 # Consider traitor as a non-wolf for the purposes of the above restrictions (if unset, traitor is treated the same as wolf cub)

ENABLE_DEADCHAT = True # dead players can communicate with each other

DYNQUIT_DURING_GAME = False # are dynamic quit messages used while a game is in progress? Note that true will break certain stats scrapers

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

# How likely a default game is replaced by a villagergame game, 1 = 100% 0 = 0%
# villagergame has no wolves, the bot kills someone each night
# village wins if and only if they can unanimously !vote the bot during the day
VILLAGERGAME_CHANCE = 0

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

                        #    HALF    FULL
PROPHET_REVEALED_CHANCE = (  2/5  ,  4/5  )

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night

DOCTOR_IMMUNIZATION_MULTIPLIER = 0.135 # ceil(num_players * multiplier) = number of immunizations

TOTEM_ORDER   =                  (   "shaman"  , "crazed shaman" , "wolf shaman" )
TOTEM_CHANCES = {       "death": (      1      ,        1        ,       0       ),
                   "protection": (      1      ,        1        ,       1       ),
                      "silence": (      1      ,        1        ,       1       ),
                    "revealing": (      1      ,        1        ,       0       ),
                  "desperation": (      1      ,        1        ,       0       ),
                   "impatience": (      1      ,        1        ,       1       ),
                     "pacifism": (      1      ,        1        ,       1       ),
                    "influence": (      1      ,        1        ,       0       ),
                   "narcolepsy": (      0      ,        1        ,       0       ),
                     "exchange": (      0      ,        1        ,       0       ),
                  "lycanthropy": (      0      ,        1        ,       1       ),
                         "luck": (      0      ,        1        ,       1       ),
                   "pestilence": (      0      ,        1        ,       0       ),
                  "retribution": (      0      ,        1        ,       1       ),
                 "misdirection": (      0      ,        1        ,       1       ),
                       "deceit": (      0      ,        1        ,       1       ),
                }

GAME_MODES = {}
GAME_PHASES = ("night", "day") # all phases that constitute "in game", game modes can extend this with custom phases

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

GUEST_NICK_PATTERN = r"^Guest\d+$|^\d|away.+|.+away"

LOG_CHANNEL = "" # Log !fwarns to this channel, if set
LOG_PREFIX = "" # Message prefix for LOG_CHANNEL
DEV_CHANNEL = ""
DEV_PREFIX = ""
PASTEBIN_ERRORS = False

TRACEBACK_VERBOSITY = 2 # 0 = no locals at all, 1 = innermost frame's locals, 2 = all locals

# How often to ping the server (in seconds) to detect unclean disconnection
SERVER_PING_INTERVAL = 120

# Shorthand for naming roles, used to set up command aliases as well as be valid targets when
# specifying role names for things (such as !pstats or prophet's !pray)
ROLE_ALIASES = {
        "ga": "guardian angel",
        "drunk": "village drunk",
        "cs": "crazed shaman",
        "potato": "villager",
        }

# TODO: move this to a game mode called "fixed" once we implement a way to randomize roles (and have that game mode be called "random")
DEFAULT_ROLE = "villager"
ROLE_INDEX =                       (  4  ,  6  ,  7  ,  8  ,  9  , 10  , 11  , 12  , 13  , 15  , 16  , 18  , 20  , 21  , 23  , 24  )
ROLE_GUIDE = OrderedDict([ # This is order-sensitive - many parts of the code rely on this order!
             # wolf roles
             ("wolf"             , (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  3  ,  3  ,  3  )),
             ("alpha wolf"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("werecrow"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("werekitten"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("wolf mystic"      , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("wolf shaman"      , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("fallen angel"     , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("doomsayer"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("wolf cub"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("traitor"          , (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("hag"              , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  )),
             ("sorcerer"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  )),
             ("warlock"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("minion"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("cultist"          , (  0  ,  0  ,  1  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             # villager roles
             ("seer"             , (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("oracle"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("harlot"           , (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("shaman"           , (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("hunter"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("vigilante"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("augur"            , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  )),
             ("detective"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("prophet"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("guardian angel"   , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("bodyguard"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("priest"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("doctor"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("mad scientist"    , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("mystic"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("matchmaker"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("village drunk"    , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("time lord"        , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("villager"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             # neutral roles
             ("jester"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("fool"             , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("crazed shaman"    , (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("dullahan"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("monster"          , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("piper"            , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("amnesiac"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  )),
             ("turncoat"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("clone"            , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("lycan"            , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("wild child"       , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("vengeful ghost"   , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("succubus"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("demoniac"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             # templates
             ("cursed villager"  , (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  )),
             ("blessed villager" , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  )),
             ("gunner"           , (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  )),
             # NB: for sharpshooter, numbers can't be higher than gunner, since gunners get converted to sharpshooters. This is the MAX number of gunners that can be converted.
             ("sharpshooter"     , (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ("mayor"            , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  )),
             ("assassin"         , (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  )),
             ])

# Harlot dies when visiting, seer sees as wolf, gunner kills when shooting, GA and bodyguard have a chance at dying when guarding
# If every wolf role dies, and there are no remaining traitors, the game ends and villagers win (monster may steal win)
WOLF_ROLES = frozenset({"wolf", "alpha wolf", "werecrow", "wolf cub", "werekitten", "wolf mystic", "wolf shaman", "fallen angel", "doomsayer"})
# Access to wolfchat, and counted towards the # of wolves vs villagers when determining if a side has won
WOLFCHAT_ROLES = WOLF_ROLES | {"traitor", "hag", "sorcerer", "warlock"}
# Wins with the wolves, even if the roles are not necessarily wolves themselves
WOLFTEAM_ROLES = WOLFCHAT_ROLES | {"minion", "cultist"}
# These roles either steal away wins or can otherwise win with any team
TRUE_NEUTRAL_ROLES = frozenset({"crazed shaman", "fool", "jester", "monster", "clone", "piper", "turncoat", "succubus", "demoniac", "dullahan"})
# These are the roles that will NOT be used for when amnesiac turns, everything else is fair game! (var.DEFAULT_ROLE is also added if not in this set)
AMNESIAC_BLACKLIST = frozenset({"monster", "demoniac", "minion", "matchmaker", "clone", "doctor", "villager", "cultist", "piper", "dullahan", "wild child"})
# These roles are seen as wolf by the seer/oracle
SEEN_WOLF = WOLF_ROLES | {"monster", "mad scientist", "succubus"}
# These are seen as the default role (or villager) when seen by seer (this overrides SEEN_WOLF)
SEEN_DEFAULT = frozenset({"traitor", "hag", "sorcerer", "time lord", "villager", "cultist", "minion", "turncoat", "amnesiac",
                          "vengeful ghost", "lycan", "clone", "fool", "jester", "werekitten", "warlock", "piper", "demoniac"})
# These roles are notified that they are villager
HIDDEN_VILLAGERS = frozenset({"time lord"})
# These roles are notified that they are the default role. They also win alongside the default role barring other role-specific win conds.
HIDDEN_ROLES = frozenset({"vengeful ghost", "amnesiac"})
# These roles are win stealers, and are valid kills for vigilante
WIN_STEALER_ROLES = frozenset({"monster", "succubus", "demoniac", "piper", "fool"})

# these totems are beneficial for the *receiving* person, but can be detrimental to someone else acting on the receiver!
BENEFICIAL_TOTEMS = frozenset({"protection", "revealing", "desperation", "influence", "luck", "pestilence", "retribution"})

# The roles in here are considered templates and will be applied on TOP of other roles. The restrictions are a list of roles that they CANNOT be applied to
# NB: if you want a template to apply to everyone, list it here but make the restrictions an empty set. Templates not listed here are considered full roles instead
TEMPLATE_RESTRICTIONS = OrderedDict([
                        ("cursed villager"  , SEEN_WOLF | {"seer", "oracle", "fool", "jester", "priest"}),
                        ("gunner"           , WOLFTEAM_ROLES | {"fool", "lycan", "jester", "priest", "wild child"}),
                        ("sharpshooter"     , frozenset()), # the above gets automatically added to the set. this set is the list of roles that can be gunner but not sharpshooter
                        ("mayor"            , frozenset({"fool", "jester", "monster"})),
                        ("assassin"         , WOLF_ROLES | {"traitor", "seer", "augur", "oracle", "harlot", "detective", "bodyguard", "guardian angel", "lycan", "priest", "wild child"}),
                        ("blessed villager" , frozenset(ROLE_GUIDE.keys()) - {"villager", "blessed villager", "mayor"}),
                        ])

# make sharpshooter restrictions at least the same as gunner
TEMPLATE_RESTRICTIONS["sharpshooter"] |= TEMPLATE_RESTRICTIONS["gunner"]

# fallen angel can be assassin even though they are a wolf role
TEMPLATE_RESTRICTIONS["assassin"] -= {"fallen angel"}

# Roles listed here cannot be used in !fgame roles=blah. If they are defined in ROLE_GUIDE they may still be used.
DISABLED_ROLES = frozenset()

# Game modes that cannot be randomly picked or voted for
DISABLED_GAMEMODES = frozenset()

# Commands listed here cannot be used by anyone (even admins/owners)
DISABLED_COMMANDS = frozenset()

# Roles which have a command equivalent to the role name need to implement special handling for being
# passed their command again as a prefix and strip it out. For example, both !clone foo and !clone clone foo
# should be valid. Failure to add such a command to this set will result in the bot not starting
# with the error "ValueError: exclusive command already exists for ..."
ROLE_COMMAND_EXCEPTIONS = set()

GIF_CHANCE = 1/50

ALL_FLAGS = frozenset("AaDdFjms")

GRAVEYARD_LOCK = threading.RLock()
WARNING_LOCK = threading.RLock()
WAIT_TB_LOCK = threading.RLock()

# vim: set sw=4 expandtab:
