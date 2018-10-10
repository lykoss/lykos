import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

from src.roles.helper.wolves import get_wolfchat_roles, is_known_wolf_ally, send_wolfchat_message

CURSED = UserDict() # type: UserDict[users.User, users.User]
PASSED = UserSet() # type: UserSet[users.Set]

@command("curse", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def curse(var, wrapper, message):
    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    if target in get_all_players(("cursed villager",)):
        wrapper.pm(messages["target_already_cursed"].format(target))
        return

    # There may actually be valid strategy in cursing other wolfteam members,
    # but for now it is not allowed. If someone seems suspicious and shows as
    # villager across multiple nights, safes can use that as a tell that the
    # person is likely wolf-aligned.
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["no_curse_wolf"])
        return

    evt = Event("targeted_command", {"target": target, "exchange": True, "misdirection": True})
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]

    CURSED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["curse_success"].format(target))
    send_wolfchat_message(var, wrapper.source, messages["curse_success_wolfchat"].format(wrapper.source, target), {"warlock"}, role="warlock", command="curse")

    debuglog("{0} (warlock) CURSE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def pass_cmd(var, wrapper, message):
    """Decline to use your special power for that night."""
    del CURSED[:wrapper.source:]
    PASSED.add(wrapper.source)

    wrapper.pm(messages["warlock_pass"])
    send_wolfchat_message(var, wrapper.source, messages["warlock_pass_wolfchat"].format(wrapper.source), {"warlock"}, role="warlock", command="pass")

    debuglog("{0} (warlock) PASS".format(wrapper.source))

@command("retract", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def retract(var, wrapper, message):
    """Retract your curse or pass."""
    del CURSED[:wrapper.source:]
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["warlock_retract"])
    send_wolfchat_message(var, wrapper.source, messages["warlock_retract_wolfchat"].format(wrapper.source), {"warlock"}, role="warlock", command="retract")

    debuglog("{0} (warlock) RETRACT".format(wrapper.source))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(CURSED) + len(PASSED)
    evt.data["nightroles"].extend(get_all_players(("warlock",)))

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del CURSED[:player:]
    PASSED.discard(player)

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "warlock" and evt.data["role"] != "warlock":
        del CURSED[:user:]
        PASSED.discard(user)

    if not evt.data["in_wolfchat"] and evt.data["role"] == "warlock":
        # this means warlock isn't in wolfchat, so only give cursed list
        pl = get_players()
        random.shuffle(pl)
        pl.remove(user)
        player_list = []
        for player in pl:
            if player in get_all_players(("cursed villager",)):
                player_list.append("{0} (cursed".format(player))
            else:
                player_list.append(player.nick)
        user.send(messages["players_list"].format(", ".join(player_list)))

@event_listener("begin_day")
def on_begin_day(evt, var):
    wroles = get_wolfchat_roles(var)
    for warlock, target in CURSED.items():
        if get_main_role(target) not in wroles:
            var.ROLES["cursed villager"].add(target)

    CURSED.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    CURSED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["warlock"] = {"Wolfchat", "Wolfteam", "Nocturnal"}
