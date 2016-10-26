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
    def __init__(*args, **kwargs):
        # We do this so that e.g. 'data' can be given as a param
        self, name, data = args # If this raises, there are too few/many args

        self.stop_processing = False
        self.prevent_default = False
        self.name = name
        self.data = data
        self.params = SimpleNamespace(**kwargs)

    def dispatch(*args, **kwargs):
        self = args[0] # If this fails, you forgot to do Event(stuff) first
        self.stop_processing = False
        self.prevent_default = False
        for item in list(EVENT_CALLBACKS[self.name]):
            item[1](*args, **kwargs)
            if self.stop_processing:
                break

        return not self.prevent_default

# vim: set sw=4 expandtab:
