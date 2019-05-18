from antlr4 import InputStream, CommonTokenStream, ParseTreeWalker
from src.messages import message_formatter
from src.messages.message_lexer import message_lexer
from src.messages.message_parser import message_parser
from src.messages.listener import Listener

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
        input_stream = InputStream(self.value)
        lexer = message_lexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = message_parser(token_stream)
        tree = parser.main()
        listener = Listener(message_formatter, args, kwargs)
        walker = ParseTreeWalker()
        walker.walk(listener, tree)
        return listener.value()
