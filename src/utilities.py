import functools
from typing import List

from src.events import Event
from src.messages import messages

__all__ = ["complete_role", "irc_lower",
           "plural", "singular",
           "complete_match", "complete_one_match"]

def irc_lower(nick): # FIXME: deprecated, use src.context.lower
    from src.context import lower
    return lower(nick)

def plural(role, count=2): # FIXME: deprecated, use translation metadata
    if count == 1:
        return role
    bits = role.split()
    if bits[-1][-2:] == "'s":
        bits[-1] = plural(bits[-1][:-2], count)
        bits[-1] += "'" if bits[-1][-1] == "s" else "'s"
    else:
        bits[-1] = {"person": "people",
                    "wolf": "wolves",
                    "has": "have",
                    "succubus": "succubi",
                    "child": "children"}.get(bits[-1], bits[-1] + "s")
    return " ".join(bits)

def singular(plural): # FIXME: deprecated, use translation metadata
    # converse of plural above (kinda)
    # this is used to map plural team names back to singular,
    # so we don't need to worry about stuff like possessives
    # Note that this is currently only ever called on team names,
    # and will require adjustment if one wishes to use it on roles.
    # fool is present since we store fool wins as 'fool' rather than
    # 'fools' as only a single fool wins, however we don't want to
    # chop off the l and have it report 'foo wins'
    # same thing with 'everyone'
    conv = {"wolves": "wolf",
            "succubi": "succubus",
            "fool": "fool",
            "everyone": "everyone"}
    if plural in conv:
        return conv[plural]
    # otherwise we just added an s on the end
    return plural[:-1]

# completes a partial nickname or string from a list
def complete_match(string, matches):
    possible_matches = set()
    for possible in matches:
        if string == possible:
            return [string]
        if possible.startswith(string) or possible.lstrip("[{\\^_`|}]").startswith(string):
            possible_matches.add(possible)
    return sorted(possible_matches)

def complete_one_match(string, matches):
    matches = complete_match(string,matches)
    if len(matches) == 1:
        return matches.pop()
    return None

def complete_role(var, role: str, remove_spaces: bool = False, allow_special: bool = True) -> List[str]:
    """ Match a partial role or alias name into the internal role key.

    :param var: Game state
    :param role: Partial role to match on
    :param remove_spaces: Whether or not to remove all spaces before matching.
        This is meant for contexts where we truly cannot allow spaces somewhere; otherwise we should
        prefer that the user matches including spaces where possible for friendlier-looking commands.
    :param allow_special: Whether to allow special keys (lover, vg activated, etc.)
    :return: A list of 0 elements if the role didn't match anything.
        A list with 1 element containing the internal role key if the role matched unambiguously.
        A list with 2 or more elements containing localized role or alias names if the role had ambiguous matches.
    """
    from src.cats import ROLES # FIXME: should this be moved into cats? ROLES isn't declared in cats.__all__

    role = role.lower()
    if remove_spaces:
        role = role.replace(" ", "")

    role_map = messages.get_role_mapping(reverse=True, remove_spaces=remove_spaces)

    special_keys = set()
    if allow_special:
        evt = Event("get_role_metadata", {})
        evt.dispatch(var, "special_keys")
        special_keys = functools.reduce(lambda x, y: x | y, evt.data.values(), special_keys)

    matches = complete_match(role, role_map.keys())
    if not matches:
        return []

    # strip matches that don't refer to actual roles or special keys (i.e. refer to team names)
    filtered_matches = []
    allowed = ROLES.keys() | special_keys
    for match in matches:
        if role_map[match] in allowed:
            filtered_matches.append(match)

    if len(filtered_matches) == 1:
        return [role_map[filtered_matches[0]]]
    return filtered_matches
