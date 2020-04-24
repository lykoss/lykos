import argparse

# Enforce a strict import ordering to ensure things are properly defined when they need to be

# Parse command line args
# Argument --debug means start in debug mode (implies --config debug as well)
#          --config <name> Means to load settings from the configuration file botconfig.name.yml, overriding
#              whatever is present in botconfig.yml. If specified alongside --debug, this takes precedence
#              over the implicit --config debug.
# Settings can be defined in the config, but launch arguments override it
parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true', help="Run bot in debug mode. Loads botconfig.debug.yml if it exists, unless --config is specified.")
parser.add_argument('--config', help="Configuration file to load in addition to botconfig.yml. Ex: --config foo loads botconfig.foo.yml")

args = parser.parse_args()

# Bootstrap our configuration
from src import config
config.init()

if args.config:
    config.load(args.config)
elif args.debug:
    config.load("debug")

if args.debug:
    config.set_debug_mode(True)

config.finalize()

# Files with NO OTHER DEPENDENCIES on src
# This "bootstraps" the bot in preparation for importing the bulk of the code. Some imports
# change behavior based on whether or not we're in debug mode, so that must be established before
# we continue on to import other files
from src.logger import stream, stream_handler, debuglog, errlog, plog
from src import debug, events, lineparse, match

# Files with dependencies only on things imported in previous lines, in order
# The top line must only depend on things imported above in our "no dependencies" block
# All botconfig and settings are fully established at this point and are safe to use

from src import cats, messages
from src import context, functions, utilities
from src import db
from src import users
from src import channels, containers
from src import dispatcher
from src import decorators
from src import hooks, status, warnings
from src import pregame
from src import votes
from src import wolfgame
from src import handler

# Import the user-defined game modes
# These are not required, so failing to import it doesn't matter
# The file then imports our game modes
# Fall back to importing our game modes if theirs fail
# Do the same with roles

try:
    import roles # type: ignore
    roles.CUSTOM_ROLES_DEFINED
except (ModuleNotFoundError, AttributeError):
    import src.roles

try:
    import gamemodes # type: ignore
    gamemodes.CUSTOM_MODES_DEFINED
except (ModuleNotFoundError, AttributeError):
    import src.gamemodes
