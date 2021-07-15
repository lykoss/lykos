raise RuntimeError("src.settings incorrectly loaded")

ACCOUNT_PREFIX = "$a:" # "$a:" or "~a:"

AMNESIAC_NIGHTS = 3 # amnesiac gets to know their actual role on this night

GUEST_NICK_PATTERN = r"^Guest\d+$|^\d|away.+|.+away"

LOG_CHANNEL = "" # Log !fwarns to this channel, if set
LOG_PREFIX = "" # Message prefix for LOG_CHANNEL
DEV_CHANNEL = ""
DEV_PREFIX = ""
