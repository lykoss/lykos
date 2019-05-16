import fnmatch
import re
import random
import string

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
    - New spec ":join" to join a list of values. The ":join" spec takes optional arguments to override the default
      separators, in the form ":join(sep,sep,sep)". If specifying arguments, all 3 must be specified. Otherwise, all
      3 must be omitted.
    - New spec ":bold" to bold the value. This can be combined with other format specifiers.
    - New spec ":color(C)" to make the value the color C. ":colour(C)" is accepted as an alias.
      This can be combined with other format specifiers.
    - New spec ":article to give the indefinite article for the given value.
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
        specs = set()
        for spec in format_spec.split(":"):
            m = re.fullmatch(r"(.*?)\((.*)\)", spec)
            if m:
                key = m.group(1)
                args = m.group(2).split(",")
            else:
                key = spec
                args = []
            # remap aliases for uniqueness
            if key == "colour":
                key = "color"
            specs.add((key, args))

        # handle main specs
        for key, args in specs:
            if key == "plural":
                value = self._plural(value, args)
                break
            if key == "random":
                value = self._random(value, args)
                break
            if key == "join":
                value = self._join(value, args)
                break
            if key == "article":
                value = self._article(value, args)
                break

        # handle bold/color
        for key, args in specs:
            if key == "bold":
                # FIXME make this transport-agnostic
                value = "\u0002" + value + "\u0002"
            if key == "color" or key == "colour":
                value = self._color(value, args)

        # not one of our custom things
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
            if rule["amount"] is None or rule["amount"] == num:
                return value[rule["index"]]

        raise ValueError("No plural rules matched the number {0!r} in language metadata!".format(num))

    def _random(self, value, args):
        return random.choice(value)

    def _join(self, value, args):
        from src.messages import messages

        if not args:
            args = messages.raw("list")

        if not value:
            return value
        elif len(value) == 1:
            return value[0]
        elif len(value) == 2:
            return args[1].join(value)
        else:
            return args[0].join(value[:-1]) + args[2] + value[-1]

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
