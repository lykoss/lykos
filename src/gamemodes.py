import random
import math
import threading
import copy
import functools
from datetime import datetime
from collections import defaultdict, OrderedDict

import botconfig
import src.settings as var
from src.utilities import *
from src.messages import messages
from src.functions import get_players, get_all_players, get_main_role, change_role
from src.decorators import handle_error, command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src import events, channels, users

def game_mode(name, minp, maxp, likelihood=0):
    def decor(c):
        c.name = name
        var.GAME_MODES[name] = (c, minp, maxp, likelihood)
        return c
    return decor

reset_roles = lambda i: OrderedDict([(role, (0,) * len(i)) for role in var.ROLE_GUIDE])

class GameMode:
    def __init__(self, arg=""):
        if not arg:
            return

        arg = arg.replace("=", ":").replace(";", ",")

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.lower().replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise InvalidModeException(messages["invalid_mode_args"].format(arg))

            key, val = change
            if key in ("role reveal", "reveal roles"):
                if val not in ("on", "off", "team"):
                    raise InvalidModeException(messages["invalid_reveal"].format(val))
                self.ROLE_REVEAL = val
                if val == "off" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "disabled"
                elif val == "team" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "team"
            elif key in ("stats type", "stats"):
                if val not in ("default", "accurate", "team", "disabled", "experimental"):
                    raise InvalidModeException(messages["invalid_stats"].format(val))
                self.STATS_TYPE = val
            elif key == "abstain":
                if val not in ("enabled", "restricted", "disabled"):
                    raise InvalidModeException(messages["invalid_abstain"].format(val))
                if val == "enabled":
                    self.ABSTAIN_ENABLED = True
                    self.LIMIT_ABSTAIN = False
                elif val == "restricted":
                    self.ABSTAIN_ENABLED = True
                    self.LIMIT_ABSTAIN = True
                elif val == "disabled":
                    self.ABSTAIN_ENABLED = False
            elif key == "lover wins with fool":
                if val not in ("true", "false"):
                    raise InvalidModeException(messages["invalid_lover_wins_with_fool"].format(val))
                self.LOVER_WINS_WITH_FOOL = True if val == "true" else False

    def startup(self):
        pass

    def teardown(self):
        pass

    # Here so any game mode can use it
    def lovers_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        winner = evt.data["winner"]
        if winner is not None and winner.startswith("@"):
            return # fool won, lovers can't win even if they would
        from src.roles.matchmaker import get_lovers
        all_lovers = get_lovers()
        if len(all_lovers) != 1:
            return # we need exactly one cluster alive for this to trigger

        lovers = all_lovers[0]

        if len(lovers) == lpl:
            evt.data["winner"] = "lovers"
            evt.data["additional_winners"] = list(l.nick for l in lovers)
            evt.data["message"] = messages["lovers_win"]

    def all_dead_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if evt.data["winner"] == "no_team_wins":
            evt.data["winner"] = "everyone"
            evt.data["message"] = messages["everyone_died_won"]

@game_mode("roles", minp=4, maxp=35)
class ChangedRolesMode(GameMode):
    """Example: !fgame roles=wolf:1,seer:0,guardian angel:1"""

    def __init__(self, arg=""):
        super().__init__(arg)
        self.MAX_PLAYERS = 35
        self.ROLE_GUIDE = var.ROLE_GUIDE.copy()
        self.ROLE_INDEX = (var.MIN_PLAYERS,)
        arg = arg.replace("=", ":").replace(";", ",")

        for role in self.ROLE_GUIDE.keys():
            self.ROLE_GUIDE[role] = (0,)

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise InvalidModeException(messages["invalid_mode_roles"].format(arg))
            role, num = change
            try:
                if role.lower() in var.DISABLED_ROLES:
                    raise InvalidModeException(messages["role_disabled"].format(role))
                elif role.lower() in self.ROLE_GUIDE:
                    self.ROLE_GUIDE[role.lower()] = tuple([int(num)] * len(var.ROLE_INDEX))
                elif role.lower() == "default" and num.lower() in self.ROLE_GUIDE:
                    self.DEFAULT_ROLE = num.lower()
                elif role.lower() in ("role reveal", "reveal roles", "stats type", "stats", "abstain", "lover wins with fool"):
                    # handled in parent constructor
                    pass
                else:
                    raise InvalidModeException(messages["specific_invalid_role"].format(role))
            except ValueError:
                raise InvalidModeException(messages["bad_role_value"])

@game_mode("default", minp=4, maxp=24, likelihood=40)
class DefaultMode(GameMode):
    """Default game mode."""
    def __init__(self, arg="", role_index=var.ROLE_INDEX, role_guide=var.ROLE_GUIDE):
        # No extra settings, just an explicit way to revert to default settings
        super().__init__(arg)
        self.ROLE_INDEX = role_index
        self.ROLE_GUIDE = role_guide

    def startup(self):
        events.add_listener("chk_decision", self.chk_decision, priority=20)

    def teardown(self):
        events.remove_listener("chk_decision", self.chk_decision, priority=20)

    def chk_decision(self, evt, var, force):
        if len(var.ALL_PLAYERS) <= 9 and var.VILLAGERGAME_CHANCE > 0:
            if users.Bot in evt.data["votelist"]:
                if len(evt.data["votelist"][users.Bot]) == len(set(evt.params.voters) - evt.data["not_lynching"]):
                    channels.Main.send(messages["villagergame_nope"])
                    from src.wolfgame import stop_game
                    stop_game(var, "wolves")
                    evt.prevent_default = True
                else:
                    del evt.data["votelist"][users.Bot]

@game_mode("villagergame", minp=4, maxp=9, likelihood=0)
class VillagergameMode(GameMode):
    """This mode definitely does not exist, now please go away."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.fake_index = var.ROLE_INDEX
        self.fake_guide = var.ROLE_GUIDE.copy()
        self.ROLE_INDEX =       (  4  ,  6  ,  7  ,  8  ,  9  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            "seer"            : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "shaman"          : (  0  ,  0  ,  1  ,  1  ,  1  ),
            "harlot"          : (  0  ,  0  ,  0  ,  1  ,  1  ),
            "crazed shaman"   : (  0  ,  0  ,  0  ,  0  ,  1  ),
            "cursed villager" : (  0  ,  1  ,  1  ,  1  ,  1  ),
            })

    def startup(self):
        events.add_listener("chk_win", self.chk_win)
        events.add_listener("chk_nightdone", self.chk_nightdone)
        events.add_listener("transition_day_begin", self.transition_day)
        events.add_listener("retribution_kill", self.on_retribution_kill, priority=4)
        events.add_listener("chk_decision", self.chk_decision, priority=20)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win)
        events.remove_listener("chk_nightdone", self.chk_nightdone)
        events.remove_listener("transition_day_begin", self.transition_day)
        events.remove_listener("retribution_kill", self.on_retribution_kill, priority=4)
        events.remove_listener("chk_decision", self.chk_decision, priority=20)

    def chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        # village can only win via unanimous vote on the bot nick
        # villagergame_lose should probably explain that mechanic
        # Note: not implemented here since that needs to work in default too
        pc = len(var.ALL_PLAYERS)
        if (pc >= 8 and lpl <= 4) or lpl <= 2:
            evt.data["winner"] = ""
            evt.data["message"] = messages["villagergame_lose"].format(botconfig.CMD_CHAR, users.Bot.nick)
        else:
            evt.data["winner"] = None

    def chk_nightdone(self, evt, var):
        transition_day = evt.data["transition_day"]
        evt.data["transition_day"] = lambda gameid=0: self.prolong_night(var, gameid, transition_day)

    def prolong_night(self, var, gameid, transition_day):
        nspecials = len(get_all_players(("seer", "harlot", "shaman", "crazed shaman")))
        rand = random.gauss(5, 1.5)
        if rand <= 0 and nspecials > 0:
            transition_day(gameid=gameid)
        else:
            t = threading.Timer(abs(rand), transition_day, kwargs={"gameid": gameid})
            t.start()

    def transition_day(self, evt, var):
        # 30% chance we kill a safe, otherwise kill at random
        # when killing safes, go after seer, then harlot, then shaman
        self.delaying_night = False
        pl = get_players()
        tgt = None
        seer = None
        hlt = None
        hvst = None
        shmn = None
        if len(var.ROLES["seer"]) == 1:
            seer = list(var.ROLES["seer"])[0]
        if len(var.ROLES["harlot"]) == 1:
            hlt = list(var.ROLES["harlot"])[0]
            from src.roles import harlot
            hvst = harlot.VISITED.get(hlt)
            if hvst is not None:
                pl.remove(hlt)
        if len(var.ROLES["shaman"]) == 1:
            shmn = list(var.ROLES["shaman"])[0]
        if random.random() < 0.3:
            if seer:
                tgt = seer
            elif hvst:
                tgt = hvst
            elif shmn:
                tgt = shmn
            elif hlt and not hvst:
                tgt = hlt
        if not tgt:
            tgt = random.choice(pl)
        from src.roles import wolf
        wolf.KILLS[users.Bot] = [tgt]

    def on_retribution_kill(self, evt, var, victim, orig_target):
        # There are no wolves for this totem to kill
        if orig_target == "@wolves":
            evt.data["target"] = None
            evt.stop_processing = True

    def chk_decision(self, evt, var, force):
        if users.Bot in evt.data["votelist"]:
            if len(evt.data["votelist"][users.Bot]) == len(set(evt.params.voters) - evt.data["not_lynching"]):
                channels.Main.send(messages["villagergame_win"])
                from src.wolfgame import stop_game
                stop_game(var, "everyone")
                evt.prevent_default = True
            else:
                del evt.data["votelist"][users.Bot]

@game_mode("foolish", minp=8, maxp=24, likelihood=10)
class FoolishMode(GameMode):
    """Contains the fool, be careful not to lynch them!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (  8  ,  9  ,  10 , 11  , 12  , 15  , 17  , 20  , 21  , 22  , 24  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "oracle"          : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "harlot"          : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  2  ),
              "bodyguard"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ),
              "augur"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "hunter"          : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "shaman"          : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # wolf roles
              "wolf"            : (  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  3  ,  3  ,  3  ,  3  ,  4  ),
              "traitor"         : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ),
              "wolf cub"        : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "sorcerer"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # neutral roles
              "clone"           : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "fool"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # templates
              "cursed villager" : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "gunner"          : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ),
              "sharpshooter"    : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "mayor"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              })

@game_mode("mad", minp=7, maxp=22, likelihood=5)
class MadMode(GameMode):
    """This game mode has mad scientist and many things that may kill you."""
    def __init__(self, arg=""):
        super().__init__(arg)
        # gunner and sharpshooter always get 1 bullet
        self.SHOTS_MULTIPLIER = 0.0001
        self.SHARPSHOOTER_MULTIPLIER = 0.0001
        self.ROLE_INDEX =         (  7  ,  8  ,  10 , 12  , 14  , 15  , 17  , 18  , 20  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "seer"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "mad scientist"   : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "detective"       : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "guardian angel"  : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              "hunter"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ),
              "harlot"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ),
              "village drunk"   : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # wolf roles
              "wolf"            : (  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  2  ),
              "traitor"         : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "werecrow"        : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "wolf cub"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  2  ),
              "cultist"         : (  1  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # neutral roles
              "vengeful ghost"  : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "jester"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
              # templates
              "cursed villager" : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "gunner"          : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "sharpshooter"    : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "assassin"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
              })

@game_mode("evilvillage", minp=6, maxp=18, likelihood=5)
class EvilVillageMode(GameMode):
    """Majority of the village is wolf aligned, safes must secretly try to kill the wolves."""
    def __init__(self, arg=""):
        self.ABSTAIN_ENABLED = False
        super().__init__(arg)
        self.DEFAULT_ROLE = "cultist"
        self.DEFAULT_SEEN_AS_VILL = False
        self.ROLE_INDEX =         (   6   ,   8   ,  10   ,  12   ,  15   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "seer"            : (   0   ,   1   ,   1   ,   1   ,   1   ),
              "guardian angel"  : (   0   ,   0   ,   1   ,   1   ,   1   ),
              "shaman"          : (   0   ,   0   ,   0   ,   1   ,   1   ),
              "hunter"          : (   1   ,   1   ,   1   ,   1   ,   2   ),
              # wolf roles
              "wolf"            : (   1   ,   1   ,   1   ,   1   ,   2   ),
              "minion"          : (   0   ,   0   ,   1   ,   1   ,   1   ),
              # neutral roles
              "fool"            : (   0   ,   0   ,   1   ,   1   ,   1   ),
              })

    def startup(self):
        events.add_listener("chk_win", self.chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win)

    def chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        lsafes = len(list_players(["oracle", "seer", "guardian angel", "shaman", "hunter", "villager"]))
        lcultists = len(list_players(["cultist"]))
        evt.stop_processing = True

        if lrealwolves == 0 and lsafes == 0:
            evt.data["winner"] = "no_team_wins"
            evt.data["message"] = messages["evil_no_win"]
        elif lrealwolves == 0:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_villager_win"]
        elif lsafes == 0:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["evil_wolf_win"]
        elif lcultists == 0:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_cultists_dead"]
        elif lsafes == lpl / 2:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_villager_tie"]
        elif lsafes > lpl / 2:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["evil_more_villagers"]
        else:
            try:
                if evt.data["winner"][0] != "@":
                    evt.data["winner"] = None
            except TypeError:
                evt.data["winner"] = None


