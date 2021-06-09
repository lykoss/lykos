from __future__ import annotations

from argparse import ArgumentParser, Namespace, Action
from typing import Optional, Sequence, IO, NoReturn

__all__ = ["LineParseError", "LineParser", "WantsHelp"]

class LineParseError(Exception):
    def __init__(self, parser, code=0, message=None):
        self.parser = parser
        self.code = code
        self.message = message

class RaiseHelp(Action):
    def __init__(self, option_strings, dest):
        super().__init__(option_strings=option_strings,
                         dest=dest,
                         default=False,
                         required=False,
                         const=True,
                         nargs=0)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, self.const)
        raise WantsHelp(parser, namespace, values, option_string)

class WantsHelp(Exception):
    def __init__(self, parser, namespace, values, option_string):
        self.parser = parser
        self.namespace = namespace
        self.values = values
        self.option_string = option_string

# ArgumentParser that doesn't print to stdout/stderr and doesn't call sys.exit()
# The class using this is responsible for implementing its own help methods
class LineParser(ArgumentParser):
    def __init__(self, *args, allow_intermixed: bool = False, **kwargs):
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self.allow_intermixed = allow_intermixed
        self.register("action", "help", RaiseHelp)

    def print_help(self, file: Optional[IO[str]] = None) -> None:
        pass

    def print_usage(self, file: Optional[IO[str]] = None) -> None:
        pass

    def _print_message(self, message: str, file: Optional[IO[str]] = None) -> None:
        pass

    def exit(self, status: int = 0, message: Optional[str] = None) -> NoReturn:
        raise LineParseError(self, status, message)

    def error(self, message: str) -> NoReturn:
        self.exit(2, message)

    def add_subparsers(self, **kwargs):
        # parse_known_intermixed_args doesn't support subparsers, so switch back to default parsing for
        # this top-level parser
        self.allow_intermixed = False
        return super().add_subparsers(**kwargs)

    def parse_args(self, args: Optional[Sequence[str]] = None, namespace: Optional[Namespace] = None) -> Namespace:
        if args is None:
            # args=None is supported by ArgumentParser to read args from sys.argv but we don't want to do that here
            raise TypeError("LineParser requires an args list to be passed in")

        # shell out to the correct parser
        if self.allow_intermixed:
            parse = self.parse_known_intermixed_args
        else:
            parse = self.parse_known_args
        out_args, argv = parse(args, namespace)
        # allow the help option to work even if all required positionals aren't there
        if argv:
            self.error("unrecognized arguments: {}".format(" ".join(argv)))

        return out_args
