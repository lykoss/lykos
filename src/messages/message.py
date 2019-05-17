from src.messages import message_formatter

class Message:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)

    def format(self, *args, **kwargs):
        return message_formatter.vformat(self.value, args, kwargs)