@game_mode("classic", minp=4, maxp=21, likelihood=0)
class ClassicMode(GameMode):
    """Classic game mode from before all the changes."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ABSTAIN_ENABLED = False
        self.ROLE_INDEX =         (   4   ,   6   ,   8   ,  10   ,  12   ,  15   ,  17   ,  18   ,  20   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "seer"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "village drunk"   : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "harlot"          : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "bodyguard"       : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
              "detective"       : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              # wolf roles
              "wolf"            : (   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   3   ,   3   ,   4   ),
              "traitor"         : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              "werecrow"        : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              # templates
              "cursed villager" : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
              "gunner"          : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
              })

@game_mode("rapidfire", minp=6, maxp=24, likelihood=0)
class RapidFireMode(GameMode):
    """Many roles that lead to multiple chain deaths."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.SHARPSHOOTER_CHANCE = 1
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0
        self.ROLE_INDEX =         (   6   ,   8   ,  10   ,  12   ,  15   ,  18   ,  22   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "mad scientist"     : (   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "matchmaker"        : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   2   ),
            "hunter"            : (   0   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "augur"             : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "time lord"         : (   0   ,   0   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   4   ),
            "wolf cub"          : (   0   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ),
            "traitor"           : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "vengeful ghost"    : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   2   ),
            "amnesiac"          : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "assassin"          : (   0   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "sharpshooter"      : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            })

    def startup(self):
        events.add_listener("chk_win", self.all_dead_chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.all_dead_chk_win)

@game_mode("drunkfire", minp=8, maxp=17, likelihood=0)
class DrunkFireMode(GameMode):
    """Most players get a gun, quickly shoot all the wolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.SHARPSHOOTER_CHANCE = 1
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.NIGHT_TIME_LIMIT = 60
        self.NIGHT_TIME_WARN = 40     #     HIT    MISS    SUICIDE   HEADSHOT
        self.GUN_CHANCES              = (   3/7  ,  3/7  ,   1/7   ,   4/5   )
        self.WOLF_GUN_CHANCES         = (   4/7  ,  3/7  ,   0/7   ,   1     )
        self.ROLE_INDEX =         (   8   ,   10  ,  12   ,  14   ,  16   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   2   ,   2   ),
            "village drunk"     : (   2   ,   3   ,   4   ,   4   ,   5   ),
            # wolf roles
            "wolf"              : (   1   ,   2   ,   2   ,   3   ,   3   ),
            "traitor"           : (   1   ,   1   ,   1   ,   1   ,   2   ),
            "hag"               : (   0   ,   0   ,   1   ,   1   ,   1   ),
            # neutral roles
            "crazed shaman"     : (   0   ,   0   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   1   ),
            "assassin"          : (   0   ,   0   ,   0   ,   1   ,   1   ),
            "gunner"            : (   5   ,   6   ,   7   ,   8   ,   9   ),
            "sharpshooter"      : (   2   ,   2   ,   3   ,   3   ,   4   ),
            })

    def startup(self):
        events.add_listener("chk_win", self.all_dead_chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.all_dead_chk_win)

@game_mode("noreveal", minp=4, maxp=21, likelihood=1)
class NoRevealMode(GameMode):
    """Roles are not revealed when players die."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = "off"
        self.STATS_TYPE = "disabled"
        super().__init__(arg)
        self.ROLE_INDEX =         (   4   ,   6   ,   8   ,  10   ,  12   ,  15   ,  17   ,  19   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "guardian angel"    : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "mystic"            : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "detective"         : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "hunter"            : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   3   ),
            "wolf mystic"       : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "traitor"           : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # neutral roles
            "clone"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "lycan"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ),
            "amnesiac"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            })

@game_mode("lycan", minp=7, maxp=21, likelihood=5)
class LycanMode(GameMode):
    """Many lycans will turn into wolves. Hunt them down before the wolves overpower the village."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (   7   ,   8  ,    9   ,   10  ,   11  ,   12  ,  15   ,  17   ,  19   ,  20   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "bodyguard"         : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "matchmaker"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "hunter"            : (   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "wolf shaman"       : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "traitor"           : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "clone"             : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ),
            "lycan"             : (   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   4   ,   4   ,   4   ,   5   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "sharpshooter"      : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "mayor"             : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            })

@game_mode("valentines", minp=8, maxp=24, likelihood=0)
class MatchmakerMode(GameMode):
    """Love is in the air!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.NIGHT_TIME_LIMIT = 150
        self.NIGHT_TIME_WARN = 105
        self.ROLE_INDEX = range(8, 25)
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            "wolf"          : [math.ceil((i ** 1.4) * 0.06) for i in self.ROLE_INDEX],
            "matchmaker"    : [i - math.ceil((i ** 1.4) * 0.06) - (i >= 12) - (i >= 18) for i in self.ROLE_INDEX],
            "monster"       : [i >= 12 for i in self.ROLE_INDEX],
            "mad scientist" : [i >= 18 for i in self.ROLE_INDEX],
            })

    def startup(self):
        events.add_listener("chk_win", self.lovers_chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.lovers_chk_win)

@game_mode("random", minp=8, maxp=24, likelihood=0)
class RandomMode(GameMode):
    """Completely random and hidden roles."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = random.choice(("on", "off", "team"))
        self.STATS_TYPE = "disabled" if self.ROLE_REVEAL == "off" else random.choice(("disabled", "team"))
        super().__init__(arg)
        self.LOVER_WINS_WITH_FOOL = True
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        self.TEMPLATE_RESTRICTIONS = OrderedDict((template, frozenset()) for template in var.TEMPLATE_RESTRICTIONS)

        self.TOTEM_CHANCES = { #  shaman , crazed , wolf
                        "death": (   8   ,   1    ,   1   ),
                   "protection": (   6   ,   1    ,   6   ),
                      "silence": (   4   ,   1    ,   3   ),
                    "revealing": (   2   ,   1    ,   5   ),
                  "desperation": (   4   ,   1    ,   7   ),
                   "impatience": (   7   ,   1    ,   2   ),
                     "pacifism": (   7   ,   1    ,   2   ),
                    "influence": (   7   ,   1    ,   2   ),
                   "narcolepsy": (   4   ,   1    ,   3   ),
                     "exchange": (   1   ,   1    ,   1   ),
                  "lycanthropy": (   1   ,   1    ,   3   ),
                         "luck": (   6   ,   1    ,   7   ),
                   "pestilence": (   3   ,   1    ,   1   ),
                  "retribution": (   5   ,   1    ,   6   ),
                 "misdirection": (   6   ,   1    ,   4   ),
                       "deceit": (   3   ,   1    ,   6   ),
                            }

    def startup(self):
        events.add_listener("role_attribution", self.role_attribution)
        events.add_listener("chk_win", self.lovers_chk_win)

    def teardown(self):
        events.remove_listener("role_attribution", self.role_attribution)
        events.remove_listener("chk_win", self.lovers_chk_win)

    def role_attribution(self, evt, var, chk_win_conditions, villagers):
        lpl = len(villagers) - 1
        addroles = evt.data["addroles"]
        for role in var.ROLE_GUIDE:
            addroles[role] = 0

        wolves = var.WOLF_ROLES - {"wolf cub"}
        addroles[random.choice(list(wolves))] += 1 # make sure there's at least one wolf role
        roles = list(var.ROLE_GUIDE.keys() - var.TEMPLATE_RESTRICTIONS.keys() - {"villager", "cultist", "amnesiac"})
        while lpl:
            addroles[random.choice(roles)] += 1
            lpl -= 1

        addroles["gunner"] = random.randrange(int(len(villagers) ** 1.2 / 4))
        addroles["assassin"] = random.randrange(max(int(len(villagers) ** 1.2 / 8), 1))

        rolemap = defaultdict(set)
        mainroles = {}
        i = 0
        for role, count in addroles.items():
            if count > 0:
                for j in range(count):
                    u = users.FakeUser.from_nick(str(i + j))
                    rolemap[role].add(u.nick)
                    if role not in var.TEMPLATE_RESTRICTIONS:
                        mainroles[u] = role
                i += count

        if chk_win_conditions(rolemap, mainroles, end_game=False):
            return self.role_attribution(evt, var, chk_win_conditions, villagers)

        evt.prevent_default = True

# Credits to Metacity for designing and current name
# Blame arkiwitect for the original name of KrabbyPatty
@game_mode("aleatoire", minp=8, maxp=24, likelihood=10)
class AleatoireMode(GameMode):
    """Game mode created by Metacity and balanced by woffle."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.SHARPSHOOTER_CHANCE = 1
                                              #    SHAMAN   , CRAZED SHAMAN , WOLF SHAMAN
        self.TOTEM_CHANCES = {       "death": (      4      ,       1       ,      0      ),
                                "protection": (      8      ,       1       ,      0      ),
                                   "silence": (      2      ,       1       ,      0      ),
                                 "revealing": (      0      ,       1       ,      0      ),
                               "desperation": (      1      ,       1       ,      0      ),
                                "impatience": (      0      ,       1       ,      0      ),
                                  "pacifism": (      0      ,       1       ,      0      ),
                                 "influence": (      0      ,       1       ,      0      ),
                                "narcolepsy": (      0      ,       1       ,      0      ),
                                  "exchange": (      0      ,       1       ,      0      ),
                               "lycanthropy": (      0      ,       1       ,      0      ),
                                      "luck": (      0      ,       1       ,      0      ),
                                "pestilence": (      1      ,       1       ,      0      ),
                               "retribution": (      4      ,       1       ,      0      ),
                              "misdirection": (      0      ,       1       ,      0      ),
                                    "deceit": (      0      ,       1       ,      0      ),
                             }

        # get default values for wolf shaman's chances
        for totem, (s, cs, ws) in self.TOTEM_CHANCES.items():
            self.TOTEM_CHANCES[totem] = (s, cs, var.TOTEM_CHANCES[totem][2])

        self.ROLE_INDEX =         (   8   ,  10   ,  12   ,  13   ,  14   ,  15   ,  17   ,  18   ,  21   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({ # village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "shaman"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "matchmaker"        : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "hunter"            : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "augur"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "time lord"         : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ),
            "guardian angel"    : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   3   ,   3   ,   3   ),
            "wolf cub"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ),
            "traitor"           : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "hag"               : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "vengeful ghost"    : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "amnesiac"          : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "turncoat"          : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "assassin"          : (   0   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "mayor"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            })

