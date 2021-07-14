raise RuntimeError("src.settings incorrectly loaded")

MIN_PLAYERS = 6
MAX_PLAYERS = 24
ACCOUNT_PREFIX = "$a:" # "$a:" or "~a:"

START_VOTES_SCALE = 0.3
START_VOTES_MAX = 4

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night

GUEST_NICK_PATTERN = r"^Guest\d+$|^\d|away.+|.+away"

LOG_CHANNEL = "" # Log !fwarns to this channel, if set
LOG_PREFIX = "" # Message prefix for LOG_CHANNEL
DEV_CHANNEL = ""
DEV_PREFIX = ""
