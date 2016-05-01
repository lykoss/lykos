# event system
from collections import defaultdict
EVENT_CALLBACKS = defaultdict(list)

def add_listener(event, callback, priority=5):
    if (priority, callback) not in EVENT_CALLBACKS[event]:
        EVENT_CALLBACKS[event].append((priority, callback))
        EVENT_CALLBACKS[event].sort(key = lambda x: x[0])

def remove_listener(event, callback, priority = 5):
    if (priority, callback) in EVENT_CALLBACKS[event]:
        EVENT_CALLBACKS[event].remove((priority, callback))

class Event:
    def __init__(self, name, data):
        self.stop_processing = False
        self.prevent_default = False
        self.name = name
        self.data = data

    def dispatch(self, *args, **kwargs):
        for item in list(EVENT_CALLBACKS[self.name]):
            item[1](self, *args, **kwargs)
            if self.stop_processing:
                break

        return not self.prevent_default

# vim: set expandtab:sw=4:ts=4:
