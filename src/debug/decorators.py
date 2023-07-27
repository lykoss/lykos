from __future__ import annotations

import json
import platform
import re
import subprocess
import threading
import traceback
import urllib.request
import logging
import inspect
from typing import Optional
from types import TracebackType, FrameType

from src import config

__all__ = ["handle_error"]

class _LocalCls(threading.local):
    handler: Optional[chain_exceptions] = None
    level = 0

_local = _LocalCls()

# This is a mapping of stringified tracebacks to (link, uuid) tuples
# That way, we don't have to call in to the website every time we have
# another error.

_tracebacks: dict[str, tuple[str, str]] = {}

class chain_exceptions:

    def __init__(self, exc, *, suppress_context=False):
        self.exc = exc
        self.suppress_context = suppress_context

    def __enter__(self):
        return self

    def __exit__(self, exc, value, tb):
        if exc is value is tb is None:
            return False

        value.__context__ = self.exc
        value.__suppress_context__ = self.suppress_context
        self.exc = value
        return True

    @property
    def traceback(self):
        return "".join(traceback.format_exception(type(self.exc), self.exc, self.exc.__traceback__))

class print_traceback:

    def __enter__(self):
        _local.level += 1
        return self

    def __exit__(self, exc_type: Optional[type], exc_value: Optional[BaseException], tb: Optional[TracebackType]):
        if exc_type is None or exc_value is None or tb is None:
            _local.level -= 1
            return False

        if not issubclass(exc_type, Exception):
            _local.level -= 1
            return False

        if _local.level > 1:
            _local.level -= 1
            return False # the outermost caller should handle this

        from src import channels
        from src.messages import messages
        exc_log = logging.getLogger("exception.{}".format(exc_type.__name__))
        exc_tb = tb
        variables = ["", ""]
        game_state = None

        if _local.handler is None:
            _local.handler = chain_exceptions(exc_value)

        traceback_verbosity = config.Main.get("telemetry.errors.traceback_verbosity")
        if traceback_verbosity > 0:
            word = "\nLocal variables from frame #{0} (in {1}):\n"
            variables.append("")
            frames: list[Optional[FrameType]] = []

            while tb is not None:
                ignore_locals = not tb.tb_frame.f_locals or tb.tb_frame.f_locals.get("_ignore_locals_")
                # also ignore locals for library code
                if "/lib/" in tb.tb_frame.f_code.co_filename.replace("\\", "/"):
                    ignore_locals = True
                if tb.tb_next is not None and ignore_locals:
                    frames.append(None)
                else:
                    frames.append(tb.tb_frame)
                tb = tb.tb_next

            if traceback_verbosity < 2:
                word = "Local variables from innermost frame (in {1}):\n"
                frames = [frames[-1]]

            with _local.handler:
                from src.gamestate import GameState, PregameState
                from src.dispatcher import MessageDispatcher
                for i, frame in enumerate(frames, start=1):
                    if frame is None:
                        continue
                    variables.append(word.format(i, frame.f_code.co_name))
                    for name, value in frame.f_locals.items():
                        # Capture game state for later display
                        if isinstance(value, GameState) or isinstance(value, PregameState):
                            game_state = value
                        elif isinstance(value, MessageDispatcher) and value.game_state is not None:
                            game_state = value.game_state

                        try:
                            if isinstance(value, dict):
                                try:
                                    log_value = "{{{0}}}".format(", ".join("{0:for_tb}: {1:for_tb}".format(k, v) for k, v in value.items()))
                                except (TypeError, ValueError):
                                    try:
                                        log_value = "{{{0}}}".format(", ".join("{0!r}: {1:for_tb}".format(k, v) for k, v in value.items()))
                                    except (TypeError, ValueError):
                                        log_value = "{{{0}}}".format(", ".join("{0:for_tb}: {1!r}".format(k, v) for k, v in value.items()))
                            elif isinstance(value, list):
                                log_value = "[{0}]".format(", ".join(format(v, "for_tb") for v in value))
                            elif isinstance(value, set):
                                log_value = "{{{0}}}".format(", ".join(format(v, "for_tb") for v in value))
                            else:
                                log_value = format(value, "for_tb")
                        except (TypeError, ValueError):
                            log_value = repr(value)
                        variables.append("{0} = {1}".format(name, log_value))

            if len(variables) > 3:
                if traceback_verbosity > 1:
                    variables[2] = "Local variables in all frames (most recent call last):"
                else:
                    variables[2] = ""
            else:
                variables[2] = "No local variables found in all frames."

        variables[1] = _local.handler.traceback

        # dump game state if we found it in our traceback
        if game_state is not None:
            variables.append("\nGame state:\n")
            for key, value in inspect.getmembers(game_state):
                # Skip over things like __module__, __dict__, and __weakrefs__
                if key.startswith("__") and key.endswith("__"):
                    continue
                # Only interested in data members, not properties or methods
                if isinstance(value, property) or callable(value):
                    continue
                try:
                    variables.append("{0} = {1:for_tb}".format(key, value))
                except (TypeError, ValueError):
                    variables.append("{0} = {1!r}".format(key, value))

        # dump full list of known users with verbose output, as everything above has truncated output for readability
        if config.Main.get("telemetry.errors.user_data_level") > 1:
            import src.users
            variables.append("\nAll connected users:\n")
            for user in src.users.users():
                variables.append("{0:x} = {1:for_tb_verbose}".format(id(user), user))
            if len(list(src.users.disconnected())) > 0:
                variables.append("\nAll disconnected users:\n")
                for user in src.users.disconnected():
                    variables.append("{0:x} = {1:for_tb_verbose}".format(id(user), user))
            else:
                variables.append("\nNo disconnected users.")

        # obtain bot version
        try:
            ans = subprocess.check_output(["git", "log", "-n", "1", "--pretty=format:%h"])
            variables[0] = "lykos {0}, Python {1}\n".format(str(ans.decode()), platform.python_version())
        except (OSError, subprocess.CalledProcessError):
            variables[0] = "lykos <unknown>, Python {0}\n".format(platform.python_version())

        # capture variables before sanitization for local logging
        extra_data = {"variables": "\n".join(variables)}

        # sanitize paths in tb: convert backslash to forward slash and remove prefixes from src and library paths
        variables[1] = variables[1].replace("\\", "/")
        variables[1] = re.sub(r'File "[^"]*/(src|gamemodes|oyoyo|roles|[Ll]ib|wolfbot)', r'File "/\1', variables[1])

        # sanitize values within local frames
        if len(variables) > 3:
            for i in range(3, len(variables)):
                # strip filenames out of module printouts
                variables[i] = re.sub(r"<(module .*?) from .*?>", r"<\1>", variables[i])

        if channels.Main:
            channels.Main.send(messages["error_log"])
        message = [str(messages["error_log"])]

        content = "\n".join(variables)

        link = _tracebacks.get(content)
        if link is None and not config.Main.get("debug.enabled"):
            api_url = "https://ww.chat/submit"
            data = None # prevent UnboundLocalError when error log fails to upload
            with _local.handler:
                req = urllib.request.Request(api_url, json.dumps({
                        "c": content,
                    }).encode("utf-8", "replace"))

                req.add_header("Accept", "application/json")
                req.add_header("Content-Type", "application/json; charset=utf-8")
                resp = urllib.request.urlopen(req)
                data = json.loads(resp.read().decode("utf-8"))

            if data is None:  # couldn't fetch the link
                message.append(messages["error_pastebin"].format())
                extra_data["paste_error"] = _local.handler.traceback
            else:
                link = _tracebacks[content] = data["url"]
                message.append(link)

        elif link is not None:
            message.append(link)

        exc_log.error(" ".join(message), exc_info=(exc_type, exc_value, exc_tb), extra=extra_data)

        _local.level -= 1
        if not _local.level: # outermost caller; we're done here
            _local.handler = None

        return True # a true return value tells the interpreter to swallow the exception

class handle_error:

    def __new__(cls, func=None, *, instance=None):
        if isinstance(func, type(cls)) and instance is func.instance: # already decorated
            return func

        self = super().__new__(cls)
        return self

    def __init__(self, func=None, *, instance=None):
        if isinstance(func, self.__class__):
            func = func.func
        self.instance = instance
        self.func = func

    def __get__(self, instance, owner):
        if instance is not self.instance:
            return type(self)(self.func, instance=instance)
        return self

    def __call__(*args, **kwargs):
        _ignore_locals_ = True
        self, *args = args
        if self.instance is not None:
            args = [self.instance] + args
        with print_traceback():
            return self.func(*args, **kwargs)
