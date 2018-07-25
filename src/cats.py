from collections import defaultdict
import itertools

from src import events

ROLE_CATS = frozenset({"Wolf", "Wolfchat", "Wolfteam", "Killer", "Village", "Neutral", "Win Stealer", "Hidden", "Safe", "Cursed", "Innocent", "Team Switcher"})
ROLE_ORDER = ["Wolf", "Wolfchat", "Wolfteam", "Village", "Hidden", "Neutral", "Win Stealer"]

FROZEN = False

ROLES = {}

def get(cat):
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    if cat == "*":
        return All
    if cat not in ROLE_CATS:
        raise ValueError("{0!r} is not a valid role category".format(cat))
    return globals()[cat.replace(" ", "_")]

def role_order():
    buckets = defaultdict(list)
    for role, tags in ROLES.items():
        for tag in ROLE_ORDER:
            if tag in tags:
                buckets[tag].append(role)
                break
    # handle fixed ordering for wolf and villager
    buckets["Wolf"].remove("wolf")
    buckets["Village"].remove("villager")
    for tag in buckets:
        buckets[tag] = sorted(buckets[tag])
    buckets["Wolf"].insert(0, "wolf")
    buckets["Village"].append("villager")
    return itertools.chain.from_iterable([buckets[tag] for tag in ROLE_ORDER])

def register_roles(evt):
    global FROZEN
    mevt = events.Event("get_role_metadata", {})
    mevt.dispatch(None, "role_categories")
    for role, cats in mevt.data.items():
        ROLES[role] = frozenset(cats)
        for cat in cats:
            if cat not in ROLE_CATS:
                raise ValueError("{0!r} is not a valid role category".format(cat))
            globals()[cat.replace(" ", "_")]._roles.add(role)
        All._roles.add(role)

    for cat in ROLE_CATS:
        cls = globals()[cat.replace(" ", "_")]
        cls._roles = frozenset(cls._roles)
    All._roles = frozenset(All._roles)
    FROZEN = True
    events.remove_listener("init", register_roles, 10)

events.add_listener("init", register_roles, 10)

class Category:
    """Base class for role categories."""

    def __init__(self, name):
        self.name = name
        self._roles = set()

    def __iter__(self):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        yield from self._roles

    @property
    def roles(self):
        return self._roles

    def __eq__(self, other):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        if isinstance(other, Category):
            return self._roles == other._roles
        if isinstance(other, (set, frozenset)):
            return self._roles == other
        if isinstance(other, str):
            return self.name == other
        return NotImplemented

    def __hash__(self):
        try:
            return hash(self._roles)
        except TypeError: # still a regular set; not yet frozen
            raise RuntimeError("Fatal: Role categories are not ready")

    def __len__(self):
        return len(self._roles)

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Role category: {0}".format(self.name)

    @classmethod
    def from_combination(cls, first, second, op, func):
        if not isinstance(first, Category):
            raise ValueError("First argument to from_combination must be a Category")
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        if isinstance(second, str):
            if second not in ROLES:
                raise ValueError("{0} is not a role".format(second))
            second = {second}
        if isinstance(second, (Category, set, frozenset)):
            name = "{0} {1} {2}".format(first, op, second)
            self = cls(name)
            self._roles.update(first)
            func(self._roles, second)
            self._roles = frozenset(self._roles)
            return self
        return NotImplemented

    __add__ = __radd__  = lambda self, other: self.from_combination(self, other, "+", set.update)
    __or__  = __ror__   = lambda self, other: self.from_combination(self, other, "|", set.update)
    __and__ = __rand__  = lambda self, other: self.from_combination(self, other, "&", set.intersection_update)
    __xor__ = __rxor__  = lambda self, other: self.from_combination(self, other, "^", set.symmetric_difference_update)
    __sub__             = lambda self, other: self.from_combination(self, other, "-", set.difference_update)

All = Category("*")
for cat in ROLE_CATS:
    globals()[cat] = Category(cat)

del cat

# vim: set sw=4 expandtab:
