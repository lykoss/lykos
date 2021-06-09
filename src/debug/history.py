from __future__ import annotations

import traceback
from typing import Set, List, Tuple, Dict, Optional
from src import config

__all__ = ["History", "enable_history", "disable_history"]

ENABLED_NAMES = set() # type: Set[str]

def enable_history(name: str) -> None:
    ENABLED_NAMES.add(name)

def disable_history(name: str) -> None:
    ENABLED_NAMES.discard(name)

ENABLED_NAMES.update(config.Main.get("debug.containers.names"))
HISTORY_LIMIT = config.Main.get("debug.containers.limit") # type: int

class History:
    def __init__(self, name: str):
        self.name = name
        self.history = [] # type: List[Tuple[str, List[str], Dict[str,str], traceback.StackSummary]]

    def __str__(self) -> str:
        return self.list(-5)

    def __getitem__(self, item):
        return self.history[item]

    def _format_item(self, item) -> str:
        arglist = list(item[1])
        for k, v in item[2].items():
            arglist.append("{0}={1}".format(k, v))
        return "{0}({1})".format(item[0], ", ".join(arglist))

    def list(self, start: Optional[int] = None, stop: Optional[int] = None) -> str:
        if not self.history:
            return "No history"

        lines = []
        s = slice(start, stop)
        if start is None:
            start_index = 0
        elif start < 0:
            start_index = max(len(self.history) + start, 0)
        else:
            start_index = start

        for i, item in enumerate(self.history[s], start=start_index):
            lines.append("{0}: {1}".format(i, self._format_item(item)))
        return "\n".join(lines)

    def get(self, index: int) -> str:
        # FIXME: make this less verbose so it fits in output better
        item = self.history[index]
        lines = [self._format_item(item)]
        lines.extend(traceback.format_list(item[3]))
        return "\n".join(lines)

    def _enabled(self) -> bool:
        if self.name in ENABLED_NAMES or "*" in ENABLED_NAMES:
            return True

        parts = self.name.split(".")
        parts.pop()
        while parts:
            label = ".".join(parts) + ".*"
            if label in ENABLED_NAMES:
                return True
            parts.pop()

        return False

    def add(self, event: str, *args, **kwargs) -> None:
        if not self._enabled():
            return

        stack = traceback.extract_stack()
        if len(self.history) == HISTORY_LIMIT:
            self.history.pop(0)

        sanitized_args = [repr(x) for x in args]
        sanitized_kwargs = {x: repr(y) for x, y in kwargs.items()}

        self.history.append((event, sanitized_args, sanitized_kwargs, stack))
