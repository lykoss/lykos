import fnmatch
import re
import random
import string
from collections import OrderedDict

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
        return _fmt.vformat(self.value, args, kwargs)

class _Formatter(string.Formatter):
    """ Custom formatter for message strings.

    This inherits all features of base str.format() with the following additions:
    - Prefixing a value with = will treat it as a literal. It will be a list if the value contains commas,
      and a string otherwise. Example: {=some literal string} or {=some,literal,list}. You can use any valid
      conversions or format specs on these literals.
    - New spec ":plural(N)" for use on list values. Returns the singular or plural version given the value of N.
    - New spec ":random" for use on list values: Returns an element in the list chosen at random.
    - New spec ":join" to join a list of values. Can be called in four ways:
      :join to join with default settings
      :join(spec) to apply spec to all list elements and then join with default settings
      :join(sep,sep,sep) to use the specified separators instead of default separators
      :join(spec,sep,sep,sep) to apply spec to all list elements and then join with the specified separators
      As a technical restriction, inner specs cannot contain colons
    - New spec ":bold" to bold the value. This can be combined with other format specifiers.
    - New spec ":color(C)" to make the value the color C. ":colour(C)" is accepted as an alias.
      This can be combined with other format specifiers.
    - New spec ":article to give the indefinite article for the given value.
    - New spec ":!" prefixes the value with the bot's command character.
    - New convert type "!role" to indicate the value is a role name (and will be translated appropriately).
    - New convert type "!command" to indicate the value is a command name (and will be translated appropriately).
    """
    def get_value(self, key, args, kwargs):
        try:
            if key[0] == "=":
                value = key[1:]
                if "," in value:
                    return value.split(",")
                return value
        except TypeError:
            pass

        return super().get_value(key, args, kwargs)

    def format_field(self, value, format_spec):
        if not format_spec:
            return super().format_field(value, format_spec)

        specs = OrderedDict()
        for spec in format_spec.split(":"):
            m = re.fullmatch(r"(.*?)\((.*)\)", spec)
            if m:
                key = m.group(1)
                args = m.group(2).split(",")
            else:
                key = spec
                args = None
            # remap aliases for uniqueness
            if key == "colour":
                key = "color"
            specs[key] = args

        # handle specs that operate on lists. Combining multiple of these isn't supported
        if "plural" in specs:
            value = self._plural(value, specs["plural"])
            del specs["plural"]
        if "random" in specs:
            value = self._random(value, specs["random"])
            del specs["random"]
        if "join" in specs:
            value = self._join(value, specs["join"])
            del specs["join"]

        # if value is a list by this point, retrieve the first element
        # this happens when using !role but expecting just the singular value
        if isinstance(value, list):
            value = value[0]

        # handle specs that work on strings. Combining multiple of these isn't supported
        if "article" in specs:
            value = self._article(value, specs["article"])
            del specs["article"]
        if "!" in specs:
            from botconfig import CMD_CHAR
            value = CMD_CHAR + value

        # Combining these is supported, and these specs work on strings
        if "bold" in specs:
            # FIXME make this transport-agnostic
            value = "\u0002" + value + "\u0002"
            del specs["bold"]
        if "color" in specs:
            value = self._color(value, specs["color"])
            del specs["color"]

        # let __format__ and default specs handle anything that's left. This means we need to recombine
        # anything that we didn't handle back into a single spec string, reintroducing : where necessary
        remain = []
        for spec, args in specs.items():
            if args is not None:
                remain.append("{0}({1})".format(spec, ",".join(args)))
            else:
                remain.append(spec)

        format_spec = ":".join(remain)
        return super().format_field(value, format_spec)

    def convert_field(self, value, conversion):
        from src.messages import messages

        if conversion == "role":
            return messages.raw("_roles", value)
        if conversion == "command":
            return messages.raw("_commands", value)

        # not one of our custom things
        return super().convert_field(value, conversion)

    def _plural(self, value, args):
        from src.messages import messages

        num = int(args[0])
        for rule in messages.raw("_metadata", "plural"):
            if rule["number"] is None or rule["number"] == num:
                return value[rule["index"]]

        raise ValueError("No plural rules matched the number {0!r} in language metadata!".format(num))

    def _random(self, value, args):
        return random.choice(value)

    def _join(self, value, args):
        from src.messages import messages

        spec = None
        if len(args) == 1 or len(args) == 4:
            spec = args.pop(0)

        if not args:
            args = messages.raw("_metadata", "list")

        if not value:
            return ""
        elif len(value) == 1:
            return self.format_field(value[0], spec)
        elif len(value) == 2:
            return args[0].join(self.format_field(v, spec) for v in value)
        else:
            return args[1].join(self.format_field(v, spec) for v in value[:-1]) + args[2] + self.format_field(value[-1], spec)

    def _article(self, value, args):
        from src.messages import messages

        for rule in messages.raw("_metadata", "articles"):
            if rule["pattern"] is None or fnmatch.fnmatch(value, rule["pattern"]):
                return rule["article"]

        raise ValueError("No article rules matched the value {0!r} in language metadata!".format(value))

    def _color(self, value, args):
        # FIXME make this transport-agnostic
        cmap = {
            "white": 0,
            "black": 1,
            "blue": 2,
            "green": 3,
            "red": 4,
            "brown": 5,
            "purple": 6,
            "orange": 7,
            "yellow": 8,
            "lightgreen": 9,
            "cyan": 10,
            "lightcyan": 11,
            "lightblue": 12,
            "pink": 13,
            "grey": 14,
            "lightgrey": 15
        }

        return "\u0003{0}{1}\u0003".format(cmap[args[0]], value)

_fmt = _Formatter()
