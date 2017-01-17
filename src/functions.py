from src.messages import messages
from src import settings as var
from src import users

__all__ = ["get_players", "get_target"]

def get_players(roles=None):
    if roles is None:
        roles = var.ROLES

    players = set()
    for x in roles:
        if x in var.TEMPLATE_RESTRICTIONS:
            continue
        for p in var.ROLES.get(x, ()):
            players.add(p)

    return [p for p in var.ALL_PLAYERS if p.nick in players]


def get_target(var, wrapper, message, *, allow_self=False, allow_bot=False):
    if not message:
        wrapper.pm(messages["not_enough_parameters"])
        return

    players = get_players()
    if not allow_self and wrapper.source in players:
        players.remove(wrapper.source)

    if allow_bot:
        players.append(users.Bot)

    match, count = users.complete_match(message, players)
    if match is None:
        if not count and users.lower(wrapper.source.nick).startswith(users.lower(message)):
            return wrapper.source
        wrapper.pm(messages["not_playing"].format(message))
        return

    return match
