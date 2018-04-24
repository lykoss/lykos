import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target, is_known_wolf_ally
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

ROLES = UserDict()  # type: Dict[users.User, str]

@event_listener("role_assignment")
def on_role_assignment(evt, var, gamemode, pl):
    # matchmaker is blacklisted if AMNESIAC_NIGHTS > 1 due to only being able to act night 1
    # clone and traitor are blacklisted due to assumptions made in default !stats computations.
    # If you remove these from the blacklist you will need to modify the default !stats logic
    # chains in order to correctly account for these. As a forewarning, such modifications are
    # nontrivial and will likely require a great deal of thought (and likely new tracking vars)

    roles = var.ROLE_GUIDE.keys() - var.TEMPLATE_RESTRICTIONS.keys() - var.AMNESIAC_BLACKLIST - {var.DEFAULT_ROLE, "amnesiac", "clone", "traitor"}
    if var.AMNESIAC_NIGHTS > 1 and "matchmaker" in roles:
        roles.remove("matchmaker")
    for amnesiac in get_all_players(("amnesiac",)):
        ROLES[amnesiac] = random.choice(list(roles))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    if var.NIGHT_COUNT == var.AMNESIAC_NIGHTS:
        amnesiacs = get_all_players(("amnesiac",))

        for amn in amnesiacs:
            role = ROLES[amn]
            change_role(amn, "amnesiac", role)
            evt = Event("new_role", {})
            evt.dispatch(var, amn, role)
            if var.FIRST_NIGHT: # we don't need to tell them twice if they remember right away
                continue
            showrole = role
            if showrole in var.HIDDEN_VILLAGERS:
                showrole = "villager"
            elif showrole in var.HIDDEN_ROLES:
                showrole = var.DEFAULT_ROLE
            a = "a"
            if showrole.startswith(("a", "e", "i", "o", "u")):
                a = "an"
            amn.send(messages["amnesia_clear"].format(a, showrole))
            if is_known_wolf_ally(amn, amn):
                if role in var.WOLF_ROLES:
                    relay_wolfchat_command(amn.client, amn.nick, messages["amnesia_wolfchat"].format(amn, showrole), var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)
                else:
                    relay_wolfchat_command(amn.client, amn.nick, messages["amnesia_wolfchat"].format(amn, showrole), var.WOLFCHAT_ROLES)

            debuglog("{0} REMEMBER: {1} as {2}".format(amn, role, showrole))

@event_listener("new_role")
def on_new_role(evt, var, user, role):
    if role == "turncoat": # FIXME: Need to split into turncoat.py when split
        var.TURNCOATS[user.nick] = ("none", -1)
    if role == "doctor": # FIXME: Need to split into doctor.py when split
        var.DOCTORS[user.nick] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(get_players()))

@event_listener("investigate")
def on_investigate(evt, var, actor, target):
    if evt.data["role"] == "amnesiac":
        evt.data["role"] = ROLES[target]

@event_listener("exchange_roles")
def on_exchange_roles(evt, var, actor, target, actor_role, target_role):
    if actor_role == "amnesiac":
        actor_role = ROLES[actor]
        if target in ROLES:
            ROLES[actor] = ROLES[target]
            ROLES[target] = actor_role
        else:
            del ROLES[actor]
            ROLES[target] = actor_role

    if target_role == "amnesiac":
        if actor not in ROLES:
            target_role = ROLES[target]
            ROLES[actor] = target_role
            del ROLES[target]
        else: # we swapped amnesiac_roles earlier on, get our version back
            target_role = ROLES[actor]

    evt.data["actor_role"] = actor_role
    evt.data["target_role"] = target_role

@event_listener("revealing_totem")
def on_revealing_totem(evt, var, votee):
    if evt.data["role"] == "amnesiac":
        role = ROLES[votee]
        change_role(votee, "amnesiac", role)
        votee.send(messages["totem_amnesia_clear"])
        nevt = Event("new_role", {})
        nevt.dispatch(var, votee, role)
        evt.data["role"] = role
        # If wolfteam, don't bother giving list of wolves since night is about to start anyway
        # Existing wolves also know that someone just joined their team because revealing totem says what they are

@event_listener("get_reveal_role")
def on_reveal_role(evt, var, user):
    if var.HIDDEN_AMNESIAC and user in var.ORIGINAL_ROLES["amnesiac"]:
        evt.data["role"] = "amnesiac"

@event_listener("get_endgame_message")
def on_get_endgame_message(evt, var, role, players, original_roles):
    if role == "amnesiac":
        for player in players:
            evt.data["message"].append("\u0002{0}\u0002 (would be {1})".format(player, ROLES[player]))
        evt.stop_processing = True

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "amnesiac":
        evt.data["special_case"].append("will become {0}".format(ROLES[user]))

@event_listener("update_stats")
def on_update_stats(evt, var, player, mainrole, revealrole, allroles):
    if not var.HIDDEN_AMNESIAC and var.NIGHT_COUNT >= var.AMNESIAC_NIGHTS:
        if not var.AMNESIAC_BLACKLIST & {mainrole, revealrole}: # make sure roles aren't blacklisted
            evt.data["possible"].add("amnesiac")

@event_listener("reset")
def on_reset(evt, var):
    ROLES.clear()

# vim: set sw=4 expandtab:
