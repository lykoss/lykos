# event system
from collections import defaultdict
from types import SimpleNamespace
EVENT_CALLBACKS = defaultdict(list)

__all__ = ["add_listener", "remove_listener", "Event"]

def add_listener(event, callback, priority=5):
    if (priority, callback) not in EVENT_CALLBACKS[event]:
        EVENT_CALLBACKS[event].append((priority, callback))
        EVENT_CALLBACKS[event].sort(key = lambda x: x[0])

def remove_listener(event, callback, priority = 5):
    if (priority, callback) in EVENT_CALLBACKS[event]:
        EVENT_CALLBACKS[event].remove((priority, callback))

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
        for item in list(EVENT_CALLBACKS[self.name]):
            item[1](self, *args, **kwargs)
            if self.stop_processing:
                break

        return not self.prevent_default

# vim: set sw=4 expandtab:
