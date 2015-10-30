from collections import OrderedDict

import random
import math
import threading

import src.settings as var
from src.utilities import *
import botconfig

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
                raise var.InvalidModeException("Invalid syntax for mode arguments. arg={0}".format(arg))

            key, val = change
            if key in ("role reveal", "reveal roles"):
                if val not in ("on", "off", "team"):
                    raise var.InvalidModeException(("Did not recognize value \u0002{0}\u0002 for role reveal. "+
                                               "Allowed values: on, off, team").format(val))
                self.ROLE_REVEAL = val
                if val == "off" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "disabled"
                elif val == "team" and not hasattr(self, "STATS_TYPE"):
                    self.STATS_TYPE = "team"
            elif key in ("stats type", "stats"):
                if val not in ("default", "accurate", "team", "disabled"):
                    raise var.InvalidModeException(("Did not recognize value \u0002{0}\u0002 for stats type. "+
                                               "Allowed values: default, accurate, team, disabled").format(val))
                self.STATS_TYPE = val
            elif key == "abstain":
                if val not in ("enabled", "restricted", "disabled"):
                    raise var.InvalidModeException(("Did not recognize value \u0002{0}\u0002 for abstain. "+
                                               "Allowed values: enabled, restricted, disabled").format(val))
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
            evt.data["message"] = ("Game over! The remaining villagers through their inseparable "
                                   "love for each other have agreed to stop all of this senseless "
                                   "violence and coexist in peace forever more. All remaining players win.")

@game_mode("roles", minp = 4, maxp = 35)
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
                raise var.InvalidModeException("Invalid syntax for mode roles. arg={0}".format(arg))
            role, num = change
            try:
                if role.lower() in var.DISABLED_ROLES:
                    raise var.InvalidModeException("The role \u0002{0}\u0002 has been disabled.".format(role))
                elif role.lower() in self.ROLE_GUIDE:
                    self.ROLE_GUIDE[role.lower()] = tuple([int(num)] * len(var.ROLE_INDEX))
                elif role.lower() == "default" and num.lower() in self.ROLE_GUIDE:
                    self.DEFAULT_ROLE = num.lower()
                elif role.lower() in ("role reveal", "reveal roles", "stats type", "stats", "abstain"):
                    # handled in parent constructor
                    pass
                else:
                    raise var.InvalidModeException(("The role \u0002{0}\u0002 "+
                                                "is not valid.").format(role))
            except ValueError:
                raise var.InvalidModeException("A bad value was used in mode roles.")

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

@game_mode("mad", minp = 7, maxp = 22, likelihood = 8)
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
            evt.data["message"] = ("Game over! All the villagers are dead, but the cult needed to sacrifice " +
                                 "the wolves to accomplish that. The cult disperses shortly thereafter, " +
                                 "and nobody wins.")
        elif lrealwolves == 0:
            evt.data["winner"] = "villagers"
            evt.data["message"] = ("Game over! All the wolves are dead! The villagers " +
                                   "round up the remaining cultists, hang them, and live " +
                                   "happily ever after.")
        elif lsafes == 0:
            evt.data["winner"] = "wolves"
            evt.data["message"] = ("Game over! All the villagers are dead! The cultists rejoice " +
                                   "with their wolf buddies and start plotting to take over the " +
                                   "next village.")
        elif lcultists == 0:
            evt.data["winner"] = "villagers"
            evt.data["message"] = ("Game over! All the cultists are dead! The now-exposed wolves " +
                                   "are captured and killed by the remaining villagers. A BBQ party " +
                                   "commences shortly thereafter.")
        elif lsafes >= lpl / 2:
            evt.data["winner"] = "villagers"
            evt.data["message"] = ("Game over! There are {0} villagers {1} cultists. They " +
                                   "manage to regain control of the village and dispose of the remaining " +
                                   "cultists.").format("more" if lsafes > lpl / 2 else "the same number of",
                                                       "than" if lsafes > lpl / 2 else "as")
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
        self.STATS_TYPE = "disabled"
        super().__init__(arg)
        self.LOVER_WINS_WITH_FOOL = True
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        self.ALPHA_WOLF_NIGHTS = 2
        self.TEMPLATE_RESTRICTIONS = {template: frozenset() for template in var.TEMPLATE_RESTRICTIONS}

        self.TOTEM_CHANCES = { #  shaman , crazed
                        "death": (   8   ,   1   ),
                   "protection": (   6   ,   1   ),
                      "silence": (   4   ,   1   ),
                    "revealing": (   2   ,   1   ),
                  "desperation": (   4   ,   1   ),
                   "impatience": (   7   ,   1   ),
                     "pacifism": (   7   ,   1   ),
                    "influence": (   7   ,   1   ),
                   "narcolepsy": (   4   ,   1   ),
                     "exchange": (   1   ,   1   ),
                  "lycanthropy": (   1   ,   1   ),
                         "luck": (   6   ,   1   ),
                   "pestilence": (   3   ,   1   ),
                  "retribution": (   5   ,   1   ),
                 "misdirection": (   6   ,   1   ),
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
        ldemoniacs = addroles["demoniacs"]
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
                                              #    SHAMAN   , CRAZED SHAMAN
        self.TOTEM_CHANCES = {       "death": (      4      ,      1      ),
                                "protection": (      8      ,      1      ),
                                   "silence": (      2      ,      1      ),
                                 "revealing": (      0      ,      1      ),
                               "desperation": (      1      ,      1      ),
                                "impatience": (      0      ,      1      ),
                                  "pacifism": (      0      ,      1      ),
                                 "influence": (      0      ,      1      ),
                                "narcolepsy": (      0      ,      1      ),
                                  "exchange": (      0      ,      1      ),
                               "lycanthropy": (      0      ,      1      ),
                                      "luck": (      0      ,      1      ),
                                "pestilence": (      1      ,      1      ),
                               "retribution": (      4      ,      1      ),
                              "misdirection": (      0      ,      1      ),
                             }
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

        self.TOTEM_CHANCES = { #  shaman , crazed
                        "death": (   4   ,   1   ),
                   "protection": (   8   ,   1   ),
                      "silence": (   2   ,   1   ),
                    "revealing": (   0   ,   1   ),
                  "desperation": (   0   ,   1   ),
                   "impatience": (   0   ,   1   ),
                     "pacifism": (   0   ,   1   ),
                    "influence": (   0   ,   1   ),
                   "narcolepsy": (   0   ,   1   ),
                     "exchange": (   0   ,   1   ),
                  "lycanthropy": (   0   ,   1   ),
                         "luck": (   3   ,   1   ),
                   "pestilence": (   0   ,   1   ),
                  "retribution": (   6   ,   1   ),
                 "misdirection": (   4   ,   1   ),
                                 }

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
            evt.data["message"] = ("Game over! There are more wolves than uninjured villagers. With the ancestral " +
                                   "guardians dead, the wolves overpower the defenseless villagers and win.")
        elif not lguardians and lwolves == lpl / 2:
            evt.data["winner"] = "wolves"
            evt.data["message"] = ("Game over! There are the same number of wolves as uninjured villagers. With the ancestral " +
                                   "guardians dead, the wolves overpower the defenseless villagers and win.")
        elif not lrealwolves and lguardians:
            evt.data["winner"] = "villagers"
            evt.data["message"] = ("Game over! All the wolves are dead! The remaining villagers throw a party in honor " +
                                   "of the guardian angels that watched over the village, and live happily ever after.")
        elif not lrealwolves and not lguardians:
            evt.data["winner"] = "none"
            evt.data["message"] = ("Game over! The remaining villagers managed to destroy the wolves, however the guardians " +
                                   "that used to watch over the village are nowhere to be found. The village lives on in an " +
                                   "uneasy peace, not knowing when they will be destroyed completely now that they are " +
                                   "defenseless. Nobody wins.")
        elif lwolves == lguardians and lpl - lwolves - lguardians == 0:
            evt.data["winner"] = "none"
            evt.data["message"] = ("Game over! The guardians, angered by the loss of everyone they were meant to guard, " +
                                   "engage the wolves in battle and mutually assured destruction. After the dust settles " +
                                   "the village is completely dead, and nobody wins.")
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

@game_mode("sleepy", minp=8, maxp=24, likelihood=0)
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
        self.TEMPLATE_RESTRICTIONS["blessed villager"] = frozenset(self.ROLE_GUIDE.keys()) - {"priest", "blessed villager", "prophet"}
        self.TEMPLATE_RESTRICTIONS["prophet"] = frozenset(self.ROLE_GUIDE.keys()) - {"priest", "blessed villager", "prophet"}
        # this ensures that village drunk will always receive the gunner template
        self.TEMPLATE_RESTRICTIONS["gunner"] = frozenset(self.ROLE_GUIDE.keys()) - {"village drunk", "cursed villager", "gunner"}
        # disable wolfchat
        self.RESTRICT_WOLFCHAT = 0x0f

        self.having_nightmare = None

    def startup(self):
        from src import decorators
        events.add_listener("dullahan_targets", self.dullahan_targets)
        events.add_listener("transition_night_begin", self.setup_nightmares)
        events.add_listener("chk_nightdone", self.prolong_night)
        events.add_listener("transition_day_begin", self.nightmare_kill)
        events.add_listener("del_player", self.happy_fun_times)
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
        decorators.COMMANDS["north"].remove(self.north_cmd)
        decorators.COMMANDS["n"].remove(self.north_cmd)
        decorators.COMMANDS["east"].remove(self.east_cmd)
        decorators.COMMANDS["e"].remove(self.east_cmd)
        decorators.COMMANDS["south"].remove(self.south_cmd)
        decorators.COMMANDS["s"].remove(self.south_cmd)
        decorators.COMMANDS["west"].remove(self.west_cmd)
        decorators.COMMANDS["west"].remove(self.west_cmd)

    def dullahan_targets(self, evt, cli, var, dullahans, max_targets):
        for dull in dullahans:
            evt.data["targets"][dull] = set(var.ROLES["priest"])

    def setup_nightmares(self, evt, cli, var):
        if random.random() < 1/5:
            self.having_nightmare = True
            with var.WARNING_LOCK:
                t = threading.Timer(60, self.do_nightmare, (cli, random.choice(var.list_players()))
                t.start()
        else:
            self.having_nightmare = None

    def do_nightmare(self, cli, target):
        self.having_nightmare = target
        pm(cli, self.having_nightmare, ("While walking through the woods, you hear the clopping of hooves behind you. Turning around, " +
                                        "you see a large black horse with dark red eyes and flames where its mane and tail would be. " +
                                        "After a brief period of time, it starts chasing after you! You think if you can cross the bridge " +
                                        "over the nearby river you'll be safe, but your surroundings are almost unrecognizable in this darkness."))
        self.correct = [None, None, None]
        self.fake1 = [None, None, None]
        self.fake2 = [None, None, None]
        directions = ["n", "e", "s", "w"]
        self.step = 0
        for i in range(0, 3):
            self.correct[i] = random.choice(directions)
            self.fake1[i] = random.choice(directions)
            self.fake2[i] = random.choice(directions)
        self.prev_direction = "s" if self.correct[0] != "s" else "w"
        self.start_direction = self.prev_direction
        self.on_path = set()
        self.nightmare_step(cli)

    def nightmare_step(self, cli):
        if self.prev_direction == "n":
            directions = "east, south, and west"
        elif self.prev_direction == "e":
            directions = "north, south, and west"
        elif self.prev_direction == "s":
            directions = "north, east, and west"
        elif self.prev_direction == "w":
            directions = "north, east, and south"

        if self.step == 0:
            pm(cli, self.having_nightmare, ("You find yourself deep in the heart of the woods, with imposing trees covering up what little light " +
                                            "exists with their dense canopy. The paths here are very twisty, and it's easy to wind up going in " +
                                            "circles if one is not careful. Directions are {0}.").format(directions))
        elif self.step == 1:
            pm(cli, self.having_nightmare, ("You come across a small creek, the water babbling softly in the night as if nothing is amiss. " +
                                            "As you approach, a flock of ravens bathing there disperses into all directions. " +
                                            "Directions are {0}.").format(directions))
        elif self.step == 2:
            pm(cli, self.having_nightmare, ("The treeline starts thinning and you start feeling fresh air for the first time in a while, you " +
                                            "must be getting close to the edge of the woods! Directions are {0}.").format(directions))
        elif self.step == 3:
            if "correct" in self.on_path:
                pm(cli, self.having_nightmare, ("You break clear of the woods and see a roaring river ahead with a rope bridge going over it. " +
                                                "You sprint to the bridge with the beast hot on your tail, your adrenaline overcoming your tired " +
                                                "legs as you push yourself for one final burst. You make it across the bridge, and not a moment too " +
                                                "soon as the sun starts rising up, causing you to wake from your dream in a cold sweat."))
                self.having_nightmare = None
                chk_nightdone(cli)
            elif "fake1" in self.on_path:
                pm(cli, self.having_nightmare, ("You break clear of the woods and see a roaring river ahead. However, look as you may you are unable " +
                                                "to find any means of crossing it. Knowing how expansive the river is, and how fast the beast can chase " +
                                                "you if it isn't being slowed down by the foliage, you think it's best to look for the correct side of the " +
                                                "woods again by going back in. Cursing your bad luck, you head back into the woods."))
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step(cli)
            elif "fake2" in self.on_path:
                pm(cli, self.having_nightmare, ("You break clear of the woods only to find an expansive plains ahead of you, with no river in sight. " +
                                                "You must have found your way out through the wrong side of the woods! Attempting to circle around the " +
                                                "woods would result in the beast catching you in short order, so you softly curse at your bad luck as you " +
                                                "head back into the woods to find the correct path."))
                self.step = 0
                self.on_path = set()
                self.prev_direction = self.start_direction
                self.nightmare_step(cli)

    def north(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "n":
            self.on_path.add("correct")
            advance = True
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "n":
            self.on_path.add("fake1")
            advance = True
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "n":
            self.on_path.add("fake2")
            advance = True
        if advance:
            self.step += 1
            self.prev_direction = "n"
        else:
            self.step = 0
            self.prev_direction = self.start_direction
        self.nightmare_step(cli)

    def east(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "e":
            self.on_path.add("correct")
            advance = True
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "e":
            self.on_path.add("fake1")
            advance = True
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "e":
            self.on_path.add("fake2")
            advance = True
        if advance:
            self.step += 1
            self.prev_direction = "e"
        else:
            self.step = 0
            self.prev_direction = self.start_direction
        self.nightmare_step(cli)

    def south(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "s":
            self.on_path.add("correct")
            advance = True
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "s":
            self.on_path.add("fake1")
            advance = True
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "s":
            self.on_path.add("fake2")
            advance = True
        if advance:
            self.step += 1
            self.prev_direction = "s"
        else:
            self.step = 0
            self.prev_direction = self.start_direction
        self.nightmare_step(cli)

    def west(self, cli, nick, chan, rest):
        if nick != self.having_nightmare:
            return
        advance = False
        if ("correct" in self.on_path or self.step == 0) and self.correct[self.step] == "w":
            self.on_path.add("correct")
            advance = True
        if ("fake1" in self.on_path or self.step == 0) and self.fake1[self.step] == "w":
            self.on_path.add("fake1")
            advance = True
        if ("fake2" in self.on_path or self.step == 0) and self.fake2[self.step] == "w":
            self.on_path.add("fake2")
            advance = True
        if advance:
            self.step += 1
            self.prev_direction = "w"
        else:
            self.step = 0
            self.on_path = set()
            self.prev_direction = self.start_direction
        self.nightmare_step(cli)

    def prolong_night(self, evt, cli, var):
        if self.having_nightmare is not None:
            evt.data["actedcount"] = -1

    def nightmare_kill(self, evt, cli, var):
        if self.having_nightmare is not None:
            var.DYING.add(self.having_nightmare)
            pm(cli, self.having_nightmare, ("As the sun starts rising, your legs give out, causing the beast to descend upon you and snuff out your life."))

    def happy_fun_times(self, evt, cli, var, nick, nickrole, nicktpls, forced_death, end_game, death_triggers, killer_role, deadlist, original, ismain, refresh_pl):
        if death_triggers:
            if nickrole == "priest":
                pl = evt.data["pl"]
                turn_chance = 3/4
                seers = [p for p in var.ROLES["seer"] if p in pl and random.random() < turn_chance]
                harlots = [p for p in var.ROLES["harlot"] if p in pl and random.random() < turn_chance]
                cultists = [p for p in var.ROLES["cultist"] if p in pl and random.random() < turn_chance]
                total = sum(map(len, (seers, harlots, cultists)))
                if total > 0:
                    cli.msg(botconfig.CHANNEL, ("The sky suddenly darkens as a thunderstorm appears from nowhere. The bell on the newly-abandoned church starts ringing " +
                                                "in sinister tones, managing to perform \u0002{0}\u0002 {1} before the building is struck repeatedly by lightning, " +
                                                "setting it alight in a raging inferno...").format(total, var.plural("toll", total)))
                    for seer in seers:
                        var.ROLES["seer"].remove(seer)
                        var.ROLES["doomsayer"].add(seer)
                        pm(cli, seer, ("You feel something rushing into you and taking control over your mind and body. It causes you to rapidly " +
                                       "start transforming into a werewolf, and you realize your vision powers can now be used to inflict malady " +
                                       "on the unwary. You are now a \u0002doomsayer\u0002."))
                        relay_wolfchat_command(cli, seer, "\u0002{0}\u0002 is now a \u0002doomsayer\u0002.", var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)
                    for harlot in harlots:
                        var.ROLES["harlot"].remove(harlot)
                        var.ROLES["succubus"].add(harlot)
                        pm(cli, harlot, ("You feel something rushing into you and taking control over your mind and body. You are now a " +
                                         "\u0002succubus\u0002. Your job is to entrance the village, bringing them all under your absolute " +
                                         "control."))
                    for cultist in cultists:
                        var.ROLES["cultist"].remove(cultist)
                        var.ROLES["demoniac"].add(cultist)
                        pm(cli, cultist, ("You feel something rushing into you and taking control over your mind and body, showing you your new purpose in life. " +
                                          "There are far greater evils than the wolves lurking in the shadows, and by sacrificing all of the wolves, you can " +
                                          "unleash those evils upon the world. You are now a \u0002demoniac\u0002."))
                    # NOTE: chk_win is called by del_player, don't need to call it here even though this has a chance of ending game

# vim: set expandtab:sw=4:ts=4:
