ROLES = {"person" : []}
ORIGINAL_ROLES = None
PHASE = "none"  # "join", "day", or "night"
LAST_PING = 0
PING_WAIT = 300  # Seconds
WAIT = 60
WAITED = 0
GUNNERS = {}
MAX_SHOTS = 2

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