import fnmatch
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
    - The syntax {=literal:spec} can be used to apply a format spec to a literal string.
      as opposed to passing the string in as an argument. If the literal contains commas, it will
      be treated as a list.
    - The syntax {=literal!convert} can be used to apply a conversion to a literal string
      as opposed to passing the string in as an argument. If the literal contains commas, it will
      be treated as a list.
    - New spec ":plural:N" for use on list values: Returns the first argument (singular) if N=1,
      and the second argument (plural) otherwise.
    - New spec ":random" for use on list values: Returns an element in the list chosen at random.
    - New spec ":join" to join a list of values. The "list" key at the top level of the json will be used to
      join elements together. The value should be a list with three items: the regular separator, the final
      separator in the event the list contains exactly two elements, and the final separator if the list contains
      3 or more elements. The ":join" spec takes optional arguments to override these default separators, in the
      form ":join:sep:2sep:3sep" -- for example ":join:, : and :, and " would reflect the default value for en.
      If specifying arguments, all 3 must be specified. Otherwise, all 3 must be omitted.
    - New spec ":article" to give the indefinite article for the given value. The "articles" key at the top
      level of the json will be used to retrieve this article. It is processed from top to bottom using pattern
      matching (globs, so * is wildcard), stopping at the first match and using that article. If nothing matches,
      an error is raised.
    - New convert type "!role" to indicate the value is a role name (and will be translated appropriately).
      The "roles" key at the top level of the json will be used to resolve role names. It should be a dict of
      role names to a list of ["singular role", "plural role"].
    - New convert type "!cmd" to indicate the value is a command name (and will be translated appropriately).
      The "commands" key at the top level of the json will be used to resolve command names. It should be a dict
      of command names to a list containing that command name and all aliases. Even if there are no aliases, it
      must be a list.
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
        args = format_spec.split(":")
        key = args.pop(0)
        if key == "plural":
            return self._plural(value, args)
        if key == "random":
            return self._random(value, args)
        if key == "join":
            return self._join(value, args)
        if key == "article":
            return self._article(value, args)

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


_fmt = _Formatter()
