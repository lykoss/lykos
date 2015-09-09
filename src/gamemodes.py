from collections import OrderedDict

import random
import math

import src.settings as var

from src import events

def game_mode(name, minp, maxp, likelihood = 0, conceal_roles = False):
    def decor(c):
        c.name = name
        var.GAME_MODES[name] = (c, minp, maxp, likelihood, conceal_roles)
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
    def __init__(self, arg=""):
        # No extra settings, just an explicit way to revert to default settings
        super().__init__(arg)

@game_mode("foolish", minp = 8, maxp = 24, likelihood = 8)
class FoolishMode(GameMode):
    """Contains the fool, be careful not to lynch them!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_INDEX =         (  8  ,  9  ,  10 , 11  , 12  , 15  , 17  , 20  , 21  , 22  , 24  )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({# village roles
              "oracle"          : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  1  ),
              "harlot"          : (  1  ,  1  ,  1  ,  1  ,  1  ,  1  ,  2  ,  2  ,  2  ,  2 ,   2  ),
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
        events.add_listener("chk_win", self.chk_win, 1)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win, 1)

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


@game_mode("classic", minp = 7, maxp = 21, likelihood = 4)
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

@game_mode("random", minp = 8, maxp = 24, likelihood = 0, conceal_roles = True)
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
        events.add_listener("role_attribution", self.role_attribution, 1)

    def teardown(self):
        events.remove_listener("role_attribution", self.role_attribution, 1)

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
        ltraitors = addroles["traitor"]
        lpipers = addroles["piper"]

        if chk_win_conditions(lpl, lwolves, lcubs, lrealwolves, lmonsters, ltraitors, lpipers, cli, end_game=False):
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
        self.ROLE_INDEX =         (   8   ,  10   ,  12   ,  15   ,  18   ,  21   )
        self.ROLE_GUIDE = reset_roles(self.ROLE_INDEX)
        self.ROLE_GUIDE.update({ # village roles
            "seer"              : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "shaman"            : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "matchmaker"        : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "hunter"            : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "augur"             : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "time lord"         : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ),
            "guardian angel"    : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # wolf roles
            "wolf"              : (   1   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "wolf cub"          : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ),
            "traitor"           : (   1   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "werecrow"          : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            "hag"               : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            # neutral roles
            "vengeful ghost"    : (   0   ,   1   ,   1   ,   1   ,   2   ,   2   ),
            "amnesiac"          : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "lycan"             : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
            # templates
            "cursed villager"   : (   2   ,   2   ,   2   ,   2   ,   2   ,   2   ),
            "assassin"          : (   0   ,   1   ,   2   ,   2   ,   2   ,   2   ),
            "gunner"            : (   0   ,   1   ,   1   ,   1   ,   1   ,   1   ),
            "sharpshooter"      : (   0   ,   0   ,   0   ,   0   ,   0   ,   1   ),
            "bureaucrat"        : (   0   ,   0   ,   1   ,   1   ,   1   ,   1   ),
            "mayor"             : (   0   ,   0   ,   0   ,   1   ,   1   ,   1   ),
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
        events.add_listener("chk_win", self.chk_win, 1)

    def teardown(self):
        events.remove_listener("chk_win", self.chk_win, 1)

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
