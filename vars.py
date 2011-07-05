PING_WAIT = 300  # Seconds
MINIMUM_WAIT = 0 # debug, change to 60 for normal
EXTRA_WAIT = 20
MAXIMUM_WAITED = 2  # limit for amount of !wait's
MAX_SHOTS = 2
NIGHT_TIME_LIMIT = 90

#######################################################################################
#               PLAYERS     SEER    WOLF   CURSED   DRUNK   HARLOT  TRAITOR  GUNNER   #
ROLES_GUIDE = {    4    : (   1   ,   1   ,   0   ,   0   ,   0   ,    0   ,   0   ), #
                   6    : (   0   ,   0   ,   1   ,   1   ,   0   ,    0   ,   0   ), #
                   8    : (   0   ,   1   ,   0   ,   0   ,   1   ,    0   ,   0   ), #
                   10   : (   0   ,   0   ,   0   ,   0   ,   0   ,    1   ,   1   )} #
#######################################################################################



NO_VICTIMS_MESSAGES = ("The body of a young penguin pet is found.",
                       "A pool of blood and wolf paw prints are found.",
                       "Traces of wolf fur are found.")

                                              

# These change ingame
ROLES = {"person" : []}
ORIGINAL_ROLES = None
PHASE = "none"  # "join", "day", or "night"
LAST_PING = 0
CURSED = ""  # nickname of cursed villager
WAITED = 0
GUNNERS = {}
VICTIM = ""  # nickname of to-be-killed villager
SEEN = []  # list of seers that have had visions
DEAD = []  # list of people who are dead
TRAITOR = ""
TIMERS = [None, None]  # nightlimit, daylimit
VOTES = {}
WOUNDED = []

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
    
get_role = lambda plyr: list_players_and_roles()[plyr]

def del_player(pname):
    prole = get_role(pname)
    ROLES[prole].remove(pname)