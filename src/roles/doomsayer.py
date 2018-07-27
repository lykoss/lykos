import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

from src.roles._wolf_helper import is_known_wolf_ally

SEEN = UserSet()
KILLS = UserDict()
SICK = UserDict()
LYCANS = UserDict()

_mappings = ("death", KILLS), ("lycan", LYCANS), ("sick", SICK)

@command("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("doomsayer",))
def see(var, wrapper, message):
    """Use your paranormal senses to determine a player's doom."""
    if wrapper.source in SEEN:
        wrapper.send(messages["seer_fail"])
        return
    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_see_self")
    if not target:
        return

    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.send(messages["no_see_wolf"])
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, wrapper.source, target)
    if evt.prevent_default:
        return

    target = evt.data["target"]
    targrole = get_main_role(target)

    mode, mapping = random.choice(_mappings)
    wrapper.send(messages["doomsayer_{0}".format(mode)].format(target))
    if mode != "sick" or wrapper.source.nick not in var.IMMUNIZED:
        mapping[wrapper.source] = target

    debuglog("{0} (doomsayer) SEE: {1} ({2}) - {3}".format(wrapper.source, target, targrole, mode.upper()))
    relay_wolfchat_command(wrapper.client, wrapper.source.nick, messages["doomsayer_wolfchat"].format(wrapper.source, target), ("doomsayer",), is_wolf_command=True)

    SEEN.add(wrapper.source)

@event_listener("night_acted")
def on_acted(evt, var, user, actor):
    if user in SEEN:
        evt.data["acted"] = True

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "doomsayer" and target_role != "doomsayer":
        SEEN.discard(actor)
        for name, mapping in _mappings:
            del mapping[:actor:]

    elif target_role == "doomsayer" and actor_role != "doomsayer":
        SEEN.discard(target)
        for name, mapping in _mappings:
            del mapping[:target:]

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    # only remove from SEEN; keep results of sees intact on death
    # so that we can apply them in begin_day even if doomsayer dies.
    SEEN.discard(user)

@event_listener("doctor_immunize")
def on_doctor_immunize(evt, var, doctor, target):
    user = users._get(target) # FIXME
    if user in SICK.values():
        for n, v in list(SICK.items()):
            if v is user:
                del SICK[n]
        evt.data["message"] = "not_sick"

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(SEEN)
    evt.data["nightroles"].extend(get_all_players(("doomsayer",)))

@event_listener("abstain")
def on_abstain(evt, var, user):
    if user in SICK.values():
        user.send(messages["illness_no_vote"])
        evt.prevent_default = True

@event_listener("lynch")
def on_lynch(evt, var, target):
    if target in SICK.values():
        target.send(messages["illness_no_vote"])
        evt.prevent_default = True

@event_listener("get_voters")
def on_get_voters(evt, var):
    evt.data["voters"].difference_update(SICK.values())

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    for target in SICK.values():
        target.queue_message(messages["player_sick"])
    if SICK:
        target.send_messages()

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for killer, victim in list(KILLS.items()):
        evt.data["victims"].append(victim)
        # even though doomsayer is a wolf, remove from onlybywolves since
        # that particular item indicates that they were the target of a wolf !kill.
        # If doomsayer doesn't remove this, roles such as harlot or monster will not
        # die if they are the target of a doomsayer !see that ends up killing the target.
        evt.data["onlybywolves"].discard(victim)
        evt.data["killers"][victim].append(killer)

@event_listener("begin_day")
def on_begin_day(evt, var):
    var.DISEASED.update([p.nick for p in SICK.values()]) # FIXME
    var.SILENCED.update([p.nick for p in SICK.values()]) # FIXME
    var.LYCANTHROPES.update([p.nick for p in LYCANS.values()]) # FIXME

    SEEN.clear()
    KILLS.clear()
    LYCANS.clear()

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    SICK.clear()

@event_listener("reset")
def on_reset(evt, var):
    SEEN.clear()
    KILLS.clear()
    SICK.clear()
    LYCANS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["doomsayer"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal"}

# vim: set sw=4 expandtab:
