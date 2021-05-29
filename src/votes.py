from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import random
import copy
import math
import re
from typing import TYPE_CHECKING

from src.containers import UserDict, UserList, UserSet
from src.decorators import command, event_listener
from src.functions import get_players, get_target, get_reveal_role
from src.messages import messages
from src.status import try_absent, get_absent, get_forced_votes, get_all_forced_votes, get_forced_abstains, get_vote_weight, try_lynch_immunity, add_dying, kill_players
from src.events import Event
from src import channels, pregame

if TYPE_CHECKING:
    from src.users import User

VOTES: UserDict[User, UserList] = UserDict()
ABSTAINS: UserSet = UserSet()
ABSTAINED = False
LAST_VOTES = None
LYNCHED: int = 0

@command("lynch", playing=True, pm=True, phases=("day",))
def lynch(var, wrapper, message):
    """Use this to vote for a candidate to be lynched."""
    if not message:
        show_votes.func(var, wrapper, message)
        return
    if wrapper.private:
        return
    msg = re.split(" +", message)[0].strip()

    can_vote_bot = var.CURRENT_GAMEMODE.can_vote_bot(var)

    voted = get_target(var, wrapper, msg, allow_self=var.SELF_LYNCH_ALLOWED, allow_bot=can_vote_bot, not_self_message="no_self_lynch")
    if not voted:
        return

    if try_absent(var, wrapper.source):
        return

    ABSTAINS.discard(wrapper.source)

    for votee in list(VOTES):  # remove previous vote
        if votee is voted and wrapper.source in VOTES[votee]:
            break
        if wrapper.source in VOTES[votee]:
            VOTES[votee].remove(wrapper.source)
            if not VOTES.get(votee) and votee is not voted:
                del VOTES[votee]
            break

    if voted not in VOTES:
        VOTES[voted] = UserList()
    if wrapper.source not in VOTES[voted]:
        VOTES[voted].append(wrapper.source)
        channels.Main.send(messages["player_vote"].format(wrapper.source, voted))

    global LAST_VOTES
    LAST_VOTES = None # reset

    chk_decision(var)

@command("abstain", playing=True, phases=("day",))
def no_lynch(var, wrapper, message):
    """Allow you to abstain from voting for the day."""
    if not var.ABSTAIN_ENABLED:
        wrapper.pm(messages["command_disabled"])
        return
    elif var.LIMIT_ABSTAIN and ABSTAINED:
        wrapper.pm(messages["exhausted_abstain"])
        return
    elif var.LIMIT_ABSTAIN and var.FIRST_DAY:
        wrapper.pm(messages["no_abstain_day_one"])
        return
    elif try_absent(var, wrapper.source):
        return
    for voter in list(VOTES):
        if wrapper.source in VOTES[voter]:
            VOTES[voter].remove(wrapper.source)
            if not VOTES[voter]:
                del VOTES[voter]
    ABSTAINS.add(wrapper.source)
    channels.Main.send(messages["player_abstain"].format(wrapper.source))

    chk_decision(var)

@command("retract", phases=("day", "join"))
def retract(var, wrapper, message):
    """Takes back your vote during the day (for whom to lynch)."""
    if wrapper.source not in get_players() or wrapper.source in var.DISCONNECTED or var.PHASE != "day":
        return

    global LAST_VOTES

    if wrapper.source in ABSTAINS:
        ABSTAINS.remove(wrapper.source)
        wrapper.send(messages["retracted_vote"].format(wrapper.source))
        LAST_VOTES = None # reset
        return

    for votee in list(VOTES):
        if wrapper.source in VOTES[votee]:
            VOTES[votee].remove(wrapper.source)
            if not VOTES[votee]:
                del VOTES[votee]
            wrapper.send(messages["retracted_vote"].format(wrapper.source))
            LAST_VOTES = None # reset
            break
    else:
        wrapper.pm(messages["pending_vote"])

@command("votes", pm=True, phases=("join", "day", "night"))
def show_votes(var, wrapper, message):
    """Show the current votes."""
    pl = get_players()
    if var.PHASE == "join":
        # get gamemode votes in a dict of {mode: number of votes}
        gm_votes = list(Counter(var.GAMEMODE_VOTES.values()).items())
        gm_votes.sort(key=lambda x: x[1], reverse=True) # sort from highest to lowest

        votelist = []
        majority = False
        for gamemode, num_votes in gm_votes:
            # We bold the game mode if:
            # - The number of players is within the bounds of the game mode
            # - This game mode has a majority of votes
            # - It can be randomly picked
            # - No other game mode has a majority
            if (var.GAME_MODES[gamemode][1] <= len(pl) <= var.GAME_MODES[gamemode][2] and
                (not majority or num_votes >= len(pl) / 2) and (var.GAME_MODES[gamemode][3] > 0 or num_votes >= len(pl) / 2)):
                gamemode = messages["bold"].format(gamemode)
                if num_votes >= len(pl) / 2:
                    majority = True
            votelist.append("{0}: {1}".format(gamemode, num_votes))

        msg = ", ".join(votelist)
        if len(pl) >= var.MIN_PLAYERS:
            msg += messages["majority_votes"].format("; " if votelist else "", math.ceil(len(pl) / 2))

        with var.WARNING_LOCK:
            if pregame.START_VOTES:
                msg += messages["start_votes"].format(len(pregame.START_VOTES), pregame.START_VOTES)

        wrapper.send(msg)
        return

    if var.PHASE == "night":
        wrapper.pm(messages["voting_daytime_only"])
        return

    global LAST_VOTES

    if (wrapper.public and LAST_VOTES and var.VOTES_RATE_LIMIT and
            LAST_VOTES + timedelta(seconds=var.VOTES_RATE_LIMIT) > datetime.now()):
        wrapper.pm(messages["command_ratelimited"])
        return

    if wrapper.public and wrapper.source in pl:
        LAST_VOTES = datetime.now()

    if not VOTES:
        msg = messages["no_votes"]
        if wrapper.source in pl:
            LAST_VOTES = None # reset

    else:
        votelist = []
        for votee, voters in VOTES.items():
            votelist.append("{0}: {1} ({2})".format(votee, len(voters), ", ".join(p.nick for p in voters)))
        msg = ", ".join(votelist)

    wrapper.reply(msg, prefix_nick=True)

    avail = len(pl) - len(get_absent(var))
    votesneeded = avail // 2 + 1
    abstaining = len(ABSTAINS)
    if abstaining == 1: # *i18n* hardcoded English
        plural = " has"
    else:
        plural = "s have"

    to_send = messages["vote_stats"].format(len(pl), votesneeded, avail)
    if var.ABSTAIN_ENABLED:
        to_send += messages["vote_stats_abstain"].format(abstaining, plural)

    wrapper.reply(to_send, prefix_nick=True)

@command("vote", pm=True, phases=("join", "day"))
def vote(var, wrapper, message):
    """Vote for a game mode if no game is running, or for a player to be lynched."""
    if message:
        if var.PHASE == "join" and wrapper.public:
            from src.wolfgame import game
            return game.caller(var, wrapper, message)
        return lynch.caller(var, wrapper, message)
    return show_votes.caller(var, wrapper, message)

# Specify timeout=True to force a lynch and end of day even if there is no majority
# admin_forced=True will make it not count towards village's abstain limit if nobody is voted
def chk_decision(var, *, timeout=False, admin_forced=False):
    with var.GRAVEYARD_LOCK:
        players = set(get_players()) - get_absent(var)
        avail = len(players)
        needed = avail // 2 + 1

        to_vote = []

        for votee, voters in VOTES.items():
            votes = (set(voters) | get_forced_votes(var, votee)) - get_forced_abstains(var)
            if sum(get_vote_weight(var, x) for x in votes) >= needed:
                to_vote.append(votee)
                break

        behaviour_evt = Event("lynch_behaviour", {"num_lynches": 1, "kill_ties": False, "force": timeout}, votes=VOTES, players=avail)
        behaviour_evt.dispatch(var)

        num_lynches = behaviour_evt.data["num_lynches"]
        kill_ties = behaviour_evt.data["kill_ties"]
        force = behaviour_evt.data["force"]

        abstaining = False
        if not to_vote:
            if len((ABSTAINS | get_forced_abstains(var)) - get_all_forced_votes(var)) >= avail / 2:
                abstaining = True
            elif force:
                voting = []
                if VOTES:
                    plurality = [(x, len(y)) for x, y in VOTES.items()]
                    plurality.sort(key=lambda x: x[1])
                    votee, value = plurality.pop()
                    max_value = value
                    # Fetch all of the highest ties, exit out if we find someone lower
                    # If everyone is tied, then at some point plurality will be empty,
                    # but the values will still be at the max. Everything's fine, just break
                    while value == max_value:
                        voting.append(votee)
                        if not plurality:
                            break
                        votee, value = plurality.pop()

                if len(voting) == 1:
                    to_vote.append(voting[0])
                elif voting and kill_ties:
                    if set(voting) == set(get_players()): # killing everyone off? have you considered not doing that
                        abstaining = True
                    else:
                        to_vote.extend(voting)
                elif not admin_forced:
                    abstaining = True

        if abstaining:
            for forced_abstainer in get_forced_abstains(var):
                if forced_abstainer not in ABSTAINS: # did not explicitly abstain
                    channels.Main.send(messages["player_meek_abstain"].format(forced_abstainer))

            abstain_evt = Event("abstain", {})
            abstain_evt.dispatch(var, (ABSTAINS | get_forced_abstains(var)) - get_all_forced_votes(var))

            global ABSTAINED
            ABSTAINED = True
            channels.Main.send(messages["village_abstain"])

            from src.wolfgame import transition_night
            transition_night()

        if to_vote:
            global LYNCHED
            LYNCHED += len(to_vote) # track how many people we've lynched today

            if timeout:
                channels.Main.send(messages["sunset_lynch"])

            for votee in to_vote:
                voters = list(VOTES[votee])
                for forced_voter in get_forced_votes(var, votee):
                    if forced_voter not in voters: # did not explicitly vote
                        channels.Main.send(messages["impatient_vote"].format(forced_voter, votee))
                        voters.append(forced_voter) # they need to be counted as voting for them still

                if not try_lynch_immunity(var, votee):
                    lynch_evt = Event("lynch", {}, players=avail)
                    if lynch_evt.dispatch(var, votee, voters):
                        to_send = "lynch_no_reveal"
                        if var.ROLE_REVEAL in ("on", "team"):
                            to_send = "lynch_reveal"
                        lmsg = messages[to_send].format(votee, get_reveal_role(votee))
                        channels.Main.send(lmsg)
                        add_dying(var, votee, "villager", "lynch")

            kill_players(var, end_game=False) # FIXME

        elif timeout:
            channels.Main.send(messages["sunset"])

        from src.wolfgame import chk_win
        if chk_win():
            return # game ended, just exit out

        if timeout or LYNCHED >= num_lynches:
            from src.wolfgame import transition_night
            transition_night()

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    if var.PHASE == "day":
        if player in VOTES:
            del VOTES[player] # Delete other people's votes on the player
        for k in list(VOTES):
            if player in VOTES[k]:
                VOTES[k].remove(player)
                if not VOTES[k]:  # no more votes on that person
                    del VOTES[k]
                break # can only vote once

        if player in ABSTAINS:
            ABSTAINS.remove(player)

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    global LAST_VOTES, LYNCHED
    LAST_VOTES = None
    LYNCHED = 0
    ABSTAINS.clear()
    VOTES.clear()

@event_listener("reset")
def on_reset(evt, var):
    global ABSTAINED, LAST_VOTES, LYNCHED
    ABSTAINED = False
    LAST_VOTES = None
    LYNCHED = 0
    ABSTAINS.clear()
    VOTES.clear()