@game_mode("alpha", minp=10, maxp=24, likelihood=5)
class AlphaMode(GameMode):
    """Features the alpha wolf who can turn other people into wolves, be careful whom you trust!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (  10   ,  12   ,  13   ,  14   ,  16   ,  17   ,  18   ,  19   ,  20   ,  21   ,  22   ,  24   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            #village roles
            "oracle"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "doctor"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "harlot"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "guardian angel"    : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ),
            "matchmaker"        : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "augur"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "vigilante"         : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   3   ,   4   ),
            "alpha wolf"        : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "traitor"           : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "amnesiac"          : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "lycan"             : (   2   ,   2   ,   2   ,   2   ,   3   ,   3   ,   3   ,   3   ,   4   ,   4   ,   4   ,   4   ),
            "crazed shaman"     : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "clone"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   3   ,   3   ),
            "mayor"             : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "assassin"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            })

# original idea by Rossweisse, implemented by Vgr with help from woffle and jacob1
@game_mode("guardian", minp=8, maxp=16, likelihood=1)
class GuardianMode(GameMode):
    """Game mode full of guardian angels, wolves need to pick them apart!"""
    def __init__(self, arg=""):
        self.LIMIT_ABSTAIN = False
        super().__init__(arg)
        self.ROLE_INDEX =         (   8   ,   10   ,  12   ,  13   ,  15   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            # village roles
            "village drunk"     : (   1   ,   1   ,   1   ,   1   ,   1   ),
            "bodyguard"         : (   0   ,   0   ,   0   ,   0   ,   1   ),
            "guardian angel"    : (   1   ,   1   ,   2   ,   2   ,   2   ),
            "shaman"            : (   0   ,   1   ,   1   ,   1   ,   1   ),
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   1   ,   2   ),
            "werecrow"          : (   0   ,   1   ,   1   ,   1   ,   1   ),
            "werekitten"        : (   1   ,   1   ,   1   ,   1   ,   1   ),
            "alpha wolf"        : (   0   ,   0   ,   1   ,   1   ,   1   ),
            # neutral roles
            "jester"            : (   0   ,   0   ,   0   ,   1   ,   1   ),
            # templates
            "gunner"            : (   0   ,   0   ,   0   ,   1   ,   1   ),
            "cursed villager"   : (   1   ,   1   ,   2   ,   2   ,   2   ),
            })

        self.TOTEM_CHANCES = { #  shaman , crazed , wolf
                        "death": (   4   ,   1   ,   0   ),
                   "protection": (   8   ,   1   ,   0   ),
                      "silence": (   2   ,   1   ,   0   ),
                    "revealing": (   0   ,   1   ,   0   ),
                  "desperation": (   0   ,   1   ,   0   ),
                   "impatience": (   0   ,   1   ,   0   ),
                     "pacifism": (   0   ,   1   ,   0   ),
                    "influence": (   0   ,   1   ,   0   ),
                   "narcolepsy": (   0   ,   1   ,   0   ),
                     "exchange": (   0   ,   1   ,   0   ),
                  "lycanthropy": (   0   ,   1   ,   0   ),
                         "luck": (   3   ,   1   ,   0   ),
                   "pestilence": (   0   ,   1   ,   0   ),
                  "retribution": (   6   ,   1   ,   0   ),
                 "misdirection": (   4   ,   1   ,   0   ),
                       "deceit": (   0   ,   1   ,   0   ),
                                 }

        for totem, (s, cs, ws) in self.TOTEM_CHANCES.items():
            self.TOTEM_CHANCES[totem] = (s, cs, var.TOTEM_CHANCES[totem][2])

    def startup(self):
        events.add_listener("chk_win", self.chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win)

    def chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        lguardians = len(list_players(["guardian angel", "bodyguard"]))

        if lpl < 1:
            # handled by default win cond checking
            return
        elif not lguardians and lwolves > lpl / 2:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["guardian_wolf_win"]
        elif not lguardians and lwolves == lpl / 2:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["guardian_wolf_tie_no_guards"]
        elif not lrealwolves and lguardians:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["guardian_villager_win"]
        elif not lrealwolves and not lguardians:
            evt.data["winner"] = "villagers"
            evt.data["message"] = messages["guardian_lose_no_guards"]
        elif lwolves == lguardians and lpl - lwolves - lguardians == 0:
            evt.data["winner"] = "wolves"
            evt.data["message"] = messages["guardian_lose_with_guards"]
        else:
            evt.data["winner"] = None

@game_mode("charming", minp=6, maxp=24, likelihood=10)
class CharmingMode(GameMode):
    """Charmed players must band together to find the piper in this game mode."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (  6  ,  8 ,  10  , 11  , 12  , 14  , 16  , 18  , 19  , 22  , 24  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "seer"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "harlot"          : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "shaman"          : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ),
              "detective"       : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "bodyguard"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ),
              # wolf roles
              "wolf"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  3  ,  3  ),
              "traitor"         : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "werekitten"      : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "warlock"         : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "sorcerer"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
              # neutral roles
              "piper"           : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "vengeful ghost"  : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # templates
              "cursed villager" : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "gunner"          : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ),
              "sharpshooter"    : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ),
              "mayor"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "assassin"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              })

