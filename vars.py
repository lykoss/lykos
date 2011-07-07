PING_WAIT = 300  # Seconds
MINIMUM_WAIT = 0 # debug, change to 60 for normal
EXTRA_WAIT = 20
MAXIMUM_WAITED = 2  # limit for amount of !wait's
MAX_SHOTS = 2
DRUNK_SHOTS_MULTIPLIER = 3
NIGHT_TIME_LIMIT = 0
DAY_TIME_LIMIT = 0

                    #       HIT    MISS    SUICIDE
GUN_CHANCES         =   (   5/7  ,  1/7  ,   1/7   )
DRUNK_GUN_CHANCES   =   (   4/7  ,  2/7  ,   1/7   )
MANSLAUGHTER_CHANCE =       1/5

GAME_MODES = {}

############################################################################################
# ROLE INDEX:   PLAYERS     SEER    WOLF   CURSED   DRUNK   HARLOT  TRAITOR  GUNNER   CROW #
ROLES_GUIDE = {    4    : (   1   ,   1   ,   0   ,   0   ,   0   ,    0   ,   0   ,   0), #
                   6    : (   0   ,   1   ,   0   ,   5   ,   0   ,    0   ,   5   ,   0), #
                   8    : (   1   ,   2   ,   1   ,   1   ,   1   ,    0   ,   0   ,   0), #
                   10   : (   1   ,   2   ,   1   ,   1   ,   1   ,    1   ,   1   ,   0)} #
############################################################################################

ROLE_INDICES = {0 : "seer",
                1 : "wolf",
                2 : "cursed",
                3 : "village drunk",
                4 : "harlot",
                5 : "traitor",
                6 : "gunner",
                7 : "werecrow"}



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


    
class InvalidModeException(object): pass
def game_mode(name):
    def decor(c):
        GAME_MODES[name] = c
        return c
    return decor

    
CHANGEABLE_ROLES = { "seer" : 0,
                     "wolf" : 1,
                    "drunk" : 3,
                   "harlot" : 4,
                  "traitor" : 5,
                   "gunner" : 6,
                 "werecrow" : 7 }
    
#  !game roles wolves:1 seers:0

# TODO: implement game modes
@game_mode("roles")
class ChangedRolesMode(object):
    ROLES_GUIDE = ROLES_GUIDE.copy()
    def __init__(self, arg):
        pairs = arg.split(" ")
        if len(parts) == 1:
            raise InvalidModeException("Invalid syntax for !game roles.")
        for pair in pairs:
            change = pair.split(":")
            if len(change) != 2:
                raise InvalidModeException("Invalid syntax for !game roles.")
            role, num = change
            try:
                num = int(num)
            except ValueError:
                raise InvalidModeException("A bad value was used in !game roles.")
            for x in self.ROLES_GUIDE.keys():
                lx = list(x)
                try:
                    lx[CHANGEABLE_ROLES[role.lower()]] = num
                except KeyError:
                    raise InvalidModeException('"{0}" is not a changeable role.'.format(role))
                self.ROLES_GUIDE[x] = tuple(lx)
                pl = list_players()
        if len(pl) < sum(self.ROLES_GUIDE[4]):
            raise InvalidModeException("Too few players for such these custom roles.")
            