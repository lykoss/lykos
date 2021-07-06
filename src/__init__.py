# Enforce a strict import ordering to ensure things are properly defined when they need to be

# This "bootstraps" the bot in preparation for importing the bulk of the code. Some imports
# change behavior based on whether or not we're in debug mode, so that must be established before
# we continue on to import other files
from src import config, lineparse, match

# Initialize config.Main
config.init()

# Initialize logging framework
from src import logger
logger.init()

# Files with dependencies only on things imported in previous lines, in order
# The top line must only depend on things imported above in our "no dependencies" block
from src import debug
from src import events
from src import cats, messages
from src import context, functions, utilities
from src import db
from src import users
from src import channels, containers
from src import dispatcher
from src import decorators
from src import hooks, status, warnings
from src import pregame
from src import trans
from src import votes
from src import handler
from src import wolfgame
from src import game_stats

# Import the user-defined game modes
# These are not required, so failing to import it doesn't matter
# The file then imports our game modes
# Fall back to importing our game modes if theirs fail
# Do the same with roles

try:
    import roles # type: ignore
    # noinspection PyStatementEffect
    roles.CUSTOM_ROLES_DEFINED # type: ignore
except (ModuleNotFoundError, AttributeError):
    import src.roles

try:
    import gamemodes # type: ignore
    # noinspection PyStatementEffect
    gamemodes.CUSTOM_MODES_DEFINED # type: ignore
except (ModuleNotFoundError, AttributeError):
    import src.gamemodes
