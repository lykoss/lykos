from __future__ import annotations

import collections.abc
import time
import json
import logging
import logging.handlers
import string
import sys
import importlib
from typing import Callable, Sequence, Any, Mapping
from pathlib import Path

from src import config

__all__ = ["UnionFilterMixin", "StreamHandler", "FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler",
           "IRCTransportHandler", "StringFormatter", "StructuredFormatter", "LogRecord", "init"]

class UnionFilterMixin(logging.Filterer):
    # Change filter logic so that we log as long as one of the provided filters succeeds.
    # Default is to require all attached filters to succeed in order to log.
    def filter(self, record: logging.LogRecord) -> bool:
        for f in self.filters: # type: logging.Filter | Callable
            if hasattr(f, "filter"):
                val = f.filter(record)
            else:
                val = f(record)
            if val:
                return True
        return False

class StreamHandler(UnionFilterMixin, logging.StreamHandler):
    pass

class FileHandler(UnionFilterMixin, logging.FileHandler):
    pass

class RotatingFileHandler(UnionFilterMixin, logging.handlers.RotatingFileHandler):
    pass

class TimedRotatingFileHandler(UnionFilterMixin, logging.handlers.TimedRotatingFileHandler):
    pass

class IRCTransportHandler(UnionFilterMixin, logging.Handler):
    def __init__(self, transport: str, destination: str):
        """
        Create a new handler which logs to IRC.

        :param transport: Transport name to log to, defined in botconfig.yml
        :param destination: Channel to log to, optionally with a prefix in front
            if STATUSMSG is supported by the irc server. The bot must have been
            configured to join this channel in the transport definition.
        """
        super().__init__()
        # TODO: make use of transport; right now we only support a single transport
        self.transport = transport
        self.destination = destination

    def emit(self, record: logging.LogRecord) -> None:
        from src import channels
        from src.context import Features
        line = self.format(record)
        prefix = None
        channel = self.destination
        if Features.STATUSMSG and self.destination[0] in Features.PREFIX:
            prefix = self.destination[0]
            channel = self.destination[1:]
        channels.get(channel).send(line, prefix=prefix)

    def format(self, record: logging.LogRecord) -> str:
        # When sending to IRC, only send the first line
        line = super().format(record)
        return line.rsplit("\r?\n")[0]

class StringFormatter(logging.Formatter):
    def __init__(self, tsconfig: dict):
        if tsconfig["enabled"]:
            fmt = "[{asctime}] {message}"
        else:
            fmt = "{message}"
        super().__init__(fmt, datefmt=tsconfig["format"], style="{")
        if tsconfig["utc"]:
            self.converter = time.gmtime

class StructuredFormatter(StringFormatter):
    def format(self, record: logging.LogRecord) -> str:
        # need to call parent format() to populate various fields on record
        _ = StringFormatter.format(self, record)
        obj = {
            "version": 2,
            "message": record.message,
            "template": record.msg,
            "args": record.args,
            "created": record.created,
            "level": record.levelname,
            "channel": record.name
        }

        if hasattr(record, "data"):
            obj["data"] = record.data

        if record.exc_text:
            obj["exception"] = record.exc_text

        if record.stack_info:
            obj["stack"] = self.formatStack(record.stack_info)

        return json.dumps(obj)

class LogRecord(logging.LogRecord):
    def getMessage(self) -> str:
        msg = str(self.msg)
        # Internal packages (urllib3, other dependencies we may pull in) still use %-style formatting
        # So try {-style first and fall back to %-style if that fails. In both cases we assume that
        # all arguments being passed in are consumed in the format string.

        # self.args might be a mapping instead of a sequence, which makes vformat unhappy.
        if isinstance(self.args, collections.abc.Mapping):
            arg_list = []
            arg_dict = self.args
        else:
            arg_list = self.args
            arg_dict = {}

        if self.args:
            brace_formatter = _ThrowingFormatter()
            try:
                msg = brace_formatter.vformat(msg, arg_list, arg_dict)
            except TypeError:
                msg = msg % self.args

        return msg

