# Enforce a strict import ordering to ensure things are properly defined when they need to be

# Files with NO OTHER DEPENDENCIES on src
# This "bootstraps" the bot in preparation for importing the bulk of the code. Some imports
# change behavior based on whether or not we're in debug mode, so that must be established before
# we continue on to import other files
from src import config
from src.logger import stream, stream_handler, debuglog, errlog, plog
from src import events, lineparse, match

# Initialize config.Main
from pathlib import Path
import os
import sys

_bp = Path(__file__).parent
config.Main.load_metadata(_bp / "defaultsettings.yml")

_p = _bp.parent / "botconfig.yml"
if _p.is_file():
    config.Main.load_config(_bp.parent / "botconfig.yml")
del _p

if os.environ.get("BOTCONFIG", False):
    _cp = Path(os.environ["BOTCONFIG"])
    if not _cp.is_file():
        print("BOTCONFIG environment variable does not point to a valid file", file=sys.stderr)
        sys.exit(1)
    config.Main.load_config(_cp)
    del _cp

if os.environ.get("DEBUG", False):
    config.Main.set("debug.enabled", True)
    _dp = _bp.parent / "botconfig.debug.yml"
    if _dp.is_file():
        config.Main.load_config(_dp)
    del _dp

del _bp

# Files with dependencies only on things imported in previous lines, in order
# The top line must only depend on things imported above in our "no dependencies" block

from src import debug
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
