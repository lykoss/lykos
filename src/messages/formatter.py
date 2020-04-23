import string
import random
import re
import fnmatch

class Formatter(string.Formatter):
    """ Custom formatter for message strings.

    This inherits all features of base str.format() with the following additions:
    - Prefixing a value with = will treat it as a literal. It will be a list if the value contains commas,
      and a string otherwise. Example: {=some literal string} or {=some,literal,list}. You can use any valid
      conversions or format specs on these literals.
    - New spec ":plural(N)" for use on list values. Returns the singular or plural version given the value of N.
      N can be either numeric or a list (in which case the length of the list is used).
    - New spec ":random" for use on list values: Returns an element in the list chosen at random.
    - New spec ":join" to join a list of values. Can be called in four ways:
      :join to join with default settings
      :join(spec) to apply spec to all list elements and then join with default settings
    - The ":join_space" and ":join_simple" specs work like ":join", but join with only spaces or only commas
      rather than regular join which adds an "and" and avoids commas when there are only two list elements.
    - New spec ":bold" to bold the value. This can be combined with other format specifiers.
    - New spec ":article to give the indefinite article for the given value.
    - New spec ":!" prefixes the value with the bot's command character.
    - New convert type "!role" to indicate the value is a role name (and will be translated appropriately).
    - New convert type "!mode" to indicate the value is a gamemode name (and will be translated appropriately).
    - New convert type "!command" to indicate the value is a command name (and will be translated appropriately).
    - New convert type "!totem" to indicate the value is a totem name (and will be translated appropriately).
    - New convert type "!cat" to indicate the value is a role category name (and will be translated appropriately).
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

    def format_field(self, value, format_spec, *, flatten_lists=True):
        if not format_spec:
            specs = {}
        elif not isinstance(format_spec, dict):
            specs = {format_spec: None}
        else:
            specs = format_spec.copy()

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
        if "join_space" in specs:
            value = self._join_space(value, specs["join_space"])
            del specs["join_space"]
        if "join_simple" in specs:
            value = self._join_simple(value, specs["join_simple"])
            del specs["join_simple"]

        if isinstance(value, dict) or isinstance(value, set):
            # we were passed a set/dict, but we only support passing lists up. Convert it.
            value = list(value)

        if isinstance(value, list):
            if flatten_lists:
                # if value is a list by this point, retrieve the first element
                # this happens when using !role but expecting just the singular value
                # The list may be empty as well, in which case it flattens to an empty string
                if value:
                    value = value[0]
                else:
                    value = ""
            else:
                # if we aren't supposed to be flattening lists, ensure we don't have any specs remaining
                # which operate on strings. If we do, that's an error.
                # We can't call super() here because that will coerce value into a string.
                if specs:
                    raise ValueError("Invalid format specifier for list context")
                return value

        # handle specs that work on strings. Combining multiple of these isn't supported
        if "article" in specs:
            value = self._article(value, specs["article"])
            del specs["article"]
        if "!" in specs:
            from botconfig import CMD_CHAR
            value = CMD_CHAR + value
            del specs["!"]

        # Combining these is supported, and these specs work on strings
        if "bold" in specs:
            value = self._bold(value, specs["bold"])
            del specs["bold"]
        if "capitalize" in specs:
            value = self._capitalize(value, specs["capitalize"])
            del specs["capitalize"]

        # let __format__ and default specs handle anything that's left. This means we need to recombine
        # anything that we didn't handle back into a single spec string, reintroducing : where necessary
        remain = []
        for spec, arg in specs.items():
            if arg is not None:
                remain.append("{0}({1})".format(spec, arg))
            else:
                remain.append(spec)

        format_spec = ":".join(remain)
        return super().format_field(value, format_spec)

    def convert_field(self, value, conversion):
        from src.messages import messages

        if conversion == "role":
            return messages.raw("_roles", value)
        if conversion == "mode":
            return messages.raw("_gamemodes", value)
        if conversion == "command":
            return messages.raw("_commands", value)[0]
        if conversion == "totem":
            return messages.raw("_totems", value)
        if conversion == "cat":
            return messages.raw("_role_categories", value)
        if conversion == "phase":
            return messages.raw("_phases", value)

        # not one of our custom things
        return super().convert_field(value, conversion)

    def _plural(self, value, arg):
        from src.messages import messages

        if not arg:
            num = None
        else:
            try:
                num = int(arg)
            except TypeError:
                num = len(arg)
        for rule in messages.raw("_metadata", "plural"):
            if rule["number"] is None or rule["number"] == num:
                return value[rule["index"]]

        raise ValueError("No plural rules matched the number {0!r} in language metadata!".format(num))

    def _random(self, value, arg):
        return random.choice(value)

    def _join_space(self, value, arg):
        return self._join(value, arg, join_chars=[" ", " ", " "])

    def _join_simple(self, value, arg):
        from src.messages import messages
        # join using only a comma (in English), regardless of the number of list items
        normal_chars = messages.raw("_metadata", "list")
        simple = normal_chars[1]
        return self._join(value, arg, join_chars=[simple, simple, simple])

    def _join(self, value, arg, join_chars=None):
        from src.messages import messages

        spec = None
        if arg:
            spec = arg

        if not join_chars:
            join_chars = messages.raw("_metadata", "list")

        value = list(value) # make sure we can index it

        if not value:
            return ""
        elif len(value) == 1:
            return self.format_field(value[0], spec)
        elif len(value) == 2:
            return join_chars[0].join(self.format_field(v, spec) for v in value)
        else:
            return (join_chars[1].join(self.format_field(v, spec) for v in value[:-1])
                    + join_chars[2]
                    + self.format_field(value[-1], spec))

    def _article(self, value, arg):
        from src.messages import messages

        for rule in messages.raw("_metadata", "articles"):
            if rule["pattern"] is None or fnmatch.fnmatch(value, rule["pattern"]):
                return rule["article"]

        raise ValueError("No article rules matched the value {0!r} in language metadata!".format(value))

    def _bold(self, value, arg):
        # FIXME make this transport-agnostic
        return "\u0002{0}\u0002".format(value)

    def _capitalize(self, value, arg):
        return value.capitalize()

    def tag_b(self, content, param):
        return self._bold(content, param)

    def _truthy(self, value):
        # when evaluating if/nif the value is usually already coerced to string,
        # so we can't rely on python's if/if not to correctly evaluate things.
        falsy = {"False", "None", "0", "0.0", "[]", "{}", "()", "set()"}
        return value and value not in falsy

    def tag_if(self, content, param):
        return content if self._truthy(param) else ""

    def tag_nif(self, content, param):
        return content if not self._truthy(param) else ""
