from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional

from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.containers import UserDict, UserSet
from src.gamestate import GameState
from src.functions import get_players, get_reveal_role, get_main_role
from src.warnings import add_warning
from src.messages import messages
from src.status import add_dying, kill_players
from src.events import Event, event_listener
from src.debug import handle_error
from src.users import User
from src import config, locks, users, channels

LAST_SAID_TIME = UserDict()
DISCONNECTED: UserDict[User, tuple[datetime, str]] = UserDict()
IDLE_WARNED = UserSet()
IDLE_WARNED_PM = UserSet()
DCED_LOSERS = UserSet()
NIGHT_IDLED = UserSet()

@handle_error
def reaper(var: GameState, gameid: int):
    # check to see if idlers need to be killed.
    game_start_time = datetime.now()
    last_day_id = var.day_count
    num_night_iters = 0
    short = False

    while var.in_game and gameid == var.game_id:
        skip = False
        time.sleep(1 if short else 10)
        short = False
        with locks.reaper:
            # Terminate reaper when game ends
            if not var.in_game:
                return
            if var.in_phase_transition:
                # in a phase transition, so don't run the reaper here or else things may break
                # flag to re-run sooner than usual though
                short = True
                continue
            elif not config.Main.get("gameplay.nightchat"):
                if var.current_phase == "night":
                    # don't count nighttime towards idling
                    # this doesn't do an exact count, but is good enough
                    num_night_iters += 1
                    skip = True
                elif var.current_phase == "day" and var.day_count != last_day_id:
                    last_day_id = var.day_count
                    num_night_iters += 1
                    for user in LAST_SAID_TIME:
                        LAST_SAID_TIME[user] += timedelta(seconds=10 * num_night_iters)
                    num_night_iters = 0

            if not skip and config.Main.get("reaper.idle.enabled"):  # only if enabled
                to_warn:    set[User] = set()
                to_warn_pm: set[User] = set()
                to_kill:    set[User] = set()
                for user in get_players(var):
                    if user.is_fake:
                        continue
                    lst = LAST_SAID_TIME.get(user, game_start_time)
                    tdiff = datetime.now() - lst
                    if (config.Main.get("reaper.idle.warn.channel") and
                            tdiff > timedelta(seconds=config.Main.get("reaper.idle.warn.channel")) and
                            user not in IDLE_WARNED):
                        to_warn.add(user)
                        IDLE_WARNED.add(user)
                        LAST_SAID_TIME[user] = (datetime.now() - timedelta(seconds=config.Main.get("reaper.idle.warn.channel")))  # Give them a chance
                    elif (config.Main.get("reaper.idle.warn.private") and
                            tdiff > timedelta(seconds=config.Main.get("reaper.idle.warn.private")) and
                            user not in IDLE_WARNED_PM):
                        to_warn_pm.add(user)
                        IDLE_WARNED_PM.add(user)
                        LAST_SAID_TIME[user] = (datetime.now() - timedelta(seconds=config.Main.get("reaper.idle.warn.private")))
                    elif (config.Main.get("reaper.idle.grace") and
                            tdiff > timedelta(seconds=config.Main.get("reaper.idle.grace")) and
                            (not config.Main.get("reaper.idle.warn.channel") or user in IDLE_WARNED) and
                            (not config.Main.get("reaper.idle.warn.private") or user in IDLE_WARNED_PM)):
                        to_kill.add(user)
                    elif tdiff < timedelta(seconds=config.Main.get("reaper.idle.warn.channel")) and (user in IDLE_WARNED or user in IDLE_WARNED_PM):
                        IDLE_WARNED.discard(user)  # player saved themselves from death
                        IDLE_WARNED_PM.discard(user)
                for user in to_kill:
                    if var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["idle_death"].format(user, get_reveal_role(var, user)))
                    else:
                        channels.Main.send(messages["idle_death_no_reveal"].format(user))
                    if var.in_game:
                        DCED_LOSERS.add(user)
                    if config.Main.get("reaper.idle.enabled"):
                        NIGHT_IDLED.discard(user) # don't double-dip if they idled out night as well
                        add_warning(user, config.Main.get("reaper.idle.points"), users.Bot, messages["idle_warning"], expires=config.Main.get("reaper.idle.expiration"))
                    add_dying(var, user, "bot", "idle", death_triggers=False)
                pl = get_players(var)
                x = [a for a in to_warn if a in pl]
                if x:
                    channels.Main.send(messages["channel_idle_warning"].format(x))
                msg_targets = [p for p in to_warn_pm if p in pl]
                for p in msg_targets:
                    p.queue_message(messages["player_idle_warning"].format(channels.Main))
                if msg_targets:
                    p.send_messages()
            for dcedplayer, (timeofdc, what) in list(DISCONNECTED.items()):
                mainrole = get_main_role(var, dcedplayer)
                revealrole = get_reveal_role(var, dcedplayer)
                if (what == "quit" and config.Main.get("reaper.quit.enabled") and
                   (datetime.now() - timeofdc) > timedelta(seconds=config.Main.get("reaper.quit.grace"))):
                    if var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["quit_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["quit_death_no_reveal"].format(dcedplayer))
                    if var.current_phase != "join":
                        NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, config.Main.get("reaper.quit.points"), users.Bot, messages["quit_warning"], expires=config.Main.get("reaper.quit.expiration"))
                    if var.in_game:
                        DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "quit", death_triggers=False)

                elif (what == "part" and config.Main.get("reaper.part.enabled") and
                        (datetime.now() - timeofdc) > timedelta(seconds=config.Main.get("reaper.part.grace"))):
                    if var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["part_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["part_death_no_reveal"].format(dcedplayer))
                    if var.current_phase != "join":
                        NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, config.Main.get("reaper.part.points"), users.Bot, messages["part_warning"], expires=config.Main.get("reaper.part.expiration"))
                    if var.in_game:
                        DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "part", death_triggers=False)

                elif (what == "account" and config.Main.get("reaper.account.enabled") and
                        (datetime.now() - timeofdc) > timedelta(seconds=config.Main.get("reaper.account.grace"))):
                    if var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["account_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["account_death_no_reveal"].format(dcedplayer))
                    if var.current_phase != "join":
                        NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, config.Main.get("reaper.account.points"), users.Bot, messages["acc_warning"], expires=config.Main.get("reaper.account.expiration"))
                    if var.in_game:
                        DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "account", death_triggers=False)
            kill_players(var)

@command("")  # update last said
def update_last_said(wrapper: MessageDispatcher, message: str):
    if wrapper.target is not channels.Main or wrapper.game_state is None:
        return

    if not config.Main.get("reaper.enabled"):
        return

    if wrapper.game_state.in_game:
        LAST_SAID_TIME[wrapper.source] = datetime.now()

    if wrapper.source in get_players(wrapper.game_state) and wrapper.source in IDLE_WARNED_PM:
        wrapper.pm(messages["privmsg_idle_warning"].format(channels.Main))

@handle_error
def return_to_village(var: GameState, target: User, *, show_message: bool, new_user: Optional[User] = None):
    with locks.reaper:
        from src.trans import ORIGINAL_ACCOUNTS
        if channels.Main not in target.channels:
            # managed to leave the channel in between the time return_to_village was scheduled and called
            return

        if target.account not in ORIGINAL_ACCOUNTS.values():
            return

        if target in DISCONNECTED:
            del DISCONNECTED[target]
            if new_user is None:
                new_user = target

            LAST_SAID_TIME[target] = datetime.now()
            DCED_LOSERS.discard(target)

            if new_user is not target:
                # different users, perform a swap. This will clean up disconnected users.
                target.swap(new_user)

            if show_message:
                if config.Main.get("gameplay.nightchat") or var.current_phase != "night":
                    channels.Main.mode(("+v", new_user))
                if target.nick == new_user.nick:
                    channels.Main.send(messages["player_return"].format(new_user))
                else:
                    channels.Main.send(messages["player_return_nickchange"].format(new_user, target))
        else:
            # this particular user doesn't exist in DISCONNECTED, but that doesn't
            # mean that they aren't dced. They may have rejoined as a different nick,
            # for example, and we want to mark them as back without requiring them to do
            # a !swap.
            userlist = users.get(account=target.account, allow_multiple=True, allow_ghosts=True)
            userlist = [u for u in userlist if u in DISCONNECTED]
            if len(userlist) == 1:
                return_to_village(var, userlist[0], show_message=show_message, new_user=target)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if var.in_game: # remove the player from variables if they're in there
        DISCONNECTED.pop(player, None)

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    # Add warnings for people that idled out night
    if config.Main.get("reaper.night_idle.enabled"):
        for player in NIGHT_IDLED:
            if player.is_fake:
                continue
            add_warning(player, config.Main.get("reaper.night_idle.points"), users.Bot, messages["night_idle_warning"], expires=config.Main.get("reaper.night_idle.expiration"))

    LAST_SAID_TIME.clear()
    DISCONNECTED.clear()
    IDLE_WARNED.clear()
    IDLE_WARNED_PM.clear()
    DCED_LOSERS.clear()
    NIGHT_IDLED.clear()
