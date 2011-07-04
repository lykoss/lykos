GAME_STARTED = False
ROLES = {"person" : []}
ORIGINAL_ROLES = None
PHASE = "none"  # "join", "day", or "night"
GUNNERS = {}
MAX_SHOTS = 2

is_role = lambda plyr, rol: rol in ROLES and plyr in ROLES[rol]

def plural(role):
    if role == "wolf": return "wolves"
    elif role == "person": return "people"
    else: return role + "s"