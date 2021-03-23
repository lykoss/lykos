# event system
from collections import defaultdict
from types import SimpleNamespace
from typing import Callable, Optional
EVENT_CALLBACKS = defaultdict(list)

__all__ = ["find_listener", "Event", "EventListener"]

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

class Event:
    def __init__(self, _name, _data, **kwargs):
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
