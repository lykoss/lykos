from argparse import ArgumentParser

class LineParseError(Exception):
    def __init__(self, code=0, message=None):
        self.code = code
        self.message = message

# ArgumentParser that doesn't print to stdout/stderr and doesn't call sys.exit()
# The class using this is responsible for implementing its own help methods
class LineParser(ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)

    def print_help(self, file=None):
        pass

    def print_usage(self, file=None):
        pass

    def _print_message(self, message, file=None):
        pass

    def exit(self, status=0, message=None):
        raise LineParseError(status, message)

    def error(self, message):
        self.exit(2, message)
