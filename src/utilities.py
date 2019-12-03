import itertools
import functools
import fnmatch
import re
from collections import defaultdict
from typing import List

import botconfig
import src.settings as var
from src import debuglog
from src.events import Event
from src.messages import messages

__all__ = ["pm", "is_fake_nick", "mass_privmsg", "reply",
           "complete_role", "irc_lower",
           "is_owner", "is_admin", "plural", "singular", "list_players",
           "get_role", "role_order", "break_long_message",
           "complete_match", "complete_one_match", "get_victim"]

# XXX: Replace with wrapper.pm instead
def pm(cli, target, message):
    from src.users import _get
    user = _get(target)
    user.send(message)

is_fake_nick = re.compile(r"^[0-9]+$").search

# XXX: Replace with the queue_message and send_messages methods
def mass_privmsg(cli, targets, msg, notice=False, privmsg=False):
    from src.users import _get
    targs = [_get(t) for t in targets]
    for user in targs:
        user.queue_message(msg)
    if targs:
        user.send_messages()

# FIXME: Deprecated in favor of MessageDispatcher
def reply(cli, nick, chan, msg, private=False, prefix_nick=False):
    from src.users import Bot, _get as users_get
    from src.channels import get as chan_get
    from src.dispatcher import MessageDispatcher
    user = users_get(nick)
    if private or nick == chan or chan == Bot.nick:
        target = Bot
    else:
        target = chan_get(chan)
    wrapper = MessageDispatcher(user, target)
    wrapper.reply(msg, prefix_nick=prefix_nick)

def irc_lower(nick):
    from src.context import lower
    return lower(nick)

def is_owner(nick, ident=None, host=None, acc=None):
    from src.users import _get
    user = _get(nick=nick, ident=ident, host=host, account=acc)
    return user.is_owner()

def is_admin(nick, ident=None, host=None, acc=None):
    from src.users import _get
    user = _get(nick=nick, ident=ident, host=host, account=acc)
    return user.is_admin()

def plural(role, count=2):
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

def singular(plural):
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

def list_players(roles=None, *, mainroles=None):
    from src.functions import get_players
    return [p.nick for p in get_players(roles, mainroles=mainroles)]

def get_role(p):
    # TODO DEPRECATED: replace with get_main_role(user)
    from src import users
    from src.functions import get_main_role
    return get_main_role(users._get(p))

def role_order():
    # Deprecated in favour of cats.role_order()
    from src import cats
    return cats.role_order()

def break_long_message(phrases, joinstr = " "):
    message = []
    count = 0
    for phrase in phrases:
        # IRC max is 512, but freenode splits around 380ish, make 300 to have plenty of wiggle room
        if count + len(joinstr) + len(phrase) > 300:
            message.append("\n" + phrase)
            count = len(phrase)
        else:
            if not message:
                count = len(phrase)
            else:
                count += len(joinstr) + len(phrase)
            message.append(phrase)
    return joinstr.join(message)

#completes a partial nickname or string from a list
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

#wrapper around complete_match() used for roles
def get_victim(cli, nick, victim, in_chan, self_in_list=False, bot_in_list=False):
    from src import users
    chan = botconfig.CHANNEL if in_chan else nick
    if not victim:
        reply(cli, nick, chan, messages["not_enough_parameters"], private=True)
        return
    pl = [x for x in list_players() if x != nick or self_in_list]
    pll = [x.lower() for x in pl]

    if bot_in_list: # for villagergame
        pl.append(users.Bot.nick)
        pll.append(users.Bot.nick.lower())

    tempvictims = complete_match(victim.lower(), pll)
    if len(tempvictims) != 1:
        #ensure messages about not being able to act on yourself work
        if len(tempvictims) == 0 and nick.lower().startswith(victim.lower()):
            return nick
        reply(cli, nick, chan, messages["not_playing"].format(victim), private=True)
        return
    return pl[pll.index(tempvictims.pop())] #convert back to normal casing


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
    from src.cats import ROLES

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
