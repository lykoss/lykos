# role categories; roles return a subset of these categories when fetching their metadata
# Wolf: Defines the role as a true wolf role (usually can kill, dies when shot, kills visiting harlots, etc.)
# Wolfchat: Defines the role as having access to wolfchat (depending on gameplay.wolfchat config settings)
# Wolfteam: Defines the role as wolfteam for determining winners
# Vampire: Defines the role as a true vampire role (usually able to bite, access to vampire chat)
# Vampire Team: Defines the role as vampire team for determining winners
# Killer: Roles which can kill other roles during the game. Roles which kill upon or after death (ms, vg) don't belong in here
# Village: Defines the role as village for determining winners
# Nocturnal: Defines the role as being awake at night (usually due to having commands which work at night)
# Neutral: Defines the role as neutral (seen as grey by augur) and not in village or wolfteam when determining winners
# Win Stealer: Defines the role as a win stealer (do not win with a built-in team, vigilante can kill them without issue, etc.)
# Hidden: Players with hidden roles do not know that they have that role (told they are an eligible instead, and win with that team)
# Hidden Eligible: Roles that the bot can re-map players with hidden roles to. These roles should never have special powers.
# Safe: Seer sees these roles as they are, instead of as the default role; usually reserved for village-side special roles
# Spy: Actively gets information about other players or teams
# Intuitive: Passively gets information about other players or teams
# Cursed: Seer sees these roles as wolf
# Innocent: Seer sees these roles as the default role even if they would otherwise be seen as wolf
# Team Switcher: Roles which may change teams during gameplay
# Wolf Objective: If the number of alive players with this role is greater than or equal to the other players,
#    the wolfteam wins. Only main roles are considered for this. All Vampire Objectives must additionally be dead.
# Vampire Objective: If the number of alive players with this role is greater than or equal to the other players,
#    the vampire team wins. Only main roles are considered for this. All Wolf Objectives must additionally be dead.
# Village Objective: If all of the players with this cat are dead, the village wins.
#    Only main roles are considered for this.
# All: A category containing every role. Useful for checking if a role is loaded.
# Nobody: A category containing no roles. Used to indicate if nobody should win a particular game.

from __future__ import annotations

from collections import defaultdict
import itertools
from typing import Iterable, TYPE_CHECKING, Collection

from src.events import Event, EventListener

if TYPE_CHECKING:
    from src.gamestate import GameState

__all__ = [
    "get", "get_team", "role_order", "all_cats", "all_roles", "all_teams", "Category",
    "Wolf", "Wolfchat", "Wolfteam", "Killer", "Village", "Nocturnal", "Neutral", "Win_Stealer", "Hidden", "Safe",
    "Spy", "Intuitive", "Cursed", "Innocent", "Team_Switcher", "Wolf_Objective", "Village_Objective",
    "Vampire", "Vampire_Team", "Vampire_Objective", "Hidden_Eligible", "All", "Nobody"
]

_dict_keys = type(dict().keys())  # type: ignore

# Mapping of category names to the categories themselves; populated in Category.__init__
ROLE_CATS: dict[str, Category] = {}

# the ordering in which we list roles (values should be categories, and roles are ordered within the categories in alphabetical order,
# with exception that wolf is first in the wolf category and villager is last in the village category)
# Roles which are always secondary roles in a particular game mode are always listed last (after everything else is done)
ROLE_ORDER = ["Wolf", "Wolfchat", "Wolfteam", "Vampire", "Vampire Team", "Village", "Hidden", "Win Stealer", "Neutral"]

FROZEN = False

ROLES: dict[str, Collection[str]] = {}
TEAMS: set[Category] = set()

def get(cat: str) -> Category:
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    if cat not in ROLE_CATS:
        raise ValueError("{0!r} is not a valid role category".format(cat))
    return ROLE_CATS[cat]

def role_order() -> Iterable[str]:
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    buckets = defaultdict(list)
    for role, tags in ROLES.items():
        for tag in ROLE_ORDER:
            if tag in tags:
                buckets[tag].append(role)
                break
    for tags in buckets.values():
        tags.sort()
    # handle roles that match the category name being first
    for tag, roles in buckets.items():
        if tag.lower() in roles:
            roles.remove(tag.lower())
            roles.insert(0, tag.lower())
    # handle "vanilla" roles being last (villager/cultist/thrall)
    for role in Hidden_Eligible:
        for roles in buckets.values():
            if role in roles:
                roles.remove(role)
                roles.append(role)
    return itertools.chain.from_iterable([buckets[tag] for tag in ROLE_ORDER])

def all_cats() -> dict[str, Category]:
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    # make a copy so that the original cannot be mutated and skip the * alias
    return {k: v for k, v in ROLE_CATS.items() if k != "*"}

def all_roles() -> dict[str, list[Category]]:
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    roles = {}
    # sort the categories for each role by the main category (team affiliation) first,
    # followed by all other categories in alphabetical order
    for role, tags in ROLES.items():
        cats = set(ROLE_CATS[tag] for tag in tags)
        main_cat = cats & TEAMS
        cats.difference_update(main_cat)
        roles[role] = [next(iter(main_cat))] + sorted(iter(cats), key=str)
    return roles

def all_teams() -> Iterable[Category]:
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    for role in ROLE_ORDER:
        cat = ROLE_CATS[role]
        if cat in TEAMS and cat is not Hidden:
            yield cat

def get_team(var: GameState, role: str) -> Category:
    if not FROZEN:
        raise RuntimeError("Fatal: Role categories are not ready")
    if Hidden in TEAMS and role in Hidden:
        role = var.hidden_role
    for team in TEAMS:
        if role in team:
            return team
    else:
        raise RuntimeError(f"No team defined for role {role}")

def _register_roles(evt: Event):
    global FROZEN
    team_evt = Event("get_role_metadata", {
        "teams": {"Wolfteam", "Vampire Team", "Village", "Neutral", "Hidden"}
    })
    team_evt.dispatch(None, "team_categories")
    teams = set(team_evt.data["teams"])
    for cat in teams:
        if cat not in ROLE_CATS or ROLE_CATS[cat] is All or ROLE_CATS[cat] is Nobody:
            raise ValueError("{0!r} is not a valid role category".format(cat))

    evt = Event("get_role_metadata", {})
    evt.dispatch(None, "role_categories")
    for role, cats in evt.data.items():
        if len(cats & teams) != 1:
            raise RuntimeError("Invalid categories for {0}: Must have exactly one team defined".format(role))
        ROLES[role] = frozenset(cats)
        for cat in cats:
            if cat not in ROLE_CATS or ROLE_CATS[cat] is All or ROLE_CATS[cat] is Nobody:
                raise ValueError("{0!r} is not a valid role category".format(cat))
            ROLE_CATS[cat].roles.add(role)
        All.roles.add(role)

    for cat in ROLE_CATS.values():
        cat.freeze()
    FROZEN = True

    for cat in teams:
        TEAMS.add(ROLE_CATS[cat])

EventListener(_register_roles, priority=1).install("init")

class Category:
    """Base class for role categories."""

    def __init__(self, name, *, alias=None):
        if not FROZEN:
            ROLE_CATS[name] = self
            if alias:
                ROLE_CATS[alias] = self
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

    @roles.setter
    def roles(self, value):
        if FROZEN:
            raise RuntimeError("Fatal: Role categories have already been established")
        self._roles = value

    def freeze(self):
        self._roles = frozenset(self._roles)

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

# For proper auto-completion support in IDEs, please do not try to "save space" by turning this into a loop
# and dynamically creating globals.
All = Category("All", alias="*")
Wolf = Category("Wolf")
Wolfchat = Category("Wolfchat")
Wolfteam = Category("Wolfteam")
Vampire = Category("Vampire")
Vampire_Team = Category("Vampire Team")
Killer = Category("Killer")
Village = Category("Village")
Nocturnal = Category("Nocturnal")
Neutral = Category("Neutral")
Win_Stealer = Category("Win Stealer")
Hidden = Category("Hidden")
Hidden_Eligible = Category("Hidden Eligible")
Safe = Category("Safe")
Spy = Category("Spy")
Intuitive = Category("Intuitive")
Cursed = Category("Cursed")
Innocent = Category("Innocent")
Team_Switcher = Category("Team Switcher")
Village_Objective = Category("Village Objective")
Wolf_Objective = Category("Wolf Objective")
Vampire_Objective = Category("Vampire Objective")
Evil = Category("Evil")
Nobody = Category("Nobody")
