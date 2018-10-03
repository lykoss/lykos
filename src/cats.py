from collections import defaultdict
import itertools

from src import events

__all__ = ["get", "role_order"]

_dict_keys = type(dict().keys())

# role categories; roles return a subset of these categories when fetching their metadata
# Wolf: Defines the role as a true wolf role (usually can kill, usually dies when shot, usually kills visiting harlots, etc.)
#    The village needs to kill every true wolf role to win
# Wolfchat: Defines the role as having access to wolfchat (depending on var.RESTRICT_WOLFCHAT settings)
#    The wolfteam wins if the number of wolfchat roles is greater than or equal to the number of other roles alive
# Wolfteam: Defines the role as wolfteam for determining winners
# Killer: Roles which can kill other roles during the game. Roles which kill upon or after death (ms, vg) don't belong in here
# Village: Defines the role as village for determining winners
# Neutral: Defines the role as neutral (seen as grey by augur, not members of any particular team) and also for determining winner
# Win Stealer: Defines the role as a win stealer (do not win with a built-in team, vigilante can kill them without issue, etc.).
#    Also seen as grey by augur and win as a separate team if not in neutral (e.g. all monsters win together, whereas fools win individually)
# Hidden: Players with hidden roles do not know that they have that role (told they are default role instead, and win with that team)
# Safe: Seer sees these roles as they are, instead of as the default role; usually reserved for village-side special roles
# Spy: Actively gets information about other players or teams
# Intuitive: Passively gets information about other players or teams
# Cursed: Seer sees these roles as wolf
# Innocent: Seer sees these roles as the default role even if they would otherwise be seen as wolf
# Team Switcher: Roles which may change teams during gameplay
ROLE_CATS = frozenset({"Wolf", "Wolfchat", "Wolfteam", "Killer", "Village", "Nocturnal", "Neutral", "Win Stealer", "Hidden", "Safe", "Spy", "Intuitive", "Cursed", "Innocent", "Team Switcher"})
# the ordering in which we list roles (values should be categories, and roles are ordered within the categories in alphabetical order,
# with exception that wolf is first in the wolf category and villager is last in the village category)
# Roles which are always secondary roles in a particular game mode are always listed last (after everything else is done)
ROLE_ORDER = ["Wolf", "Wolfchat", "Wolfteam", "Village", "Hidden", "Win Stealer", "Neutral"]

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
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    buckets = defaultdict(list)
    for role, tags in ROLES.items():
        for tag in ROLE_ORDER:
            if tag in tags:
                buckets[tag].append(role)
                break
    # handle fixed ordering for wolf and villager
    buckets["Wolf"].remove("wolf")
    buckets["Village"].remove("villager")
    for tags in buckets.values():
        tags.sort()
    buckets["Wolf"].insert(0, "wolf")
    buckets["Village"].append("villager")
    return itertools.chain.from_iterable([buckets[tag] for tag in ROLE_ORDER])

def register_roles(evt):
    global FROZEN
    mevt = events.Event("get_role_metadata", {})
    mevt.dispatch(None, "role_categories")
    for role, cats in mevt.data.items():
        if len(cats & {"Wolfteam", "Village", "Neutral", "Hidden"}) != 1:
            raise RuntimeError("Invalid categories for {0}: Must have exactly one of {{Wolfteam, Village, Neutral, Hidden}}, got {1}".format(role, cats))
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

events.add_listener("init", register_roles, 1)

class Category:
    """Base class for role categories."""

    def __init__(self, name):
        self.name = name
        self._roles = set()

    def __len__(self):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        return len(self._roles)

    def __iter__(self):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        yield from self._roles

    def __contains__(self, item):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        return item in self._roles

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

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Role category: {0}".format(self.name)

    def __invert__(self):
        new = self.from_combination(All, self, "", set.difference_update)
        if self.name in ROLE_CATS:
            name = "~{0}".format(self.name)
        else:
            name = "~({0})".format(self.name)
        new.name = name
        return new

    @classmethod
    def from_combination(cls, first, second, op, func):
        if not FROZEN:
            raise RuntimeError("Fatal: Role categories are not ready")
        if isinstance(second, (Category, set, frozenset, _dict_keys)):
            for cont in (first, second):
                for role in cont:
                    if role not in ROLES:
                        raise ValueError("{0!r} is not a role".format(role))
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
    __rsub__            = lambda self, other: self.from_combination(other, self, "-", set.difference_update)

All = Category("*")
for cat in ROLE_CATS:
    name = cat.replace(" ", "_")
    globals()[name] = Category(cat)
    __all__.append(name)

del cat, name, register_roles

# vim: set sw=4 expandtab:
