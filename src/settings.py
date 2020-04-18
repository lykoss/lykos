import fnmatch
import re
import threading
from collections import OrderedDict

LANGUAGE = 'en'

MINIMUM_WAIT = 60
EXTRA_WAIT = 30
EXTRA_WAIT_JOIN = 0 # Add this many seconds to the waiting time for each !join
WAIT_AFTER_JOIN = 25 # Wait at least this many seconds after the last join
# token bucket for the IRC client; 1 token = 1 message sent to IRC
# Run the bot with --lagtest to receive settings recommendations for this
IRC_TB_INIT = 23 # initial number of tokens
IRC_TB_DELAY = 1.73 # wait time between adding tokens
IRC_TB_BURST = 23 # maximum number of tokens that can be accumulated
# !wait uses a token bucket
WAIT_TB_INIT  = 2   # initial number of tokens
WAIT_TB_DELAY = 240 # wait time between adding tokens
WAIT_TB_BURST = 3   # maximum number of tokens that can be accumulated
STATS_RATE_LIMIT = 60
VOTES_RATE_LIMIT = 60
ADMINS_RATE_LIMIT = 300
GSTATS_RATE_LIMIT = 0
PSTATS_RATE_LIMIT = 0
RSTATS_RATE_LIMIT = 0
TIME_RATE_LIMIT = 10
START_RATE_LIMIT = 10 # (per-user)
WAIT_RATE_LIMIT = 10  # (per-user)
GOAT_RATE_LIMIT = 300 # (per-user)
MIN_PLAYERS = 4
MAX_PLAYERS = 24
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
TIME_LORD_NIGHT_WARN = 0
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
# Give penalties if idling night.
# All other penalties take precedence over night penalties; only one penalty will be given per game.
NIGHT_IDLE_PENALTY = 1
NIGHT_IDLE_EXPIRY = "14d"

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
        (6, 10, {"stasis": 1}),
        (11, 15, {"scalestasis": (0, 1, -8)}),
        (16, 16, {"tempban": 8})
        )

# Send a message to deadchat or wolfchat when a user spectates them
SPECTATE_NOTICE = True
# Whether to include which user is doing the spectating in the message
SPECTATE_NOTICE_USER = False

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

ABSTAIN_ENABLED = True # whether village can !abstain in order to not vote anyone during day
LIMIT_ABSTAIN = True # if true, village will be limited to successfully !abstaining a vote only once
SELF_LYNCH_ALLOWED = True
HIDDEN_TRAITOR = True
HIDDEN_AMNESIAC = False # amnesiac still shows as amnesiac if killed even after turning
HIDDEN_CLONE = False
GUARDIAN_ANGEL_CAN_GUARD_SELF = True
START_WITH_DAY = False
ROLE_REVEAL = "on" # on/off/team - what role information is shown on death
STATS_TYPE = "default" # default/accurate/team/disabled - what role information is shown when doing !stats

START_VOTES_SCALE = 0.3
START_VOTES_MAX = 4

# Custom settings to disable auto bot moderating
DISABLE_TIMERS = False
DISABLE_TIME_LORD = False
DISABLE_REAPER = False
DISABLE_STASIS = False

# Debug mode settings, whether or not timers and stasis should apply during debug mode
DISABLE_DEBUG_MODE_TIMERS = True
DISABLE_DEBUG_MODE_TIME_LORD = False
DISABLE_DEBUG_MODE_REAPER = True
DISABLE_DEBUG_MODE_STASIS = True
DEBUG_MODE_NOTHROW_MESSAGES = True

# number of bullets a gunner role gets when the role is assigned or swapped in
SHOTS_MULTIPLIER = {
    "gunner": 0.12,
    "sharpshooter": 0.06,
    "wolf gunner": 0.06
}

# hit, miss, and headshot chances for each gunner role (explode = 1 - hit - miss)
GUN_CHANCES = {
    "gunner": (15/20, 4/20, 4/20), # 75% hit, 20% miss, 5% explode, 20% headshot
    "sharpshooter": (1, 0, 1), # 100% hit, 0% miss, 0% explode, 100% headshot
    "wolf gunner": (14/20, 6/20, 12/20) # 70% hit, 30% miss, 0% explode, 60% headshot
}

# modifier applied to regular gun chances if the user is also drunk
DRUNK_GUN_CHANCES = (-5/20, 4/20, -3/20) # -25% hit, +20% miss, +5% explode, -15% headshot
DRUNK_SHOTS_MULTIPLIER = 3
GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE = 1/4
# at night, the wolf can steal 1 bullet from the victim and become a wolf gunner
# (will always be 1 bullet regardless of SHOTS_MULTIPLIER setting for wolf gunner above)
WOLF_STEALS_GUN = True

GUARDIAN_ANGEL_DIES_CHANCE = 0
BODYGUARD_DIES_CHANCE = 0
DETECTIVE_REVEALED_CHANCE = 2/5
FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE = 1/2

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night

DOCTOR_IMMUNIZATION_MULTIPLIER = 0.135 # ceil(num_players * multiplier) = number of immunizations

GAME_MODES = {}
GAME_PHASES = ("night", "day") # all phases that constitute "in game", game modes can extend this with custom phases

SSL_VERIFY = True
SSL_CERTFP = ()
# Tracking Mozilla's "intermediate" compatibility list -- https://wiki.mozilla.org/Security/Server_Side_TLS#Intermediate_compatibility_.28default.29
SSL_CIPHERS = ( # single string split over multiple lines - lack of commas intentional
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-"
    "SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-"
    "SHA256:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-RSA-"
    "AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:ECDHE-RSA-DES-CBC3-"
    "SHA:EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS"
)
SSL_CERTFILE = None
SSL_KEYFILE = None

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

# Data collection settings. lykos will send details about errors that happen to the lykos developers,
# these settings control how much data is sent. Please see https://werewolf.chat/dc for more information.
# These settings additionally impacts what data is written to the error log.
TRACEBACK_VERBOSITY = 2  # 0 = no locals at all, 1 = innermost frame's locals, 2 = all locals
USER_DATA_LEVEL = 0  # 0 = fully anonymize users, 1 = expose nick only, 2 = expose full hostmask, account, and channel membership
CHANNEL_DATA_LEVEL = 0  # 0 = fully anonymize channels, 1 = expose channel name

# How often to ping the server (in seconds) to detect unclean disconnection
SERVER_PING_INTERVAL = 120

# The default role can be anything, but HIDDEN_ROLE must be either "villager" or "cultist";
# hidden roles are informed they are HIDDEN_ROLE (ergo that role should not have any abilities),
# and win with that role's team. Seer sees all non-safe and non-cursed roles as HIDDEN_ROLE.
DEFAULT_ROLE = "villager"
HIDDEN_ROLE = "villager"

# Roles listed here cannot be used in !fgame roles=blah.
DISABLED_ROLES = frozenset()

# Game modes that cannot be randomly picked or voted for
DISABLED_GAMEMODES = frozenset()

# Commands listed here cannot be used by anyone (even admins/owners)
DISABLED_COMMANDS = frozenset()

GIF_CHANCE = 1/50

ALL_FLAGS = frozenset("AaDdFgjmNpSsw")

GRAVEYARD_LOCK = threading.RLock()
WARNING_LOCK = threading.RLock()

# vim: set sw=4 expandtab:
