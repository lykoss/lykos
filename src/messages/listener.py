from src.messages.message_parserListener import message_parserListener


class Listener(message_parserListener):
    def __init__(self, formatter, args, kwargs):
        super().__init__()
        self.value = None
        self.formatter = formatter
        self.args = args
        self.kwargs = kwargs

    def value(self):
        assert self.value is not None
        pass
