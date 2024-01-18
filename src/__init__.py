# Enforce a strict import ordering to ensure things are properly defined when they need to be

# This "bootstraps" the bot in preparation for importing the bulk of the code. Some imports
# change behavior based on whether or not we're in debug mode, so that must be established before
# we continue on to import other files
from src import config, lineparse, locks, match

# Initialize config.Main
config.init()

# Initialize logging framework
from src import logger
logger.init()

# Files with dependencies only on things imported in previous lines, in order
# The top line must only depend on things imported above in our "no dependencies" block
from src import debug
from src import events, transport
from src import cats, messages
from src import context, functions
from src import db
from src import users
from src import channels, containers
from src import dispatcher, gamestate
from src import decorators, locations
from src import game_stats, handler, hooks, status, warnings, relay
from src import reaper
from src import gamejoin, pregame
from src import votes
from src import trans
from src import gamecmds, wolfgame
from src import roles, gamemodes

# Import the user-defined roles, as well as builtins if custom roles don't exist or they want them
import roles as custom_roles # type: ignore
if not getattr(custom_roles, "CUSTOM_ROLES_DEFINED", False):
    roles.import_builtin_roles()

# Import the user-defined modes, as well as builtins if custom modes don't exist or they want them
import gamemodes as custom_gamemodes # type: ignore
if not getattr(custom_gamemodes, "CUSTOM_MODES_DEFINED", False):
    gamemodes.import_builtin_modes()

# Import user-defined hooks
import hooks as custom_hooks # type: ignore

# Perform final initialization
events.Event("init", {}).dispatch()
