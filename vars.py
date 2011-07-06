PING_WAIT = 300  # Seconds
MINIMUM_WAIT = 0 # debug, change to 60 for normal
EXTRA_WAIT = 20
MAXIMUM_WAITED = 2  # limit for amount of !wait's
MAX_SHOTS = 2
NIGHT_TIME_LIMIT = 90
DAY_TIME_LIMIT = 137

#######################################################################################
# ROLE INDEX:   PLAYERS     SEER    WOLF   CURSED   DRUNK   HARLOT  TRAITOR  GUNNER   #
ROLES_GUIDE = {    4    : (   1   ,   1   ,   0   ,   0   ,   0   ,    0   ,   0   ), #
                   6    : (   1   ,   1   ,   1   ,   1   ,   0   ,    0   ,   0   ), #
                   8    : (   1   ,   2   ,   1   ,   1   ,   1   ,    0   ,   0   ), #
                   10   : (   1   ,   2   ,   1   ,   1   ,   1   ,    1   ,   1   )} #
#######################################################################################

ROLE_INDICES = {0 : "seer",
                1 : "wolf",
                2 : "cursed",
                3 : "village drunk",
                4 : "harlot",
                5 : "traitor",
                6 : "gunner"}



NO_VICTIMS_MESSAGES = ("The body of a young penguin pet is found.",
                       "A pool of blood and wolf paw prints are found.",
                       "Traces of wolf fur are found.")
LYNCH_MESSAGES = ("The villagers, after much debate, finally decide on lynching \u0002{0}\u0002, who turned out to be... a \u0002{1}\u0002.",
                  "Under a lot of noise, the pitchfork-bearing villagers lynch \u0002{0}\u0002, who turned out to be... a \u0002{1}\u0002.",
                  "The mob drags a protesting \u0002{0}\u0002 to the hanging tree. S/He succumbs to the will of the horde, and is hanged. It is discovered (s)he was a \u0002{1}\u0002.",
                  "Resigned to his/her fate, \u0002{0}\u0002 is led to the gallows. After death, it is discovered (s)he was a \u0002{1}\u0002.")
                                              

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