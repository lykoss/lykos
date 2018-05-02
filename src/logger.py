import datetime
import time
import subprocess
import platform

import botconfig
import src.settings as var
from src import events

# maintain a log of all messages for the current game, wiped on game reset
# only populated if REPORT_ERRORS is True, otherwise is unnecessary overhead
_memlog = {}

def _clear_memlog(evt, var):
    for channel in _memlog:
        _memlog[channel].clear()
events.add_listener("reset", _clear_memlog)

def logger(file, write=True, display=True):
    if file is not None:
        open(file, "a").close() # create the file if it doesn't exist
        channel = file.split(".")[0]
    if file is None:
        channel = "*"
    _memlog[channel] = []
    def log(*output, write=write, display=display):
        output = " ".join([str(x) for x in output]).replace("\u0002", "").replace("\\x02", "") # remove bold
        if botconfig.DEBUG_MODE:
            write = True
        if botconfig.DEBUG_MODE or botconfig.VERBOSE_MODE:
            display = True
        timestamp = get_timestamp()
        if var.REPORT_ERRORS:
            _memlog[channel].append((time.monotonic(), output))
        if display:
            print(timestamp + output, file=utf8stdout)
        if write and file is not None:
            with open(file, "a", errors="replace") as f:
                f.seek(0, 2)
                f.write(timestamp + output + "\n")

    return log

stream_handler = logger(None)
debuglog = logger("debug.log", write=False, display=False)
errlog = logger("errors.log")
plog = stream_handler # use this instead of print so that logs have timestamps

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

def stream(output, level="normal"):
    if botconfig.VERBOSE_MODE or botconfig.DEBUG_MODE:
        plog(output)
    elif level in ("warning", "error"):
        plog(output)
    elif var.REPORT_ERRORS:
        plog(output, write=False, display=False)

def get_replay(source):
    """Retrieve the replay document."""
    try:
        ans = subprocess.check_output(["git", "log", "-n", "1", "--pretty=format:%h"])
        lykosver = ans.decode()
    except (OSError, subprocess.CalledProcessError):
        lykosver = None
    replay = {
        "version": 1,
        "timestamp": time.time(),
        "source": source,
        "system": {
            "lykos": lykosver,
            "python": platform.python_version()
            },
        "logs": _memlog,
        }
    if var.PHASE in var.GAME_PHASES:
        # should probably split this into an event, but since we're in an exception handler,
        # we can't necessarily guarantee that the event system is working properly
        replay["game"] = {
            "mode": var.CURRENT_GAMEMODE.name,
            "count": len(var.ALL_PLAYERS),
            "phase": var.PHASE,
            "days": var.DAY_COUNT,
            "nights": var.NIGHT_COUNT,
            "status": {
            "lycans": var.LYCANTHROPES,
                "lucky": var.LUCKY,
                "diseased": var.DISEASED,
                "misdirected": var.MISDIRECTED,
                "exchanged": var.EXCHANGED,
                "silenced": var.SILENCED,
                "immune": var.IMMUNIZED,
                "protected": var.ACTIVE_PROTECTIONS
                }
            "players": var.ALL_PLAYERS,
            "rolemap": {
                "original": var.ORIGINAL_ROLES,
                "current": var.ROLES
                },
            "mainroles": {
                "original": var.ORIGINAL_MAIN_ROLES,
                "current": var.MAIN_ROLES
                }
            }
    return replay

# vim: set sw=4 expandtab:
