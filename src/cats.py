from src import events

ROLE_CATS = frozenset({"Wolf", "Wolfchat", "Wolfteam", "Killer", "Village", "Neutral", "Win Stealer", "Hidden", "Safe", "Cursed", "Innocent", "Team Switcher"})
ROLE_ORDER = ["Wolf", "Wolfchat", "Wolfteam", "Village", "Hidden", "Neutral", "Win Stealer"]

FROZEN = False

ROLES = {}

def get(cat):
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    if cat == "*":
        return AllRoles
    if cat not in ROLE_CATS:
        raise ValueError("{0!r} is not a valid role category".format(cat))
    return globals()[cat.replace(" ", "_")]

def register(role, *cats):
    if FROZEN:
        raise RuntimeError("Fatal: May not register a role once role categories have been frozen")
    if role in ROLES:
        raise RuntimeError("Fatal: May not register a role more than once")
    ROLES[role] = frozenset(cats)
    for cat in cats:
        if cat not in ROLE_CATS:
            raise ValueError("{0!r} is not a valid role category".format(cat))
        globals()[cat.replace(" ", "_")]._roles.add(role)
        AllRoles._roles.add(role)

def freeze(evt):
    global FROZEN
    for cat in ROLE_CATS:
        cls = globals()[cat.replace(" ", "_")]
        cls._roles = frozenset(cls._roles)
    AllRoles._roles = frozenset(AllRoles._roles)
    FROZEN = True
    events.remove_listener("init", freeze, 10)

events.add_listener("init", freeze, 10)

def check_magic(func):
    def chk(self, other):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        if not isinstance(other, Category):
            return NotImplemented
        return func(self, other)
    return chk

class Category:
    """Base class for role categories."""

    def __init__(self, name):
        self.name = name
        self._roles = set()

    def __iter__(self):
        if FROZEN:
            yield from self._roles
        raise RuntimeError("Fatal: Role categories are not ready")

    @property
    def roles(self):
        return self._roles

    @check_magic
    def __eq__(self, other):
        return self._roles == other._roles

    def __hash__(self):
        try:
            return hash(self._roles)
        except TypeError: # still a regular set; not yet frozen
            raise RuntimeError("Fatal: Role categories are not ready")

    def __repr__(self):
        return "Role category: {0}".format(self.name)

    @check_magic
    def __add__(self, other):
        name = "{0} + {1}".format(self.name, other.name)
        cls = __class__(name)
        cls._roles.update(self)
        cls._roles.update(other)
        cls._roles = frozenset(cls._roles)
        return cls

    __radd__ = __add__

    @check_magic
    def __sub__(self, other):
        name = "{0} - {1}".format(self.name, other.name)
        cls = __class__(name)
        cls._roles.update(self)
        cls._roles.difference_update(other)
        cls._roles = frozenset(cls._roles)
        return cls

    @check_magic
    def __and__(self, other):
        name = "{0} & {1}".format(self.name, other.name)
        cls = __class__(name)
        cls._roles.update(self)
        cls._roles.intersection_update(other)
        cls._roles = frozenset(cls._roles)
        return cls

    __rand__ = __and__

    @check_magic
    def __xor__(self, other):
        name = "{0} ^ {1}".format(self.name, other.name)
        cls = __class__(name)
        cls._roles.update(self)
        cls._roles.symmetric_difference_update(other)

    __rxor__ = __xor__

AllRoles = Category("*")
for cat in ROLE_CATS:
    globals()[cat] = Category(cat)

del check_magic, cat

# vim: set sw=4 expandtab:
