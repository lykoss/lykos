import random
import math
import threading
from collections import OrderedDict

import botconfig
import src.settings as var
from src.utilities import *
from src.messages import messages
from src import events

def game_mode(name, minp, maxp, likelihood = 0):
    def decor(c):
        c.name = name
        var.GAME_MODES[name] = (c, minp, maxp, likelihood)
        return c
    return decor

reset_roles = lambda i: OrderedDict([(role, (0,) * len(i)) for role in var.ROLE_GUIDE])

def get_lovers():
    lovers = []
    pl = var.list_players()
    for lover in var.LOVERS:
        done = None
        for i, lset in enumerate(lovers):
            if lover in pl and lover in lset:
                if done is not None: # plot twist! two clusters turn out to be linked!
                    done.update(lset)
                    for lvr in var.LOVERS[lover]:
                        if lvr in pl:
                            done.add(lvr)

                    lset.clear()
                    continue

                for lvr in var.LOVERS[lover]:
                    if lvr in pl:
                        lset.add(lvr)
                done = lset

        if done is None and lover in pl:
            lovers.append(set())
            lovers[-1].add(lover)
            for lvr in var.LOVERS[lover]:
                if lvr in pl:
                    lovers[-1].add(lvr)

    while set() in lovers:
        lovers.remove(set())

    return lovers

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
                raise var.InvalidModeException(messages["invalid_mode_args"].format(arg))

            key, val = change
            if key in ("role reveal", "reveal roles"):
                if val not in ("on", "off", "team"):
                    raise var.InvalidModeException(messages["invalid_reveal"].format(val))
                self.ROLE_REVEAL = val
                if val == "off" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "disabled"
                elif val == "team" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "team"
            elif key in ("stats type", "stats"):
                if val not in ("default", "accurate", "team", "disabled"):
                    raise var.InvalidModeException(messages["invalid_stats"].format(val))
                self.STATS_TYPE = val
            elif key == "abstain":
                if val not in ("enabled", "restricted", "disabled"):
                    raise var.InvalidModeException(messages["invalid_abstain"].format(val))
                if val == "enabled":
                    self.ABSTAIN_ENABLED = True
                    self.LIMIT_ABSTAIN = False
                elif val == "restricted":
                    self.ABSTAIN_ENABLED = True
                    self.LIMIT_ABSTAIN = True
                elif val == "disabled":
                    self.ABSTAIN_ENABLED = False

    def startup(self):
        pass

    def teardown(self):
        pass

    # Here so any game mode can use it
    def lovers_chk_win(self, evt, var, lpl, lwolves, lrealwolves):
        winner = evt.data["winner"]
        if winner is not None and winner.startswith("@"):
            return # fool won, lovers can't win even if they would
        all_lovers = get_lovers()
        if len(all_lovers) != 1:
            return # we need exactly one cluster alive for this to trigger

        lovers = all_lovers[0]

        if len(lovers) == lpl:
            evt.data["winner"] = "lovers"
            evt.data["additional_winners"] = list(lovers)
            evt.data["message"] = messages["lovers_win"]

@game_mode("roles", minp = 4, maxp = 35)
class ChangedRolesMode(GameMode):
    """Example: !fgame roles=wolf:1,seer:0,guardian angel:1"""

    def __init__(self, arg=""):
        super().__init__(arg)
        self.MAX_PLAYERS = 35
        self.ROLE_GUIDE = var.ROLE_GUIDE.copy()
        self.ROLE_INDEX = (var.MIN_PLAYERS,)
        arg = arg.replace("=", ":").replace(";", ",")

        for role in self.ROLE_GUIDE:
            self.ROLE_GUIDE[role] = (0,)

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise var.InvalidModeException(messages["invalid_mode_roles"].format(arg))
            role, num = change
            try:
                if role.lower() in var.DISABLED_ROLES:
                    raise var.InvalidModeException(messages["role_disabled"].format(role))
                elif role.lower() in self.ROLE_GUIDE:
                    self.ROLE_GUIDE[role.lower()] = tuple([int(num)] * len(var.ROLE_INDEX))
                elif role.lower() == "default" and num.lower() in self.ROLE_GUIDE:
                    self.DEFAULT_ROLE = num.lower()
                elif role.lower() in ("role reveal", "reveal roles", "stats type", "stats", "abstain"):
                    # handled in parent constructor
                    pass
                else:
                    raise var.InvalidModeException(messages["specific_invalid_role"].format(role))
            except ValueError:
                raise var.InvalidModeException(messages["bad_role_value"])

@game_mode("default", minp = 4, maxp = 24, likelihood = 20)
class DefaultMode(GameMode):
    """Default game mode."""
    def __init__(self, arg="", role_index=var.ROLE_INDEX, role_guide=var.ROLE_GUIDE.copy()):
        # No extra settings, just an explicit way to revert to default settings
        super().__init__(arg)
        self.ROLE_INDEX = role_index
        self.ROLE_GUIDE = role_guide

@game_mode("foolish", minp = 8, maxp = 24, likelihood = 8)
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

@game_mode("mad", minp = 7, maxp = 22, likelihood = 4)
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

@game_mode("evilvillage", minp = 6, maxp = 18, likelihood = 1)
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
              # templates
              "cursed villager" : (   0   ,   1   ,   1   ,   1   ,   1   ),
              "mayor"           : (   0   ,   0   ,   0   ,   1   ,   1   ),
              })

    def startup(self):
        events.add_listener("chk_win", self.chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win)

    def chk_win(self, evt, var, lpl, lwolves, lrealwolves):
        lsafes = len(var.list_players(["oracle", "seer", "guardian angel", "shaman", "hunter", "villager"]))
        lcultists = len(var.list_players(["cultist"]))
        evt.stop_processing = True

        if lrealwolves == 0 and lsafes == 0:
            evt.data["winner"] = "none"
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


@game_mode("classic", minp = 4, maxp = 21, likelihood = 0)
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

@game_mode("rapidfire", minp = 6, maxp = 24, likelihood = 0)
class RapidFireMode(GameMode):
    """Many roles that lead to multiple chain deaths."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.SHARPSHOOTER_CHANCE = 1
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
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

@game_mode("drunkfire", minp = 8, maxp = 17, likelihood = 0)
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

@game_mode("noreveal", minp = 4, maxp = 21, likelihood = 2)
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

@game_mode("lycan", minp = 7, maxp = 21, likelihood = 6)
class LycanMode(GameMode):
    """Many lycans will turn into wolves. Hunt them down before the wolves overpower the village."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (   7   ,   8  ,    9   ,   10  ,   11  ,   12  ,  15   ,  17   ,  19   ,  20   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "guardian angel"    : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "matchmaker"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "hunter"            : (   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "traitor"           : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "clone"             : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ),
            "lycan"             : (   1   ,   1   ,   2   ,   2   ,   2   ,   3   ,   4   ,   4   ,   4   ,   5   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "sharpshooter"      : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "mayor"             : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            })

@game_mode("valentines", minp = 8, maxp = 24, likelihood = 0)
class MatchmakerMode(GameMode):
    """Love is in the air!"""
    def __init__(self, arg=""):
        super().__init__(arg)
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

@game_mode("random", minp = 8, maxp = 24, likelihood = 0)
class RandomMode(GameMode):
    """Completely random and hidden roles."""
    def __init__(self, arg=""):
        self.ROLE_REVEAL = random.choice(("on", "off", "team"))
        self.STATS_TYPE = "disabled" if self.ROLE_REVEAL == "off" else random.choice(("disabled", "team"))
        super().__init__(arg)
        self.LOVER_WINS_WITH_FOOL = True
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        self.ALPHA_WOLF_NIGHTS = 2
        self.TEMPLATE_RESTRICTIONS = {template: frozenset() for template in var.TEMPLATE_RESTRICTIONS}

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

    def role_attribution(self, evt, cli, chk_win_conditions, var, villagers):
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
        addroles["assassin"] = random.randrange(int(len(villagers) ** 1.2 / 8))

        lpl = len(villagers)
        lwolves = sum(addroles[r] for r in var.WOLFCHAT_ROLES)
        lcubs = addroles["wolf cub"]
        lrealwolves = sum(addroles[r] for r in var.WOLF_ROLES - {"wolf cub"})
        lmonsters = addroles["monster"]
        ldemoniacs = addroles["demoniac"]
        ltraitors = addroles["traitor"]
        lpipers = addroles["piper"]
        lsuccubi = addroles["succubus"]

        if chk_win_conditions(lpl, lwolves, lcubs, lrealwolves, lmonsters, ldemoniacs, ltraitors, lpipers, lsuccubi, 0, cli, end_game=False):
            return self.role_attribution(evt, cli, chk_win_conditions, var, villagers)

        evt.prevent_default = True

