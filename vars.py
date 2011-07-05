PING_WAIT = 300  # Seconds
MINIMUM_WAIT = 60
EXTRA_WAIT = 20
MAXIMUM_WAITED = 2  # limit for amount of !wait's
MAX_SHOTS = 2

# These change ingame
ROLES = {"person" : []}
ORIGINAL_ROLES = None
PHASE = "none"  # "join", "day", or "night"
LAST_PING = 0
CURSED = ""  # nickname of cursed villager
GAME_START_TIME = 0
CAN_START_TIME = 0
WAITED = 0
GUNNERS = {}

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