class _ThrowingFormatter(string.Formatter):
    def check_unused_args(self,
                          used_args: Sequence[int | str],
                          args: Sequence[Any],
                          kwargs: Mapping[str, Any]) -> None:
        expected_args = set(range(len(args)))
        found_args = {a for a in used_args if isinstance(a, int)}
        expected_kwargs = set(kwargs.keys())
        found_kwargs = {a for a in used_args if isinstance(a, str)}
        if expected_args - found_args or expected_kwargs - found_kwargs:
            raise TypeError("not all arguments converted during string formatting")

def init():
    gl = config.Main.get("logging.groups")
    groups = {}
    for g in gl:
        groups[g["name"]] = g["filters"]

    logs = config.Main.get("logging.logs")
    root_logger = logging.getLogger()
    for log in logs:
        # construct our Handler instance
        if log["handler"]["type"] == "file":
            bot_root = Path(__file__).parent.parent
            file = bot_root / Path(log["handler"]["file"])
            if not log["handler"]["rotate"]:
                cls = FileHandler
                kwargs = {}
            elif log["handler"]["rotate"]["type"] == "bytes":
                cls = RotatingFileHandler
                kwargs = {
                    "maxBytes": log["handler"]["rotate"]["max_bytes"],
                    "backupCount": log["handler"]["rotate"]["backup_count"]
                }
            elif log["handler"]["rotate"]["type"] == "timed":
                cls = TimedRotatingFileHandler
                kwargs = {
                    "when": log["handler"]["rotate"]["when"],
                    "interval": log["handler"]["rotate"]["interval"],
                    "atTime": log["handler"]["rotate"]["at_time"],
                    "utc": log["handler"]["rotate"]["utc"],
                    "backupCount": log["handler"]["rotate"]["backup_count"]
                }
            else:
                raise NotImplementedError("Unknown rotation in logging.logs[].handler<file>.rotate")
            handler = cls(file, encoding="utf-8", delay=False, **kwargs)
        elif log["handler"]["type"] == "stream":
            if log["handler"]["stream"] == "stdout":
                stream = sys.stdout
            elif log["handler"]["stream"] == "stderr":
                stream = sys.stderr
            else:
                raise NotImplementedError("Unknown stream in logging.logs[].handler<stream>.stream")
            handler = StreamHandler(stream)
        elif log["handler"]["type"] == "transport":
            # TODO: only IRC is supported right now
            name = log["handler"]["transport"]
            destination = log["handler"]["destination"]
            handler = IRCTransportHandler(name, destination)
        elif log["handler"]["type"] == "custom":
            module = importlib.import_module(log["handler"]["module"])
            cls = getattr(module, log["handler"]["class"])
            kwargs = log["handler"]["args"]
            handler = cls(**kwargs)
        else:
            raise NotImplementedError("Unknown type {} in logging.logs[].handler".format(log["handler"]["type"]))

        # Add relevant filters onto the Handler
        for f in groups[log["group"]]:
            handler.addFilter(logging.Filter(f))

        # Configure the Handler's level
        handler.setLevel(log["level"].upper())

        # Configure the Handler's formatter
        if log["format"] == "string":
            formatter = StringFormatter
        elif log["format"] == "structured":
            formatter = StructuredFormatter
        else:
            raise NotImplementedError("Unknown format {} in logging.logs[].format".format(log["format"]))
        handler.setFormatter(formatter(log["timestamp"]))

        # Register the handler
        root_logger.addHandler(handler)

        # Ensure that the root logger handles every message;
        # our handlers will filter appropriately based on level
        root_logger.setLevel(logging.NOTSET)

        # Configure the record factory so that we support str.format formatting of log messages
        logging.setLogRecordFactory(LogRecord)