# Credits to Metacity for designing and current name
# Blame arkiwitect for the original name of KrabbyPatty
@game_mode("aleatoire", minp = 8, maxp = 24, likelihood = 4)
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
            "guardian angel"    : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   3   ,   3   ,   3   ),
            "wolf cub"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ),
            "traitor"           : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "hag"               : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "vengeful ghost"    : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "amnesiac"          : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "lycan"             : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "assassin"          : (   0   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "bureaucrat"        : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "mayor"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            })

@game_mode("alpha", minp = 7, maxp = 24, likelihood = 5)
class AlphaMode(GameMode):
    """Features the alpha wolf who can turn other people into wolves, be careful whom you trust!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (   7   ,   8   ,  10   ,  11   ,  12   ,  14   ,  15   ,  17   ,  18   ,  20   ,  21   ,  24   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            #village roles
            "oracle"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "matchmaker"        : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "village drunk"     : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "guardian angel"    : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "doctor"            : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "harlot"            : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "augur"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   3   ,   3   ,   4   ,   5   ),
            "alpha wolf"        : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "traitor"           : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "lycan"             : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "clone"             : (   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   1   ,   1   ,   1   ,   1   ,   2   ,   2   ,   2   ,   2   ,   3   ,   3   ,   3   ,   4   ),
            })

# original idea by Rossweisse, implemented by Vgr with help from woffle and jacob1
@game_mode("guardian", minp = 8, maxp = 16, likelihood = 0)
class GuardianMode(GameMode):
    """Game mode full of guardian angels, wolves need to pick them apart!"""
    def __init__(self, arg=""):
        self.LIMIT_ABSTAIN = False
        super().__init__(arg)
        self.ROLE_INDEX =         (   8   ,   10   ,  12   ,  13   ,  15   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            # village roles
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

    def chk_win(self, evt, var, lpl, lwolves, lrealwolves):
        lguardians = len(var.list_players(["guardian angel", "bodyguard"]))

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
            evt.data["winner"] = "none"
            evt.data["message"] = messages["guardian_lose_no_guards"]
        elif lwolves == lguardians and lpl - lwolves - lguardians == 0:
            evt.data["winner"] = "none"
            evt.data["message"] = messages["guardian_lose_with_guards"]
        else:
            evt.data["winner"] = None

@game_mode("charming", minp = 5, maxp = 24, likelihood = 4)
class CharmingMode(GameMode):
    """Charmed players must band together to find the piper in this game mode."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (  5  ,  6  ,  8 ,  10  , 11  , 12  , 14  , 16  , 18  , 19  , 22  , 24  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "seer"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "harlot"          : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "shaman"          : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ),
              "detective"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "bodyguard"       : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2  ),
              # wolf roles
              "wolf"            : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  3  ,  3  ),
              "traitor"         : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "werekitten"      : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "warlock"         : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "sorcerer"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
              # neutral roles
              "piper"           : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "vengeful ghost"  : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              # templates
              "cursed villager" : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "gunner"          : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ),
              "sharpshooter"    : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ),
              "mayor"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "assassin"        : (  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              })