@game_mode("sleepy", minp=10, maxp=24, likelihood=1)
class SleepyMode(GameMode):
    """A small village has become the playing ground for all sorts of supernatural beings."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =        ( 10  , 12  , 15  , 18  , 21  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            # village roles
            "seer"             : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "priest"           : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "harlot"           : (  0  ,  0  ,  0  ,  1  ,  1  ),
            "detective"        : (  0  ,  0  ,  1  ,  1  ,  1  ),
            "vigilante"        : (  0  ,  1  ,  1  ,  1  ,  1  ),
            "village drunk"    : (  0  ,  0  ,  0  ,  0  ,  1  ),
            # wolf roles
            "wolf"             : (  1  ,  2  ,  3  ,  4  ,  5  ),
            "werecrow"         : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "traitor"          : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "cultist"          : (  1  ,  1  ,  1  ,  1  ,  1  ),
            # neutral roles
            "dullahan"         : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "vengeful ghost"   : (  0  ,  0  ,  1  ,  1  ,  1  ),
            "monster"          : (  0  ,  0  ,  0  ,  1  ,  2  ),
            # templates
            "cursed villager"  : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "blessed villager" : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "prophet"          : (  1  ,  1  ,  1  ,  1  ,  1  ),
            "gunner"           : (  0  ,  0  ,  0  ,  0  ,  1  ),
            })
        # this ensures that priest will always receive the blessed villager and prophet templates
        # prophet is normally a role by itself, but we're turning it into a template for this mode
        self.TEMPLATE_RESTRICTIONS = var.TEMPLATE_RESTRICTIONS.copy()
        self.TEMPLATE_RESTRICTIONS["cursed villager"] |= {"priest"}
        self.TEMPLATE_RESTRICTIONS["blessed villager"] = frozenset(self.ROLE_GUIDE.keys()) - {"priest", "blessed villager", "prophet"}
        self.TEMPLATE_RESTRICTIONS["prophet"] = frozenset(self.ROLE_GUIDE.keys()) - {"priest", "blessed villager", "prophet"}
        # this ensures that village drunk will always receive the gunner template
        self.TEMPLATE_RESTRICTIONS["gunner"] = frozenset(self.ROLE_GUIDE.keys()) - {"village drunk", "cursed villager", "gunner"}
        self.cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",))
        # disable wolfchat
        #self.RESTRICT_WOLFCHAT = 0x0f

    def startup(self):
        events.add_listener("dullahan_targets", self.dullahan_targets)
        events.add_listener("transition_night_begin", self.setup_nightmares)
        events.add_listener("chk_nightdone", self.prolong_night)
        events.add_listener("transition_day_begin", self.nightmare_kill)
        events.add_listener("del_player", self.happy_fun_times)
        events.add_listener("revealroles", self.on_revealroles)

        self.having_nightmare = UserList()

        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.having_nightmare)

        self.north_cmd = command("north", "n", **cmd_params)(functools.partial(self.move, "n"))
        self.east_cmd = command("east", "e", **cmd_params)(functools.partial(self.move, "e"))
        self.south_cmd = command("south", "s", **cmd_params)(functools.partial(self.move, "s"))
        self.west_cmd = command("west", "w", **cmd_params)(functools.partial(self.move, "w"))

    def teardown(self):
        from src import decorators
        events.remove_listener("dullahan_targets", self.dullahan_targets)
        events.remove_listener("transition_night_begin", self.setup_nightmares)
        events.remove_listener("chk_nightdone", self.prolong_night)
        events.remove_listener("transition_day_begin", self.nightmare_kill)
        events.remove_listener("del_player", self.happy_fun_times)
        events.remove_listener("revealroles", self.on_revealroles)

        def remove_command(name, command):
            if len(decorators.COMMANDS[name]) > 1:
                decorators.COMMANDS[name].remove(command)
            else:
                del decorators.COMMANDS[name]
        remove_command("north", self.north_cmd)
        remove_command("n", self.north_cmd)
        remove_command("east", self.east_cmd)
        remove_command("e", self.east_cmd)
        remove_command("south", self.south_cmd)
        remove_command("s", self.south_cmd)
        remove_command("west", self.west_cmd)
        remove_command("w", self.west_cmd)

        self.having_nightmare.clear()

    def dullahan_targets(self, evt, var, dullahan, max_targets):
        evt.data["targets"].update(var.ROLES["priest"])

    def setup_nightmares(self, evt, var):
        if random.random() < 1/5:
            with var.WARNING_LOCK:
                t = threading.Timer(60, self.do_nightmare, (var, random.choice(get_players()), var.NIGHT_COUNT))
                t.daemon = True
                t.start()

    @handle_error
    def do_nightmare(self, var, target, night):
        if var.PHASE != "night" or var.NIGHT_COUNT != night:
            return
        if target not in get_players():
            return
        self.having_nightmare.clear()
        self.having_nightmare.append(target)
        target.send(messages["sleepy_nightmare_begin"])
        target.send(messages["sleepy_nightmare_navigate"])
        self.correct = [None, None, None]
        self.fake1 = [None, None, None]
        self.fake2 = [None, None, None]
        directions = ["n", "e", "s", "w"]
        self.step = 0
        self.prev_direction = None
        opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
        for i in range(3):
            corrdir = directions[:]
            f1dir = directions[:]
            f2dir = directions[:]
            if i > 0:
                corrdir.remove(opposite[self.correct[i-1]])
                f1dir.remove(opposite[self.fake1[i-1]])
                f2dir.remove(opposite[self.fake2[i-1]])
            else:
                corrdir.remove("s")
                f1dir.remove("s")
                f2dir.remove("s")
            self.correct[i] = random.choice(corrdir)
            self.fake1[i] = random.choice(f1dir)
            self.fake2[i] = random.choice(f2dir)
        self.prev_direction = "n"
        self.start_direction = "n"
        self.on_path = set()
        self.nightmare_step()

    def nightmare_step(self):
        if self.prev_direction == "n":
            directions = "north, east, and west"
        elif self.prev_direction == "e":
            directions = "north, east, and south"
        elif self.prev_direction == "s":
            directions = "east, south, and west"
        elif self.prev_direction == "w":
            directions = "north, south, and west"

        if self.step == 0:
            self.having_nightmare[0].send(messages["sleepy_nightmare_0"].format(directions))
        elif self.step == 1:
            self.having_nightmare[0].send(messages["sleepy_nightmare_1"].format(directions))
        elif self.step == 2:
            self.having_nightmare[0].send(messages["sleepy_nightmare_2"].format(directions))
        elif self.step == 3:
            if "correct" in self.on_path:
                self.having_nightmare[0].send(messages["sleepy_nightmare_wake"])
                self.having_nightmare.clear()
            elif "fake1" in self.on_path:
                self.having_nightmare[0].send(messages["sleepy_nightmare_fake_1"])
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step()
            elif "fake2" in self.on_path:
                self.having_nightmare[0].send(messages["sleepy_nightmare_fake_2"])
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step()

    def move(self, direction, var, wrapper, message):
        opposite = {"n": "s", "e": "w", "s": "n", "w": "e"}
        if self.prev_direction == opposite[direction]:
            wrapper.pm(messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == direction:
            self.on_path.add("correct")
            advance = True
        else:
            self.on_path.discard("correct")
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == direction:
            self.on_path.add("fake1")
            advance = True
        else:
            self.on_path.discard("fake1")
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == direction:
            self.on_path.add("fake2")
            advance = True
        else:
            self.on_path.discard("fake2")
        if advance:
            self.step += 1
            self.prev_direction = direction
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
            wrapper.pm(messages["sleepy_nightmare_restart"])
        self.nightmare_step()

    def prolong_night(self, evt, var):
        if self.having_nightmare:
            evt.data["actedcount"] = -1

    def nightmare_kill(self, evt, var):
        if self.having_nightmare and self.having_nightmare[0] in get_players():
            var.DYING.add(self.having_nightmare[0])
            self.having_nightmare[0].send(messages["sleepy_nightmare_death"])
            del self.having_nightmare[0]

    def happy_fun_times(self, evt, var, user, mainrole, allroles, death_triggers):
        if death_triggers:
            if mainrole == "priest":
                pl = evt.data["pl"]
                turn_chance = 3/4
                seers = [p for p in get_players(("seer",)) if p in pl and random.random() < turn_chance]
                harlots = [p for p in get_players(("harlot",)) if p in pl and random.random() < turn_chance]
                cultists = [p for p in get_players(("cultist",)) if p in pl and random.random() < turn_chance]
                channels.Main.send(messages["sleepy_priest_death"])
                for seer in seers:
                    change_role(var, seer, "seer", "doomsayer", message="sleepy_doomsayer_turn")
                for harlot in harlots:
                    change_role(var, harlot, "harlot", "succubus", message="sleepy_succubus_turn")
                for cultist in cultists:
                    change_role(var, cultist, "cultist", "demoniac", message="sleepy_demoniac_turn")
                # NOTE: chk_win is called by del_player, don't need to call it here even though this has a chance of ending game

    def on_revealroles(self, evt, var, wrapper):
        if self.having_nightmare:
            evt.data["output"].append("\u0002having nightmare\u0002: {0}".format(self.having_nightmare[0]))

@game_mode("maelstrom", minp=8, maxp=24, likelihood=0)
class MaelstromMode(GameMode):
    """Some people just want to watch the world burn."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = "on"
        self.STATS_TYPE = "disabled"
        super().__init__(arg)
        self.LOVER_WINS_WITH_FOOL = True
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        self.ALWAYS_PM_ROLE = True
        # clone is pointless in this mode
        # dullahan doesn't really work in this mode either, if enabling anyway special logic to determine kill list
        # needs to be added above for when dulls are added during the game
        # matchmaker is conditionally enabled during night 1 only
        # monster and demoniac are nearly impossible to counter and don't add any interesting gameplay
        # succubus keeps around entranced people, who are then unable to win even if there are later no succubi (not very fun)
        self.roles = list(var.ROLE_GUIDE.keys() - var.TEMPLATE_RESTRICTIONS.keys() - {"amnesiac", "clone", "dullahan", "matchmaker", "monster", "demoniac", "wild child", "succubus", "piper"})

        self.DEAD_ACCOUNTS = set()
        self.DEAD_HOSTS = set()

    def startup(self):
        events.add_listener("role_attribution", self.role_attribution)
        events.add_listener("transition_night_begin", self.transition_night_begin)
        events.add_listener("del_player", self.on_del_player)
        events.add_listener("join", self.on_join)

    def teardown(self):
        events.remove_listener("role_attribution", self.role_attribution)
        events.remove_listener("transition_night_begin", self.transition_night_begin)
        events.remove_listener("del_player", self.on_del_player)
        events.remove_listener("join", self.on_join)

    def on_del_player(self, evt, var, user, mainrole, allroles, death_triggers):
        if user.is_fake:
            return

        if user.account is not None:
            self.DEAD_ACCOUNTS.add(user.lower().account)

        if not var.ACCOUNTS_ONLY:
            self.DEAD_HOSTS.add(user.lower().host)

    def on_join(self, evt, var, wrapper, message, forced=False):
        if var.PHASE != "day" or (wrapper.public and wrapper.target is not channels.Main):
            return
        temp = wrapper.source.lower()
        if (wrapper.source in var.ALL_PLAYERS or
                temp.account in self.DEAD_ACCOUNTS or
                temp.host in self.DEAD_HOSTS):
            wrapper.pm(messages["maelstrom_dead"])
            return
        if not forced and evt.data["join_player"](var, type(wrapper)(wrapper.source, channels.Main), sanity=False):
            self._on_join(var, wrapper)
            evt.prevent_default = True
        elif forced:
            # in fjoin, handle this differently
            jp = evt.data["join_player"]
            evt.data["join_player"] = lambda var, wrapper, who=None, forced=False: jp(var, wrapper, who=who, forced=forced, sanity=False) and self._on_join(var, wrapper)

    def _on_join(self, var, wrapper):
        from src import hooks, channels
        role = random.choice(self.roles)
        with copy.deepcopy(var.ROLES) as rolemap, copy.deepcopy(var.MAIN_ROLES) as mainroles:
            rolemap[role].add(wrapper.source)
            mainroles[wrapper.source] = role

            if self.chk_win_conditions(rolemap, mainroles, end_game=False):
                return self._on_join(var, wrapper)

        if not wrapper.source.is_fake or not botconfig.DEBUG_MODE:
            cmodes = [("+v", wrapper.source)]
            for mode in var.AUTO_TOGGLE_MODES & wrapper.source.channels[channels.Main]:
                cmodes.append(("-" + mode, wrapper.source))
                var.OLD_MODES[wrapper.source].add(mode)
            channels.Main.mode(*cmodes)
        var.ROLES[role].add(wrapper.source)
        var.ORIGINAL_ROLES[role].add(wrapper.source)
        var.FINAL_ROLES[wrapper.source.nick] = role # FIXME: once FINAL_ROLES stores users
        var.MAIN_ROLES[wrapper.source] = role
        var.ORIGINAL_MAIN_ROLES[wrapper.source] = role
        var.LAST_SAID_TIME[wrapper.source.nick] = datetime.now()
        if wrapper.source.nick in var.USERS:
            var.PLAYERS[wrapper.source.nick] = var.USERS[wrapper.source.nick]

        evt = events.Event("new_role", {"messages": [], "role": role}, inherit_from=None)
        # Use "player" as old role, to force wolf event to send "new wolf" messages
        evt.dispatch(var, wrapper.source, "player")
        for message in evt.data["messages"]:
            wrapper.pm(message)

        from src.decorators import COMMANDS
        COMMANDS["myrole"][0].caller(wrapper.source.client, wrapper.source.nick, wrapper.target.name, "") # FIXME: New/old API

    def role_attribution(self, evt, var, chk_win_conditions, villagers):
        self.chk_win_conditions = chk_win_conditions
        evt.data["addroles"] = self._role_attribution(var, villagers, True)

    def transition_night_begin(self, evt, var):
        # don't do this n1
        if var.FIRST_NIGHT:
            return
        villagers = get_players()
        lpl = len(villagers)
        addroles = self._role_attribution(var, villagers, False)

        # shameless copy/paste of regular role attribution
        for role, count in addroles.items():
            selected = random.sample(villagers, count)
            var.ROLES[role].clear()
            var.ROLES[role].update(selected)
            for x in selected:
                villagers.remove(x)

        # Handle roles that need extra help
        for doctor in var.ROLES["doctor"]:
            var.DOCTORS[doctor.nick] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * lpl)

        # Clear totem tracking; this would let someone that gets shaman twice in a row to give
        # out a totem to the same person twice in a row, but oh well
        var.LASTGIVEN = {}

        # for end of game stats to show what everyone ended up as on game end
        for role, pl in var.ROLES.items():
            if role in var.TEMPLATE_RESTRICTIONS.keys():
                continue
            for p in pl:
                # discard them from all non-template roles, we don't have a reliable
                # means of tracking their previous role (due to traitor turning, exchange
                # totem, etc.), so we need to iterate through everything.
                for r in var.ORIGINAL_ROLES.keys():
                    if r in var.TEMPLATE_RESTRICTIONS.keys():
                        continue
                    var.ORIGINAL_ROLES[r].discard(p)
                var.ORIGINAL_ROLES[role].add(p)
                var.FINAL_ROLES[p.nick] = role # FIXME
                var.MAIN_ROLES[p] = role
                var.ORIGINAL_MAIN_ROLES[p] = role

    def _role_attribution(self, var, villagers, do_templates):
        lpl = len(villagers) - 1
        addroles = {}
        for role in var.ROLE_GUIDE:
            if role in var.TEMPLATE_RESTRICTIONS.keys() and not do_templates:
                continue
            addroles[role] = 0

        wolves = var.WOLF_ROLES - {"wolf cub"}
        addroles[random.choice(list(wolves))] += 1 # make sure there's at least one wolf role
        roles = self.roles[:]
        if do_templates:
            # mm only works night 1, do_templates is also only true n1
            roles.append("matchmaker")
        while lpl:
            addroles[random.choice(roles)] += 1
            lpl -= 1

        if do_templates:
            addroles["gunner"] = random.randrange(4)
            addroles["sharpshooter"] = random.randrange(addroles["gunner"] + 1)
            addroles["assassin"] = random.randrange(3)
            addroles["cursed villager"] = random.randrange(3)
            addroles["mayor"] = random.randrange(2)
            if random.randrange(100) == 0 and addroles.get("villager", 0) > 0:
                addroles["blessed villager"] = 1

        rolemap = defaultdict(set)
        mainroles = {}
        i = 0
        for role, count in addroles.items():
            if count > 0:
                for j in range(count):
                    u = users.FakeUser.from_nick(str(i + j))
                    rolemap[role].add(u)
                    if role not in var.TEMPLATE_RESTRICTIONS:
                        mainroles[u] = role
                i += count

        if self.chk_win_conditions(rolemap, mainroles, end_game=False):
            return self._role_attribution(var, villagers, do_templates)

        return addroles

# someone let woffle commit while drunk again... tsk tsk
@game_mode("mudkip", minp=5, maxp=15, likelihood=5)
class MudkipMode(GameMode):
    """Why are all the professors named after trees?"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ABSTAIN_ENABLED = False

        # If changing totem chances, pay attention to the transition_night_begin listener as well further down
                                              #    SHAMAN   , CRAZED SHAMAN , WOLF SHAMAN
        self.TOTEM_CHANCES = {       "death": (      5      ,       1       ,      0      ),
                                "protection": (      0      ,       1       ,      5      ),
                                   "silence": (      0      ,       1       ,      0      ),
                                 "revealing": (      0      ,       1       ,      0      ),
                               "desperation": (      0      ,       1       ,      0      ),
                                "impatience": (      0      ,       1       ,      0      ),
                                  "pacifism": (      0      ,       1       ,      0      ),
                                 "influence": (      0      ,       1       ,      0      ),
                                "narcolepsy": (      0      ,       1       ,      0      ),
                                  "exchange": (      0      ,       1       ,      0      ),
                               "lycanthropy": (      0      ,       1       ,      0      ),
                                      "luck": (      0      ,       1       ,      0      ),
                                "pestilence": (      5      ,       1       ,      0      ),
                               "retribution": (      0      ,       1       ,      0      ),
                              "misdirection": (      0      ,       1       ,      5      ),
                                    "deceit": (      0      ,       1       ,      0      ),
                             }
        self.ROLE_INDEX =         (  5  ,  6  ,  7  ,  8  ,  9  , 10  , 11  , 12  , 13  , 14  , 15  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "investigator"    : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "guardian angel"  : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "shaman"          : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "vengeful ghost"  : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "priest"          : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ),
              "amnesiac"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ),
              # wolf roles
              "wolf"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ,  2  ),
              "doomsayer"       : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "wolf shaman"     : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
              "minion"          : (  1  ,  1  ,  1  ,  1  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ),
              # neutral roles
              "jester"          : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "succubus"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ),
              # templates
              "assassin"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              })

        self.recursion_guard = False

    def startup(self):
        events.add_listener("chk_decision", self.chk_decision)
        events.add_listener("daylight_warning", self.daylight_warning)
        events.add_listener("transition_night_begin", self.transition_night_begin)

    def teardown(self):
        events.remove_listener("chk_decision", self.chk_decision)
        events.remove_listener("daylight_warning", self.daylight_warning)
        events.remove_listener("transition_night_begin", self.transition_night_begin)

    def chk_decision(self, evt, var, force):
        # If everyone is voting, end day here with the person with plurality being voted. If there's a tie,
        # kill all tied players rather than hanging. The intent of this is to benefit village team in the event
        # of a stalemate, as they could use the extra help (especially in 5p).
        if self.recursion_guard:
            # in here, this means we're in a child chk_decision event called from this one
            # we need to ensure we don't turn into nighttime prematurely or try to vote
            # anyone other than the person we're forcing the lynch on
            evt.data["transition_night"] = lambda: None
            if force:
                evt.data["votelist"].clear()
                evt.data["votelist"][force] = set()
                evt.data["numvotes"].clear()
                evt.data["numvotes"][force] = 0
            else:
                evt.data["votelist"].clear()
                evt.data["numvotes"].clear()
            return

        avail = len(evt.params.voters)
        voted = sum(map(len, evt.data["votelist"].values()))
        if (avail != voted and not evt.params.timeout) or voted == 0:
            return

        majority = avail // 2 + 1
        maxv = max(evt.data["numvotes"].values())
        if maxv >= majority or force:
            # normal vote code will result in someone being lynched
            # not bailing out here will result in the person being voted twice
            return

        # make a copy in case an event mutates it in recursive calls
        tovote = [p for p, n in evt.data["numvotes"].items() if n == maxv]
        self.recursion_guard = True
        gameid = var.GAME_ID
        last = tovote[-1]

        if evt.params.timeout:
            channels.Main.send(messages["sunset_lynch"])

        from src.wolfgame import chk_decision
        for p in tovote:
            deadlist = tovote[:]
            deadlist.remove(p)
            chk_decision(force=p, deadlist=deadlist, end_game=p is last)

        self.recursion_guard = False
        # gameid changes if game stops due to us voting someone
        if var.GAME_ID == gameid:
            evt.data["transition_night"]()

        # make original chk_decision that called us no-op
        evt.prevent_default = True

    def daylight_warning(self, evt, var):
        evt.data["message"] = "daylight_warning_killtie"

    def transition_night_begin(self, evt, var):
        if var.FIRST_NIGHT:
            # ensure shaman gets death totem on the first night
            var.TOTEM_CHANCES["pestilence"] = (0, 1, 0)
        else:
            var.TOTEM_CHANCES["pestilence"] = (5, 1, 0)

# vim: set sw=4 expandtab:
