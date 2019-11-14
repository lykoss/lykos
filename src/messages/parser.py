import sys
from typing import TextIO
from antlr4 import TokenStream
from src.messages.message_parser import message_parser

class Parser(message_parser):
    def __init__(self, key: str, inp: TokenStream, output: TextIO = sys.stdout):
        super().__init__(inp, output)
        self.message_key = key