@game_mode("sleepy", minp=8, maxp=24, likelihood=5)
class SleepyMode(GameMode):
    """A small village has become the playing ground for all sorts of supernatural beings."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =        (  8  , 10  , 12  , 15  , 18  , 21  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({
            # village roles
            "seer"             : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "priest"           : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "harlot"           : (  0  ,  0  ,  0  ,  0  ,  1  ,  1  ),
            "detective"        : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
            "vigilante"        : (  0  ,  0  ,  1  ,  1  ,  1  ,  1  ),
            "village drunk"    : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ),
            # wolf roles
            "wolf"             : (  1  ,  1  ,  2  ,  3  ,  4  ,  5  ),
            "werecrow"         : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "traitor"          : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "cultist"          : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            # neutral roles
            "dullahan"         : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "vengeful ghost"   : (  0  ,  0  ,  0  ,  1  ,  1  ,  1  ),
            "monster"          : (  0  ,  0  ,  0  ,  0  ,  1  ,  2  ),
            # templates
            "cursed villager"  : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "blessed villager" : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "prophet"          : (  0  ,  1  ,  1  ,  1  ,  1  ,  1  ),
            "gunner"           : (  0  ,  0  ,  0  ,  0  ,  0  ,  1  ),
            })
        # this ensures that priest will always receive the blessed villager and prophet templates
        # prophet is normally a role by itself, but we're turning it into a template for this mode
        self.TEMPLATE_RESTRICTIONS = var.TEMPLATE_RESTRICTIONS.copy()
        self.TEMPLATE_RESTRICTIONS["cursed villager"] |= {"priest"}
        self.TEMPLATE_RESTRICTIONS["blessed villager"] = frozenset(self.ROLE_GUIDE) - {"priest", "blessed villager", "prophet"}
        self.TEMPLATE_RESTRICTIONS["prophet"] = frozenset(self.ROLE_GUIDE) - {"priest", "blessed villager", "prophet"}
        # this ensures that village drunk will always receive the gunner template
        self.TEMPLATE_RESTRICTIONS["gunner"] = frozenset(self.ROLE_GUIDE) - {"village drunk", "cursed villager", "gunner"}
        # disable wolfchat
        #self.RESTRICT_WOLFCHAT = 0x0f

        self.having_nightmare = None

    def startup(self):
        from src import decorators
        events.add_listener("dullahan_targets", self.dullahan_targets)
        events.add_listener("transition_night_begin", self.setup_nightmares)
        events.add_listener("chk_nightdone", self.prolong_night)
        events.add_listener("transition_day_begin", self.nightmare_kill)
        events.add_listener("del_player", self.happy_fun_times)
        events.add_listener("rename_player", self.rename_player)
        self.north_cmd = decorators.cmd("north", "n", chan=False, pm=True, playing=True, phases=("night",))(self.north)
        self.east_cmd = decorators.cmd("east", "e", chan=False, pm=True, playing=True, phases=("night",))(self.east)
        self.south_cmd = decorators.cmd("south", "s", chan=False, pm=True, playing=True, phases=("night",))(self.south)
        self.west_cmd = decorators.cmd("west", "w", chan=False, pm=True, playing=True, phases=("night",))(self.west)

    def teardown(self):
        from src import decorators
        events.remove_listener("dullahan_targets", self.dullahan_targets)
        events.remove_listener("transition_night_begin", self.setup_nightmares)
        events.remove_listener("chk_nightdone", self.prolong_night)
        events.remove_listener("transition_day_begin", self.nightmare_kill)
        events.remove_listener("del_player", self.happy_fun_times)
        events.remove_listener("rename_player", self.rename_player)
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

    def dullahan_targets(self, evt, cli, var, dullahans, max_targets):
        for dull in dullahans:
            evt.data["targets"][dull] = set(var.ROLES["priest"])

    def setup_nightmares(self, evt, cli, var):
        if random.random() < 1/5:
            from src import decorators
            self.do_nightmare = decorators.handle_error(self.do_nightmare)
            self.having_nightmare = True
            with var.WARNING_LOCK:
                t = threading.Timer(60, self.do_nightmare, (cli, var, random.choice(var.list_players()), var.NIGHT_COUNT))
                t.daemon = True
                t.start()
        else:
            self.having_nightmare = None

    def rename_player(self, evt, cli, var, prefix, nick):
        if self.having_nightmare == prefix:
            self.having_nightmare = nick

    def do_nightmare(self, cli, var, target, night):
        if var.PHASE != "night" or var.NIGHT_COUNT != night:
            return
        if target not in var.list_players():
            return
        self.having_nightmare = target
        pm(cli, self.having_nightmare, messages["sleepy_nightmare_begin"])
        pm(cli, self.having_nightmare, messages["sleepy_nightmare_navigate"])
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
        self.nightmare_step(cli)

    def nightmare_step(self, cli):
        if self.prev_direction == "n":
            directions = "north, east, and west"
        elif self.prev_direction == "e":
            directions = "north, east, and south"
        elif self.prev_direction == "s":
            directions = "east, south, and west"
        elif self.prev_direction == "w":
            directions = "north, south, and west"

        if self.step == 0:
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_0"].format(directions))
        elif self.step == 1:
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_1"].format(directions))
        elif self.step == 2:
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_2"].format(directions))
        elif self.step == 3:
            if "correct" in self.on_path:
                pm(cli, self.having_nightmare, messages["sleepy_nightmare_wake"])
                self.having_nightmare = None
                chk_nightdone(cli)
            elif "fake1" in self.on_path:
                pm(cli, self.having_nightmare, messages["sleepy_nightmare_fake_1"])
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step(cli)
            elif "fake2" in self.on_path:
                pm(cli, self.having_nightmare, messages["sleepy_nightmare_fake_2"])
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step(cli)

    def north(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        if self.prev_direction == "s":
            pm(cli, nick, messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "n":
            self.on_path.add("correct")
            advance = True
        else:
            self.on_path.discard("correct")
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "n":
            self.on_path.add("fake1")
            advance = True
        else:
            self.on_path.discard("fake1")
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "n":
            self.on_path.add("fake2")
            advance = True
        else:
            self.on_path.discard("fake2")
        if advance:
            self.step += 1
            self.prev_direction = "n"
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_restart"])
        self.nightmare_step(cli)

    def east(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        if self.prev_direction == "w":
            pm(cli, nick, messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "e":
            self.on_path.add("correct")
            advance = True
        else:
            self.on_path.discard("correct")
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "e":
            self.on_path.add("fake1")
            advance = True
        else:
            self.on_path.discard("fake1")
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "e":
            self.on_path.add("fake2")
            advance = True
        else:
            self.on_path.discard("fake2")
        if advance:
            self.step += 1
            self.prev_direction = "e"
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_restart"])
        self.nightmare_step(cli)

    def south(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        if self.prev_direction == "n":
            pm(cli, nick, messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "s":
            self.on_path.add("correct")
            advance = True
        else:
            self.on_path.discard("correct")
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "s":
            self.on_path.add("fake1")
            advance = True
        else:
            self.on_path.discard("fake1")
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "s":
            self.on_path.add("fake2")
            advance = True
        else:
            self.on_path.discard("fake2")
        if advance:
            self.step += 1
            self.prev_direction = "s"
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_restart"])
        self.nightmare_step(cli)

    def west(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        if self.prev_direction == "e":
            pm(cli, nick, messages["sleepy_nightmare_invalid_direction"])
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "w":
            self.on_path.add("correct")
            advance = True
        else:
            self.on_path.discard("correct")
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "w":
            self.on_path.add("fake1")
            advance = True
        else:
            self.on_path.discard("fake1")
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "w":
            self.on_path.add("fake2")
            advance = True
        else:
            self.on_path.discard("fake2")
        if advance:
            self.step += 1
            self.prev_direction = "w"
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_restart"])
        self.nightmare_step(cli)

    def prolong_night(self, evt, cli, var):
        if self.having_nightmare is not None:
            evt.data["actedcount"] = -1

    def nightmare_kill(self, evt, cli, var):
        # if True, it means night ended before 1 minute
        if self.having_nightmare is not None and self.having_nightmare is not True and self.having_nightmare in var.list_players():
            var.DYING.add(self.having_nightmare)
            pm(cli, self.having_nightmare, messages["sleepy_nightmare_death"])

    def happy_fun_times(self, evt, cli, var, nick, nickrole, nicktpls, forced_death, end_game, death_triggers, killer_role, deadlist, original, ismain, refresh_pl):
        if death_triggers:
            if nickrole == "priest":
                pl = evt.data["pl"]
                turn_chance = 3/4
                seers = [p for p in var.ROLES["seer"] if p in pl and random.random() < turn_chance]
                harlots = [p for p in var.ROLES["harlot"] if p in pl and random.random() < turn_chance]
                cultists = [p for p in var.ROLES["cultist"] if p in pl and random.random() < turn_chance]
                cli.msg(botconfig.CHANNEL, messages["sleepy_priest_death"])
                for seer in seers:
                    var.ROLES["seer"].remove(seer)
                    var.ROLES["doomsayer"].add(seer)
                    var.FINAL_ROLES[seer] = "doomsayer"
                    pm(cli, seer, messages["sleepy_doomsayer_turn"])
                    relay_wolfchat_command(cli, seer, messages["sleepy_doomsayer_wolfchat"].format(seer), var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)
                for harlot in harlots:
                    var.ROLES["harlot"].remove(harlot)
                    var.ROLES["succubus"].add(harlot)
                    var.FINAL_ROLES[harlot] = "succubus"
                    pm(cli, harlot, messages["sleepy_succubus_turn"])
                for cultist in cultists:
                    var.ROLES["cultist"].remove(cultist)
                    var.ROLES["demoniac"].add(cultist)
                    var.FINAL_ROLES[cultist] = "demoniac"
                    pm(cli, cultist, messages["sleepy_demoniac_turn"])
                # NOTE: chk_win is called by del_player, don't need to call it here even though this has a chance of ending game

# vim: set expandtab:sw=4:ts=4:
