raise RuntimeError("src.settings incorrectly loaded")

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
TIME_RATE_LIMIT = 10
START_RATE_LIMIT = 10 # (per-user)
WAIT_RATE_LIMIT = 10  # (per-user)
GOAT_RATE_LIMIT = 300 # (per-user)
MIN_PLAYERS = 6
MAX_PLAYERS = 24
JOIN_TIME_LIMIT = 3600
START_QUIT_DELAY = 10
QUIET_DEAD_PLAYERS = False
ACCOUNT_PREFIX = "$a:" # "$a:" or "~a:"

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

HIDDEN_TRAITOR = True
HIDDEN_AMNESIAC = False # amnesiac still shows as amnesiac if killed even after turning
HIDDEN_CLONE = False
GUARDIAN_ANGEL_CAN_GUARD_SELF = True

START_VOTES_SCALE = 0.3
START_VOTES_MAX = 4

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

# Game modes that cannot be randomly picked or voted for
DISABLED_GAMEMODES: FrozenSet[str] = frozenset()

ALL_FLAGS = frozenset("AaDdFgjmNpSsw")
