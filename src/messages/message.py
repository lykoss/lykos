from antlr4 import InputStream, CommonTokenStream, ParseTreeWalker
from antlr4.error.ErrorListener import ErrorListener
from src.messages import message_formatter
from src.messages.message_lexer import message_lexer
from src.messages.message_parser import message_parser
from src.messages.listener import Listener

__all__ = ["Message"]


class Message:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.formatter = message_formatter

    def __str__(self):
        return str(self.value)

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)

    def format(self, *args, **kwargs):
        error_listener = MessageErrorListener()
        input_stream = InputStream(self.value)
        lexer = message_lexer(input_stream)
        lexer.message_key = self.key
        lexer.addErrorListener(error_listener)
        token_stream = CommonTokenStream(lexer)
        parser = message_parser(token_stream)
        parser.message_key = self.key
        parser.addErrorListener(error_listener)
        tree = parser.main()
        listener = Listener(self, args, kwargs)
        walker = ParseTreeWalker()
        walker.walk(listener, tree)
        return listener.value()


class MessageErrorListener(ErrorListener):
    """Raise exceptions whenever a lexer or parser error occurs.

    By default, errors are printed to stderr (kinda useless), and parsing continues as if nothing happened.
    Then it tries to call our tree listener with bad parse state, which causes things to blow up down the line.
    The exception messages from that are less-than intuitive, when we really just want to know the message itself
    is bad."""
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise RuntimeError("Ill-formed message key \"{0}\" (offset {1}): {2}", recognizer.message_key, column, msg)
