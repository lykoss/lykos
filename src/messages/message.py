import random
from antlr4 import InputStream, CommonTokenStream, ParseTreeWalker
from antlr4.error.ErrorListener import ErrorListener

from src import config
from src.messages import message_formatter
from src.messages.lexer import Lexer
from src.messages.parser import Parser
from src.messages.listener import Listener

__all__ = ["Message"]


class Message:
    def __init__(self, key, value, index=None):
        """Construct a new message.

        :param key: Message key, must exist in message json file
        :param value: Message value, str and list supported
        :param index: If value is a list, determines which list index to retrieve.
            If None, retrieves a random list index (default None)
        """
        self.key = key
        if isinstance(value, list):
            if index is None:
                self.value = random.choice(value)
            else:
                self.value = value[index]
        else:
            self.value = value
        self.formatter = message_formatter

    def __str__(self):
        return self.format()

    def __add__(self, other):
        return self.format() + other

    def __radd__(self, other):
        return other + self.format()

    def format(self, *args, **kwargs) -> str:
        try:
            error_listener = MessageErrorListener()
            input_stream = InputStream(self.value)
            lexer = Lexer(self.key, input_stream)
            lexer.addErrorListener(error_listener)
            token_stream = CommonTokenStream(lexer)
            parser = Parser(self.key, token_stream)
            parser.addErrorListener(error_listener)
            tree = parser.main()
            listener = Listener(self, args, kwargs)
            walker = ParseTreeWalker()
            walker.walk(listener, tree)
            return listener.value()
        except Exception as e:
            if not config.Main.get("debug.enabled") or not config.Main.get("debug.messages.nothrow"):
                raise

            return "ERROR: {0!s} ({1}: {2!r}, {3!r})".format(e, self.key, args, kwargs)


class MessageErrorListener(ErrorListener):
    """Raise exceptions whenever a lexer or parser error occurs.

    By default, errors are printed to stderr (kinda useless), and parsing continues as if nothing happened.
    Then it tries to call our tree listener with bad parse state, which causes things to blow up down the line.
    The exception messages from that are less-than intuitive, when we really just want to know the message itself
    is bad."""
    def syntaxError(self, recognizer, offending_symbol, line, column, msg, e):
        raise RuntimeError("Ill-formed message \"{0}\" (offset {1}): {2}".format(recognizer.message_key, column, msg))
