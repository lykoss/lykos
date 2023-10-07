from __future__ import annotations

import math
import random
import re
from typing import Any

from src import config, channels
from src.cats import Wolf, Killer
from src.containers import UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target, get_main_role, get_reveal_role
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_dying, kill_players, add_absent, try_protection, is_dying
from src.trans import chk_win
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.users import User
from src.locations import move_player_home

_rolestate: dict[str, dict[str, Any]] = {}

def setup_variables(rolename: str, *, hit: float, headshot: float, explode: float, multiplier: float):
    GUNNERS: UserDict[User, int] = UserDict()
    _rolestate[rolename] = {
        "GUNNERS": GUNNERS
    }

    @command("shoot", playing=True, silenced=True, phases=("day",), roles=(rolename,))
    def shoot(wrapper: MessageDispatcher, message: str):
        """Use this to fire off a bullet at someone in the day if you have bullets."""
        if not GUNNERS[wrapper.source]:
            wrapper.pm(messages["no_bullets"])
            return

        var = wrapper.game_state

        target = get_target(wrapper, re.split(" +", message)[0], not_self_message="gunner_target_self")
        if not target:
            return

        target = try_misdirection(var, wrapper.source, target)
        if try_exchange(var, wrapper.source, target):
            return

        GUNNERS[wrapper.source] -= 1

        gun_evt = Event("gun_chances", {"hit": 0, "explode": 0, "headshot": 0})
        gun_evt.dispatch(var, wrapper.source, rolename)

        hit_dict = {
            "hit": random.random() <= gun_evt.data["hit"],
            "kill": random.random() <= gun_evt.data["headshot"],
            "explode": random.random() <= gun_evt.data["explode"],
        }

        shoot_evt = Event("gun_shoot", hit_dict)
        shoot_evt.dispatch(var, wrapper.source, target, rolename)

        realrole = get_main_role(var, target)
        targrole = get_reveal_role(var, target)

        if shoot_evt.data["hit"]:
            wrapper.send(messages["shoot_success"].format(wrapper.source, target))
            if realrole in Wolf and shoot_evt.data["kill"]:
                protected = try_protection(var, target, wrapper.source, rolename, reason="gunner_victim")
                if protected is not None:
                    channels.Main.send(*protected)
                else:
                    to_send = "gunner_victim_wolf_death_no_reveal"
                    if var.role_reveal == "on":
                        to_send = "gunner_victim_wolf_death"
                    wrapper.send(messages[to_send].format(target, targrole))
                    add_dying(var, target, killer_role=get_main_role(var, wrapper.source), reason="gunner_victim", killer=wrapper.source)
                    kill_players(var)
            elif shoot_evt.data["kill"]:
                protected = try_protection(var, target, wrapper.source, rolename, reason="gunner_victim")
                if protected is not None:
                    channels.Main.send(*protected)
                else:
                    to_send = "gunner_victim_villager_death_accident"
                    if gun_evt.data["headshot"] == 1: # would always headshot
                        to_send = "gunner_victim_villager_death"
                    wrapper.send(messages[to_send].format(target))
                    if var.role_reveal in ("on", "team"):
                        wrapper.send(messages["gunner_victim_role"].format(targrole))
                    add_dying(var, target, killer_role=get_main_role(var, wrapper.source), reason="gunner_victim", killer=wrapper.source)
                    kill_players(var)
            else:
                wrapper.send(messages["gunner_victim_injured"].format(target))
                add_absent(var, target, "wounded")
                move_player_home(var, target)
                from src.votes import chk_decision
                if not chk_win(var):
                    # game didn't immediately end due to injury, see if we should force through a vote
                    chk_decision(var)

        elif shoot_evt.data["explode"]: # BOOM! your gun explodes, you're dead
            to_send = "gunner_suicide_no_reveal"
            if var.role_reveal in ("on", "team"):
                to_send = "gunner_suicide"
            wrapper.send(messages[to_send].format(wrapper.source, get_reveal_role(var, wrapper.source)))
            add_dying(var, wrapper.source, killer_role="villager", reason="gunner_suicide") # blame explosion on villager's shoddy gun construction or something
            kill_players(var)
        else:
            wrapper.send(messages["gunner_miss"].format(wrapper.source))

    @event_listener("send_role", listener_id="gunners.<{}>.on_send_role".format(rolename))
    def on_send_role(evt: Event, var: GameState):
        for gunner in get_all_players(var, (rolename,)):
            if GUNNERS[gunner] or var.always_pm_role:
                gunner.send(messages["{0}_notify".format(rolename)].format(GUNNERS[gunner]))

    @event_listener("del_player", listener_id="gunners.<{}>.on_del_player".format(rolename))
    def on_del_player(evt: Event, var: GameState, victim: User, all_roles: set[str], death_triggers: bool):
        if not death_triggers:
            return
        if GUNNERS.get(victim) and rolename in all_roles and evt.params.killer_role == "wolf" and evt.params.reason == "night_kill":
            if random.random() * 100 < config.Main.get("gameplay.gunner_wolf.kills_attacker"):
                # pick a random wolf to be shot
                wolves = get_players(var, Wolf & Killer)
                if evt.params.killer is not None:
                    # attacked by a wolf not in wolfchat, so only the lone wolf is in danger
                    wolves = [evt.params.killer] if not is_dying(var, evt.params.killer) else []
                if wolves:
                    shot = random.choice(wolves)
                    event = Event("gun_shoot", {"hit": True, "kill": True, "explode": False})
                    event.dispatch(var, victim, shot, rolename)
                    GUNNERS[victim] -= 1  # deduct the used bullet
                    if event.data["hit"] and event.data["kill"]:
                        protected = try_protection(var, shot, victim, rolename, "gunner_overnight_fail")
                        if protected is not None:
                            channels.Main.send(*protected)
                        else:
                            to_send = "gunner_killed_wolf_overnight_no_reveal"
                            if var.role_reveal in ("on", "team"):
                                to_send = "gunner_killed_wolf_overnight"
                            channels.Main.send(messages[to_send].format(victim, shot, get_reveal_role(var, shot)))
                            add_dying(var, shot, killer_role=evt.params.main_role, reason="assassin", killer=victim)
                    elif event.data["hit"]:
                        # shot hit, but didn't kill
                        channels.Main.send(messages["gunner_shoot_overnight_hit"].format(victim))
                        add_absent(var, shot, "wounded")
                        # player will be moved back to home after daytime locations are fixed;
                        # doing it here will simply get overwritten
                    else:
                        # shot was fired and missed
                        channels.Main.send(messages["gunner_shoot_overnight_missed"].format(victim))

            # let wolf steal gun if the gunner has any bullets remaining
            # this gives the looter the "wolf gunner" secondary role
            # if the wolf gunner role isn't loaded, guns cannot be stolen regardless of gameplay.gunner_wolf.steals_gun
            if config.Main.get("gameplay.gunner_wolf.steals_gun") and GUNNERS[victim] and "wolf gunner" in _rolestate:
                possible = get_players(var, Wolf & Killer)
                if evt.params.killer is not None:
                    possible = [evt.params.killer] if not is_dying(var, evt.params.killer) else []
                if possible:
                    looter = random.choice(possible)
                    _rolestate["wolf gunner"]["GUNNERS"][looter] = _rolestate["wolf gunner"]["GUNNERS"].get(looter, 0) + 1
                    del GUNNERS[victim]
                    var.roles["wolf gunner"].add(looter)
                    looter.send(messages["wolf_gunner"].format(victim))

    @event_listener("myrole", listener_id="gunners.<{}>.on_myrole".format(rolename))
    def on_myrole(evt: Event, var: GameState, user: User):
        if GUNNERS.get(user):
            evt.data["messages"].append(messages["gunner_myrole"].format(rolename, GUNNERS[user]))

    @event_listener("revealroles_role", listener_id="gunners.<{}>.on_revealroles_role".format(rolename))
    def on_revealroles_role(evt: Event, var: GameState, user: User, role: str):
        if role == rolename and user in GUNNERS:
            evt.data["special_case"].append(messages["gunner_revealroles"].format(GUNNERS[user]))

    @event_listener("reset", listener_id="gunners.<{}>.on_reset".format(rolename))
    def on_reset(evt: Event, var: GameState):
        GUNNERS.clear()

    @event_listener("new_role", listener_id="gunners.<{}>.on_new_role".format(rolename))
    def on_new_role(evt: Event, var: GameState, user: User, old_role: str):
        if old_role == rolename:
            if evt.data["role"] != rolename:
                del GUNNERS[user]

        elif evt.data["role"] == rolename:
            bullets = math.ceil(multiplier * len(get_players(var)))
            event = Event("gun_bullets", {"bullets": bullets})
            event.dispatch(var, user, rolename)
            GUNNERS[user] = event.data["bullets"]

    @event_listener("gun_chances", listener_id="gunners.<{}>.on_gun_chances".format(rolename))
    def on_gun_chances(evt: Event, var: GameState, player: User, role: str):
        if role == rolename:
            evt.data["hit"] = hit
            evt.data["headshot"] = headshot
            evt.data["explode"] = explode

    return GUNNERS
