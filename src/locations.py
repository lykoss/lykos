from __future__ import annotations

from src import gamestate
from src.containers import UserDict
from src.users import User
from src.events import Event, event_listener

__all__ = ["Location", "VillageSquare", "Graveyard", "Forest", "Streets",
           "get_players_in_location", "get_location", "get_home",
           "move_player", "move_player_home", "set_home"]

# singleton cache of known locations; persisted between games
LOCATION_CACHE: dict[str, Location] = {}

# GameState extension to store location data for internal use
# Other modules **must** use the location API exposed in __all__
# instead of directly accessing these members
class GameState(gamestate.GameState):
    def __init__(self):
        self.home_locations: UserDict[User, Location] = UserDict()
        self.current_locations: UserDict[User, Location] = UserDict()

class Location:
    __slots__ = ("_name",)

    def __init__(self, name: str):
        self._name = name

    def __new__(cls, name: str):
        if name not in LOCATION_CACHE:
            obj = super().__new__(cls)
            obj.__init__(name)
            LOCATION_CACHE[name] = obj

        return LOCATION_CACHE[name]

    @property
    def name(self):
        return self._name

# default locations, always defined
VillageSquare = Location("square")
Graveyard = Location("graveyard")
Forest = Location("forest")
Streets = Location("streets")

def get_players_in_location(var: GameState, location: Location) -> set[User]:
    """ Get all players in a particular location.

    :param var: Game state
    :param location: Location to check
    :return: All users present in the given location, or an empty set if the location is vacant
    """
    return {p for p, loc in var.current_locations.items() if loc is location}

def get_location(var: GameState, player: User) -> Location:
    """ Get the location this player is present in.

    :param var: Game state
    :param player: Player to check
    :return: Location player is present in
    """
    return var.current_locations[player]

def get_home(var: GameState, player: User) -> Location:
    """ Get the player's home location.

    :param var: Game state
    :param player: Player to check
    :return: Player's home location
    """
    return var.home_locations[player]

def move_player(var: GameState, player: User, to: Location):
    """ Move player to a new location.

    :param var: Game state
    :param player: Player to move
    :param to: Player's new location
    """
    var.current_locations[player] = to

def move_player_home(var: GameState, player: User):
    """ Move player to their home location.

    :param var: Game state
    :param player: Player to move
    """
    var.current_locations[player] = var.home_locations[player]

def set_home(var: GameState, player: User, home: Location):
    """ Set player's home location.

    :param var: Game state
    :param player: Player to set
    :param home: New home
    """
    var.home_locations[player] = home

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: set[str], death_triggers: bool):
    if var.in_game:
        del var.home_locations[:player:]
        del var.current_locations[:player:]
