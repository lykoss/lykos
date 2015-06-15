# event system

EVENT_CALLBACKS = {}

def add_listener(event, callback, priority = 5):
    if event not in EVENT_CALLBACKS:
        EVENT_CALLBACKS[event] = []

    if (priority, callback) not in EVENT_CALLBACKS[event]:
        EVENT_CALLBACKS[event].append((priority, callback))
        EVENT_CALLBACKS[event].sort(key = lambda x: x[0])

def remove_listener(event, callback, priority = 5):
    if event in EVENT_CALLBACKS and (priority, callback) in EVENT_CALLBACKS[event]:
        EVENT_CALLBACKS[event].remove((priority, callback))

    if event in EVENT_CALLBACKS and not EVENT_CALLBACKS[event]:
        del EVENT_CALLBACKS[event]

class Event:
    def __init__(self, name, data):
        self.stop_processing = False
        self.prevent_default = False
        self.name = name
        self.data = data

    def dispatch(self, *args):
        if self.name not in EVENT_CALLBACKS:
            return True

        for item in list(EVENT_CALLBACKS[self.name]):
            item[1](self, *args)
            if self.stop_processing:
                break

        return not self.prevent_default

# vim: set expandtab:sw=4:ts=4:
