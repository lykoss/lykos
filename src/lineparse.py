from argparse import ArgumentParser, Namespace
from typing import Optional, Sequence, List, Tuple, IO, NoReturn

class LineParseError(Exception):
    def __init__(self, code=0, message=None):
        self.code = code
        self.message = message

# ArgumentParser that doesn't print to stdout/stderr and doesn't call sys.exit()
# The class using this is responsible for implementing its own help methods
class LineParser(ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["add_help"] = False
        self.allow_intermixed = kwargs.get("allow_intermixed", True)
        super().__init__(*args, **kwargs)

    def print_help(self, file: Optional[IO[str]] = None) -> None:
        pass

    def print_usage(self, file: Optional[IO[str]] = None) -> None:
        pass

    def _print_message(self, message: str, file: Optional[IO[str]] = None) -> None:
        pass

    def exit(self, status: int = 0, message: Optional[str] = None) -> NoReturn:
        raise LineParseError(status, message)

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
        args, argv = parse(args, namespace)
        if argv:
            self.error("unrecognized arguments: {}".format(" ".join(argv)))

        return args
