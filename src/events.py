# event system
from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Callable, Optional, Any
from src.debug import handle_error

__all__ = ["find_listener", "event_listener", "Event", "EventListener"]
EVENT_CALLBACKS: dict[str, list[EventListener]] = defaultdict(list)

class EventListener:
    def __init__(self, callback: Callable, *, listener_id: Optional[str] = None, priority: float = 5):
        if listener_id is not None:
            self._id = listener_id
        elif callback.__module__ is not None:
            self._id = callback.__module__ + "." + callback.__qualname__
        else:
            self._id = callback.__qualname__
        self.callback = callback
        self.priority = priority

    def install(self, event: str):
        if self in EVENT_CALLBACKS[event]:
            raise ValueError("Callback with id {} already registered for the {} event".format(self.id, event))
        EVENT_CALLBACKS[event].append(self)

    def remove(self, event: str):
        if self in EVENT_CALLBACKS[event]:
            EVENT_CALLBACKS[event].remove(self)

    def __eq__(self, other):
        if not isinstance(other, EventListener):
            return NotImplemented
        return self.id == other.id

    def __hash__(self):
        return hash(self._id)

    def __call__(self, *args, **kwargs):
        self.callback(*args, **kwargs)

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        raise ValueError("Cannot modify id attribute")

def find_listener(event: str, listener_id: str) -> EventListener:
    for evt in EVENT_CALLBACKS[event]:
        if evt.id == listener_id:
            return evt
    raise Exception("Could not find listener with id {0}".format(listener_id))

class event_listener:
    def __init__(self, event, priority=5, listener_id=None):
        self.event = event
        self.priority = priority
        self.func: Optional[Callable] = None
        self.listener_id = listener_id
        self.listener: Optional[EventListener] = None

    def __call__(self, *args, **kwargs):
        if self.func is None:
            func = args[0]
            if isinstance(func, event_listener):
                func = func.func
            if self.listener_id is None:
                self.listener_id = func.__qualname__
                # always prefix with module for disambiguation if possible
                if func.__module__ is not None:
                    self.listener_id = func.__module__ + "." + self.listener_id
            self.func = handle_error(func)
            self.listener = EventListener(self.func, priority=self.priority, listener_id=self.listener_id)
            self.listener.install(self.event)
            self.__doc__ = self.func.__doc__
            return self
        else:
            return self.func(*args, **kwargs)

    def remove(self):
        self.listener.remove(self.event)

class Event:
    def __init__(self, _name: str, _data: dict[str, Any], **kwargs):
        self.stop_processing = False
        self.prevent_default = False
        self.name = _name
        self.data = _data
        self.params = SimpleNamespace(**kwargs)

    def dispatch(self, *args, **kwargs):
        self.stop_processing = False
        self.prevent_default = False
        listeners = list(EVENT_CALLBACKS[self.name])
        listeners.sort(key=lambda x: x.priority)
        for listener in listeners:
            listener(self, *args, **kwargs)
            if self.stop_processing:
                break

        return not self.prevent_default
