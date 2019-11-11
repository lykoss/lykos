import random
import re

from src import users
from src.decorators import command, event_listener
from src.containers import UserDict
from src.functions import get_players, get_all_players, get_target, get_main_role, get_reveal_role
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_dying, kill_players, add_absent
from src.events import Event
from src.cats import Wolf, Wolfchat

def setup_variables(rolename):
    GUNNERS = UserDict() # type: UserDict[users.User, int]

    @command("shoot", playing=True, silenced=True, phases=("day",), roles=(rolename,))
    def shoot(var, wrapper, message):
        """Use this to fire off a bullet at someone in the day if you have bullets."""
        if not GUNNERS[wrapper.source]:
            wrapper.pm(messages["no_bullets"])
            return

        target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="gunner_target_self")
        if not target:
            return

        target = try_misdirection(var, wrapper.source, target)
        if try_exchange(var, wrapper.source, target):
            return

        GUNNERS[wrapper.source] -= 1

        gun_evt = Event("gun_chances", {"hit": 0, "miss": 0, "headshot": 0})
        gun_evt.dispatch(var, wrapper.source, rolename)

        rand = random.random() # need to save it

        shoot_evt = Event("gun_shoot", {"hit": rand <= gun_evt.data["hit"], "kill": random.random() <= gun_evt.data["headshot"]})
        shoot_evt.dispatch(var, wrapper.source, target)

        realrole = get_main_role(target)
        targrole = get_reveal_role(target)

        if shoot_evt.data["hit"]:
            wrapper.send(messages["shoot_success"].format(wrapper.source, target))
            if realrole in Wolf:
                to_send = "gunner_victim_wolf_death_no_reveal"
                if var.ROLE_REVEAL == "on":
                    to_send = "gunner_victim_wolf_death"
                wrapper.send(messages[to_send].format(target, targrole))
                add_dying(var, target, killer_role=get_main_role(wrapper.source), reason="gunner_victim")
                if kill_players(var):
                    return
            elif shoot_evt.data["kill"]:
                to_send = "gunner_victim_villager_death_accident"
                if gun_evt.data["headshot"] == 1: # would always headshot
                    to_send = "gunner_victim_villager_death"
                wrapper.send(messages[to_send].format(target))
                if var.ROLE_REVEAL in ("on", "team"):
                    wrapper.send(messages["gunner_victim_role"].format(targrole))
                add_dying(var, target, killer_role=get_main_role(wrapper.source), reason="gunner_victim")
                if kill_players(var):
                    return
            else:
                wrapper.send(messages["gunner_victim_injured"].format(target))
                add_absent(var, target, "wounded")
                from src.votes import chk_decision
                from src.wolfgame import chk_win
                if not chk_win():
                    # game didn't immediately end due to injury, see if we should force through a vote
                    chk_decision(var)

        elif rand <= gun_evt.data["hit"] + gun_evt.data["miss"]:
            wrapper.send(messages["gunner_miss"].format(wrapper.source))
        else: # BOOM! your gun explodes, you're dead
            to_send = "gunner_suicide_no_reveal"
            if var.ROLE_REVEAL in ("on", "team"):
                to_send = "gunner_suicide"
            wrapper.send(messages[to_send].format(wrapper.source, get_reveal_role(wrapper.source)))
            add_dying(var, wrapper.source, killer_role="villager", reason="gunner_suicide") # blame explosion on villager's shoddy gun construction or something
            kill_players(var)

    @event_listener("transition_night_end", listener_id="<{}>.on_transition_night_end".format(rolename))
    def on_transition_night_end(evt, var):
        for gunner in get_all_players((rolename,)):
            if GUNNERS[gunner]:
                if gunner.prefers_simple(): # gunner and sharpshooter share the same key for simple
                    gunner.send(messages["gunner_simple"].format(rolename, GUNNERS[gunner]))
                else:
                    gunner.send(messages["{0}_notify".format(rolename)].format(GUNNERS[gunner]))

    @event_listener("transition_day_resolve_end", priority=4, listener_id="<{}>.on_transition_day_resolve_end".format(rolename))
    def on_transition_day_resolve_end(evt, var, victims):
        for victim in list(evt.data["dead"]):
            if GUNNERS.get(victim) and "@wolves" in evt.data["killers"][victim]:
                if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
                    # pick a random wolf to be shot
                    wolfset = [wolf for wolf in get_players(Wolf) if wolf not in evt.data["dead"]]
                    if wolfset:
                        deadwolf = random.choice(wolfset)
                        to_send = "gunner_killed_wolf_overnight_no_reveal"
                        if var.ROLE_REVEAL in ("on", "team"):
                            to_send = "gunner_killed_wolf_overnight"
                        evt.data["message"][victim].append(messages[to_send].format(victim, deadwolf, get_reveal_role(deadwolf)))
                        evt.data["dead"].append(deadwolf)
                        evt.data["killers"][deadwolf].append(victim)
                        GUNNERS[victim] -= 1 # deduct the used bullet

                if var.WOLF_STEALS_GUN and GUNNERS[victim]: # might have used up the last bullet or something
                    possible = get_players(Wolfchat)
                    random.shuffle(possible)
                    for looter in possible:
                        if looter not in evt.data["dead"]:
                            break
                    else:
                        return # no live wolf, nothing to do here

                    GUNNERS[looter] = GUNNERS.get(looter, 0) + 1
                    del GUNNERS[victim]
                    var.ROLES[rolename].add(looter)
                    looter.send(messages["wolf_gunner"].format(victim))

    @event_listener("myrole", listener_id="<{}>.on_myrole".format(rolename))
    def on_myrole(evt, var, user):
        if GUNNERS.get(user):
            evt.data["messages"].append(messages["gunner_simple"].format(rolename, GUNNERS[user]))

    @event_listener("revealroles_role", listener_id="<{}>.on_revealroles_role".format(rolename))
    def on_revealroles_role(evt, var, user, role):
        if role == rolename and user in GUNNERS:
            evt.data["special_case"].append(messages["gunner_revealroles"].format(GUNNERS[user]))

    @event_listener("reset", listener_id="<{}>.on_reset".format(rolename))
    def on_reset(evt, var):
        GUNNERS.clear()

    return GUNNERS
