import traceback
import argparse
import datetime
import socket
import time
import sys
import io

import botconfig
import src.settings as var

# Import the user-defined game modes
# These are not required, so failing to import it doesn't matter
# The file then imports our game modes
# Fall back to importing our game modes if theirs fail

try:
    import gamemodes
except ImportError:
    import src.gamemodes

# Handle launch parameters

# Argument --debug means start in debug mode
#          --verbose means to print a lot of stuff (when not in debug mode)
#          --normal means to override the above and use nothing
# Settings can be defined in the config, but launch argumentss override it

debug_mode = False
verbose = False
normal = False

# Carry over settings from botconfig into settings.py

for setting, value in botconfig.__dict__.items():
    if not setting.isupper():
        continue # Not a setting
    if setting == "DEBUG_MODE":
        debug_mode = value
    if setting == "VERBOSE_MODE":
        verbose = value
    if setting == "NORMAL_MODE":
        normal = value
    if not setting in var.__dict__.keys():
        continue # Don't carry over config-only settings

    # If we got that far, it's valid
    setattr(var, setting, value)

parser = argparse.ArgumentParser()
parser.add_argument('--debug', action='store_true')
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--normal', action='store_true')

args = parser.parse_args()

if args.debug: debug_mode = True
if args.verbose: verbose = True
if args.normal: normal = True

botconfig.DEBUG_MODE = debug_mode if not botconfig.DISABLE_DEBUG_MODE and not normal else False
botconfig.VERBOSE_MODE = verbose if not normal else False

# Initialize Database

var.init_db()

# Logger

# replace characters that can't be encoded with '?'
# since windows likes to use weird encodings by default
utf8stdout = open(1, 'w', errors="replace", closefd=False) # stdout

def get_timestamp(use_utc=None, ts_format=None):
    """Return a timestamp with timezone + offset from UTC."""
    if use_utc is None:
        use_utc = botconfig.USE_UTC
    if ts_format is None:
        ts_format = botconfig.TIMESTAMP_FORMAT
    if use_utc:
        tmf = datetime.datetime.utcnow().strftime(ts_format)
        tz = "UTC"
        offset = "+0000"
    else:
        tmf = time.strftime(ts_format)
        tz = time.tzname[0]
        offset = "+"
        if datetime.datetime.utcnow().hour > datetime.datetime.now().hour:
            offset = "-"
        offset += str(time.timezone // 36).zfill(4)
    return tmf.format(tzname=tz, tzoffset=offset).strip().upper() + " "

def logger(file, write=True, display=True):
    if file is not None:
        open(file, "a").close() # create the file if it doesn't exist
    def log(*output, write=write, display=display):
        output = " ".join([str(x) for x in output]).replace("\u0002", "").replace("\\x02", "") # remove bold
        if botconfig.DEBUG_MODE:
            write = True
        if botconfig.DEBUG_MODE or botconfig.VERBOSE_MODE:
            display = True
        timestamp = get_timestamp()
        if display:
            print(timestamp + output, file=utf8stdout)
        if write and file is not None:
            with open(file, "a", errors="replace") as f:
                f.seek(0, 2)
                f.write(timestamp + output + "\n")

    return log

stream_handler = logger(None)
debuglog = logger("debug.log", write=False, display=False)

def stream(output, level="normal"):
    if botconfig.VERBOSE_MODE or botconfig.DEBUG_MODE:
        stream_handler(output)
    elif level == "warning":
        stream_handler(output)

# Error handler

buffer = io.BufferedWriter(io.FileIO(file=sys.stderr.fileno(), mode="wb", closefd=False))

class ErrorHandler(io.TextIOWrapper):
    """Handle tracebacks sent to sys.stderr."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cli = None
        self.target_logger = None
        self.data = None

    def write(self, data):
        if self.closed:
            raise ValueError("write to closed file")
        if not isinstance(data, str):
            raise ValueError("can't write %s to text stream" % data.__class__.__name__)
        length = len(data)
        b = data.encode("utf-8", "replace")
        self.buffer.write(b)
        self.data = data
        self.flush()
        return length

    def flush(self):
        # Probably a syntax error on startup, so these aren't defined yet
        # If we do nothing, the error magically is printed to the console
        if self.cli is None or self.target_logger is None:
            return

        self.buffer.flush()

        if self.data is None:
            return

        exc = self.data.rstrip().splitlines()[-1].partition(":")[0]

        import builtins

        if "." in exc:
            import importlib
            module, dot, name = exc.rpartition(".")
            try:
                module = importlib.import_module(module)
            except ImportError:
                exc = Exception
            else:
                exc = getattr(module, name.strip())

        elif hasattr(builtins, exc):
            exc = getattr(builtins, exc)

        if not isinstance(exc, type) or not issubclass(exc, Exception):
            self.data = None
            return # not an actual exception

        msg = "An error has occurred and has been logged."
        if not botconfig.PASTEBIN_ERRORS or botconfig.CHANNEL != botconfig.DEV_CHANNEL:
            self.cli.msg(botconfig.CHANNEL, msg)
        if botconfig.PASTEBIN_ERRORS and botconfig.DEV_CHANNEL:
            try:
                with socket.socket() as sock:
                    sock.connect(("termbin.com", 9999))
                    sock.send(b"".join(s.encode("utf-8", "replace") for s in self.data) + b"\n")
                    url = sock.recv(1024).decode("utf-8")
            except socket.error:
                self.target_logger(self.data, display=False)
            else:
                self.cli.msg(botconfig.DEV_CHANNEL, " ".join((msg, url)))
        self.data = None

sys.stderr = ErrorHandler(buffer=buffer, encoding=sys.stderr.encoding,
             errors=sys.stderr.errors, line_buffering=sys.stderr.line_buffering)
