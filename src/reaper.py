import time
from datetime import datetime, timedelta
from typing import Set

from src.gamestate import GameState
from src.functions import get_players, get_reveal_role, get_main_role
from src.warnings import add_warning
from src.messages import messages
from src.status import add_dying, kill_players
from src.debug import handle_error
from src import config, locks, users, channels, trans

# TODO: Move stuff from var into module-level globals here

@handle_error
def reaper(var: GameState, gameid: int):
    # check to see if idlers need to be killed.
    last_day_id = var.DAY_COUNT
    num_night_iters = 0
    short = False

    while gameid == var.GAME_ID:
        skip = False
        time.sleep(1 if short else 10)
        short = False
        with locks.reaper:
            # Terminate reaper when game ends
            if not var.in_game:
                return
            if var.PHASE != var.GAMEPHASE:
                # in a phase transition, so don't run the reaper here or else things may break
                # flag to re-run sooner than usual though
                short = True
                continue
            elif not config.Main.get("gameplay.nightchat"):
                if var.PHASE == "night":
                    # don't count nighttime towards idling
                    # this doesn't do an exact count, but is good enough
                    num_night_iters += 1
                    skip = True
                elif var.PHASE == "day" and var.DAY_COUNT != last_day_id:
                    last_day_id = var.DAY_COUNT
                    num_night_iters += 1
                    for user in var.LAST_SAID_TIME:
                        var.LAST_SAID_TIME[user] += timedelta(seconds=10 * num_night_iters)
                    num_night_iters = 0

            if not skip and (var.WARN_IDLE_TIME or var.PM_WARN_IDLE_TIME or var.KILL_IDLE_TIME):  # only if enabled
                to_warn    = set() # type: Set[users.User]
                to_warn_pm = set() # type: Set[users.User]
                to_kill    = set() # type: Set[users.User]
                for user in get_players(var):
                    if user.is_fake:
                        continue
                    lst = var.LAST_SAID_TIME.get(user, var.GAME_START_TIME)
                    tdiff = datetime.now() - lst
                    if var.WARN_IDLE_TIME and (tdiff > timedelta(seconds=var.WARN_IDLE_TIME) and
                                            user not in var.IDLE_WARNED):
                        to_warn.add(user)
                        var.IDLE_WARNED.add(user)
                        var.LAST_SAID_TIME[user] = (datetime.now() - timedelta(seconds=var.WARN_IDLE_TIME))  # Give them a chance
                    elif var.PM_WARN_IDLE_TIME and (tdiff > timedelta(seconds=var.PM_WARN_IDLE_TIME) and
                                            user not in var.IDLE_WARNED_PM):
                        to_warn_pm.add(user)
                        var.IDLE_WARNED_PM.add(user)
                        var.LAST_SAID_TIME[user] = (datetime.now() - timedelta(seconds=var.PM_WARN_IDLE_TIME))
                    elif var.KILL_IDLE_TIME and (tdiff > timedelta(seconds=var.KILL_IDLE_TIME) and
                                            (not var.WARN_IDLE_TIME or user in var.IDLE_WARNED) and
                                            (not var.PM_WARN_IDLE_TIME or user in var.IDLE_WARNED_PM)):
                        to_kill.add(user)
                    elif (tdiff < timedelta(seconds=var.WARN_IDLE_TIME) and
                                            (user in var.IDLE_WARNED or user in var.IDLE_WARNED_PM)):
                        var.IDLE_WARNED.discard(user)  # player saved themselves from death
                        var.IDLE_WARNED_PM.discard(user)
                for user in to_kill:
                    if var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["idle_death"].format(user, get_reveal_role(var, user)))
                    else:
                        channels.Main.send(messages["idle_death_no_reveal"].format(user))
                    if var.in_game:
                        var.DCED_LOSERS.add(user)
                    if var.IDLE_PENALTY:
                        trans.NIGHT_IDLED.discard(user) # don't double-dip if they idled out night as well
                        add_warning(user, var.IDLE_PENALTY, users.Bot, messages["idle_warning"], expires=var.IDLE_EXPIRY)
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
            for dcedplayer, (timeofdc, what) in list(var.DISCONNECTED.items()):
                mainrole = get_main_role(var, dcedplayer)
                revealrole = get_reveal_role(var, dcedplayer)
                if what == "quit" and (datetime.now() - timeofdc) > timedelta(seconds=var.QUIT_GRACE_TIME):
                    if mainrole != "person" and var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["quit_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["quit_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        trans.NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, var.PART_PENALTY, users.Bot, messages["quit_warning"], expires=var.PART_EXPIRY)
                    if var.in_game:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "quit", death_triggers=False)
                elif what == "part" and (datetime.now() - timeofdc) > timedelta(seconds=var.PART_GRACE_TIME):
                    if mainrole != "person" and var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["part_death"].format(dcedplayer, revealrole))
                    else: # FIXME: Merge those two
                        channels.Main.send(messages["part_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.PART_PENALTY:
                        trans.NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, var.PART_PENALTY, users.Bot, messages["part_warning"], expires=var.PART_EXPIRY)
                    if var.in_game:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "part", death_triggers=False)
                elif what == "account" and (datetime.now() - timeofdc) > timedelta(seconds=var.ACC_GRACE_TIME):
                    if mainrole != "person" and var.role_reveal in ("on", "team"):
                        channels.Main.send(messages["account_death"].format(dcedplayer, revealrole))
                    else:
                        channels.Main.send(messages["account_death_no_reveal"].format(dcedplayer))
                    if var.PHASE != "join" and var.ACC_PENALTY:
                        trans.NIGHT_IDLED.discard(dcedplayer) # don't double-dip if they idled out night as well
                        add_warning(dcedplayer, var.ACC_PENALTY, users.Bot, messages["acc_warning"], expires=var.ACC_EXPIRY)
                    if var.in_game:
                        var.DCED_LOSERS.add(dcedplayer)
                    add_dying(var, dcedplayer, "bot", "account", death_triggers=False)
            kill_players(var)
