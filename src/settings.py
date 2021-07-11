raise RuntimeError("src.settings incorrectly loaded")

# token bucket for the IRC client; 1 token = 1 message sent to IRC
# Run the bot with --lagtest to receive settings recommendations for this
IRC_TB_INIT = 23 # initial number of tokens
IRC_TB_DELAY = 1.73 # wait time between adding tokens
IRC_TB_BURST = 23 # maximum number of tokens that can be accumulated
MIN_PLAYERS = 6
MAX_PLAYERS = 24
ACCOUNT_PREFIX = "$a:" # "$a:" or "~a:"

# Send a message to deadchat or wolfchat when a user spectates them
SPECTATE_NOTICE = True
# Whether to include which user is doing the spectating in the message
SPECTATE_NOTICE_USER = False

GUARDIAN_ANGEL_CAN_GUARD_SELF = True

START_VOTES_SCALE = 0.3
START_VOTES_MAX = 4

GUARDIAN_ANGEL_DIES_CHANCE = 0
BODYGUARD_DIES_CHANCE = 0
DETECTIVE_REVEALED_CHANCE = 2/5
FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE = 1/2

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night

DOCTOR_IMMUNIZATION_MULTIPLIER = 0.135 # ceil(num_players * multiplier) = number of immunizations

GUEST_NICK_PATTERN = r"^Guest\d+$|^\d|away.+|.+away"

LOG_CHANNEL = "" # Log !fwarns to this channel, if set
LOG_PREFIX = "" # Message prefix for LOG_CHANNEL
DEV_CHANNEL = ""
DEV_PREFIX = ""
