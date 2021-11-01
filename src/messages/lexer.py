import sys
from typing import Optional, TextIO
from antlr4 import InputStream
from src.messages.message_lexer import message_lexer

class Lexer(message_lexer):
    def __init__(self, key: str, inp: InputStream, output: TextIO = sys.stdout):
        super().__init__(inp, output)
        self._recent: Optional[str] = None
        self._text = ""
        self.message_key = key

    def append_text(self, text: Optional[str] = None):
        """ Append a character to the token's text.

        :param text: If not None, appends this to the text.
            Otherwise, grabs the most recently lexed character from the input.
        """

        if text is None:
            text = self._input.strdata[self._input.index - 1]
        else:
            self._recent = text

        self._text += text
