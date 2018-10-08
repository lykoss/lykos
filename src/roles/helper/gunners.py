import random
import re

from src.decorators import command, event_listener
from src.containers import UserDict
from src.functions import get_players, get_all_players, get_target, get_main_role, get_reveal_role
from src.messages import messages
from src.status import add_dying, kill_players
from src.events import Event
from src.cats import Wolf, Wolfchat

import botconfig

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

        # get actual victim
        evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
        if not evt.dispatch(var, wrapper.source, target):
            return

        target = evt.data["target"]

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
            an = "n" if targrole.startswith(("a", "e", "i", "o", "u")) else ""
            if realrole in Wolf:
                if var.ROLE_REVEAL == "on":
                    wrapper.send(messages["gunner_victim_wolf_death"].format(target, an, targrole))
                else: # off and team
                    wrapper.send(messages["gunner_victim_wolf_death_no_reveal"].format(target))
                add_dying(var, target, killer_role=get_main_role(wrapper.source), reason="gunner_victim")
                if kill_players(var):
                    return
            elif shoot_evt.data["kill"]:
                accident = "accidentally "
                if gun_evt.data["headshot"] == 1: # would always headshot
                    accident = ""
                wrapper.send(messages["gunner_victim_villager_death"].format(target, accident))
                if var.ROLE_REVEAL in ("on", "team"):
                    wrapper.send(messages["gunner_victim_role"].format(an, targrole))
                add_dying(var, target, killer_role=get_main_role(wrapper.source), reason="gunner_victim")
                if kill_players(var):
                    return
            else:
                wrapper.send(messages["gunner_victim_injured"].format(target))
                var.WOUNDED.add(target)
                lcandidates = list(var.VOTES.keys())
                for cand in lcandidates:  # remove previous vote
                    if target in var.VOTES[cand]:
                        var.VOTES[cand].remove(target)
                        if not var.VOTES.get(cand):
                            del var.VOTES[cand]
                        break
                from src.wolfgame import chk_decision, chk_win
                chk_decision()
                chk_win()

        elif rand <= gun_evt.data["hit"] + gun_evt.data["miss"]:
            wrapper.send(messages["gunner_miss"].format(wrapper.source))
        else: # BOOM! your gun explodes, you're dead
            if var.ROLE_REVEAL in ("on", "team"):
                wrapper.send(messages["gunner_suicide"].format(wrapper.source, get_reveal_role(wrapper.source)))
            else:
                wrapper.send(messages["gunner_suicide_no_reveal"].format(wrapper.source))
            add_dying(var, wrapper.source, killer_role="villager", reason="gunner_suicide") # blame explosion on villager's shoddy gun construction or something
            kill_players(var)

    @event_listener("transition_night_end")
    def on_transition_night_end(evt, var):
        for gunner in get_all_players((rolename,)):
            if GUNNERS[gunner]:
                if gunner.prefers_simple(): # gunner and sharpshooter share the same key for simple
                    gunner.send(messages["gunner_simple"].format(rolename, GUNNERS[gunner], "s" if GUNNERS[gunner] > 1 else ""))
                else:
                    gunner.send(messages["{0}_notify".format(rolename)].format(botconfig.CMD_CHAR, GUNNERS[gunner], "s" if GUNNERS[gunner] > 1 else ""))

    @event_listener("transition_day_resolve_end", priority=4)
    def on_transition_day_resolve_end(evt, var, victims):
        for victim in list(evt.data["dead"]):
            if GUNNERS.get(victim) and "@wolves" in evt.data["killers"][victim]:
                if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
                    # pick a random wolf to be shot
                    wolfset = [wolf for wolf in get_players(Wolf) if wolf not in evt.data["dead"]]
                    if wolfset:
                        deadwolf = random.choice(wolfset)
                        if var.ROLE_REVEAL in ("on", "team"):
                            evt.data["message"][victim].append(messages["gunner_killed_wolf_overnight"].format(victim, deadwolf, get_reveal_role(deadwolf)))
                        else:
                            evt.data["message"][victim].append(messages["gunner_killed_wolf_overnight_no_reveal"].format(victim, deadwolf))
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

    @event_listener("myrole")
    def on_myrole(evt, var, user):
        if GUNNERS.get(user):
            evt.data["messages"].append(messages["gunner_simple"].format(rolename, GUNNERS[user], "" if GUNNERS[user] == 1 else "s"))

    @event_listener("revealroles_role")
    def on_revealroles_role(evt, var, user, role):
        if role == rolename and user in GUNNERS:
            evt.data["special_case"].append("{0} bullet{1}".format(GUNNERS[user], "" if GUNNERS[user] == 1 else "s"))

    @event_listener("reset")
    def on_reset(evt, var):
        GUNNERS.clear()

    return GUNNERS
