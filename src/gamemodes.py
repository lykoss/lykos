import random
import math
import threading
import copy
import functools
from datetime import datetime
from collections import defaultdict, OrderedDict, Counter

import botconfig
import src.settings as var
from src.utilities import *
from src.messages import messages
from src.functions import get_players, get_all_players, get_main_role, change_role
from src.decorators import handle_error, command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.status import add_dying
from src import events, channels, users, cats
from src.cats import All, Wolf, Cursed, Innocent, Killer, Village, Neutral, Hidden, Team_Switcher, Win_Stealer, Spy, Nocturnal

class InvalidModeException(Exception): pass

def game_mode(name, minp, maxp, likelihood=0):
    def decor(c):
        c.name = name
        var.GAME_MODES[name] = (c, minp, maxp, likelihood)
        return c
    return decor

class GameMode:
    def __init__(self, arg=""):
        # Default values for the role sets and secondary roles restrictions
        self.ROLE_SETS = {
            "gunner/sharpshooter": {"gunner": 4, "sharpshooter": 1},
        }
        self.SECONDARY_ROLES = {
            "cursed villager"   : All - Cursed - Wolf - Innocent - {"seer", "oracle"},
            "gunner"            : Village + Neutral + Hidden - Innocent - Team_Switcher,
            "sharpshooter"      : Village + Neutral + Hidden - Innocent - Team_Switcher,
            "mayor"             : All - Innocent - Win_Stealer,
            "assassin"          : All - Nocturnal + Killer - Wolf - Innocent - Spy - Team_Switcher - {"traitor"}, # inaccurate, but best bet for now
            "blessed villager"  : ["villager"],
        }
        self.DEFAULT_TOTEM_CHANCES = self.TOTEM_CHANCES = {}

        # Support all shamans and totems
        # Listeners should add their custom totems with non-zero chances, and custom roles in evt.data["shaman_roles"]
        # Totems (both the default and custom ones) get filled with every shaman role at a chance of 0
        # Add totems with a priority of 1 and shamans with a priority of 3
        # Listeners at priority 5 can make use of this information freely
        evt = events.Event("default_totems", {"shaman_roles": set()})
        evt.dispatch(self.TOTEM_CHANCES)

        shamans = evt.data["shaman_roles"]
        for chances in self.TOTEM_CHANCES.values():
            if chances.keys() != shamans:
                for role in shamans:
                    if role not in chances:
                        chances[role] = 0 # default to 0 for new totems/shamans

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

    def startup(self):
        pass

    def teardown(self):
        pass

    def set_default_totem_chances(self):
        if self.TOTEM_CHANCES is self.DEFAULT_TOTEM_CHANCES:
            return # nothing more we can do
        for totem, chances in self.TOTEM_CHANCES.items():
            if totem not in self.DEFAULT_TOTEM_CHANCES or self.DEFAULT_TOTEM_CHANCES[totem].keys() == chances.keys():
                continue
            for role, value in self.DEFAULT_TOTEM_CHANCES[totem].items():
                if role not in chances:
                    chances[role] = value

    # Here so any game mode can use it
    def lovers_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        winner = evt.data["winner"]
        if winner in Win_Stealer:
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
        self.ROLE_GUIDE = {1: []}
        arg = arg.replace("=", ":").replace(";", ",")

        pairs = [arg]
        while pairs:
            pair, *pairs = pairs[0].split(",", 1)
            change = pair.replace(":", " ").strip().rsplit(None, 1)
            if len(change) != 2:
                raise InvalidModeException(messages["invalid_mode_roles"].format(arg))
            role, num = change
            role = role.lower()
            num = num.lower()
            try:
                if role in var.DISABLED_ROLES:
                    raise InvalidModeException(messages["role_disabled"].format(role))
                elif role in cats.ROLES:
                    self.ROLE_GUIDE[1].extend((role,) * int(num))
                elif "/" in role:
                    choose = role.split("/")
                    for c in choose:
                        if c not in cats.ROLES:
                            raise InvalidModeException(messages["specific_invalid_role"].format(c))
                        elif c in var.DISABLED_ROLES:
                            raise InvalidModeException(messages["role_disabled"].format(c))
                    self.ROLE_SETS[role] = Counter(choose)
                    self.ROLE_GUIDE[1].extend((role,) * int(num))
                elif role == "default" and num in cats.ROLES:
                    self.DEFAULT_ROLE = num
                elif role.lower() == "hidden" and num in ("villager", "cultist"):
                    self.HIDDEN_ROLE = num
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
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            4:  ["wolf", "seer"],
            6:  ["cursed villager"],
            7:  ["cultist", "shaman"],
            8:  ["harlot", "traitor", "-cultist"],
            9:  ["crazed shaman"],
            10: ["wolf cub", "gunner/sharpshooter"],
            11: ["matchmaker"],
            12: ["werecrow", "detective"],
            13: ["assassin"],
            15: ["wolf(2)", "hunter"],
            16: ["monster"],
            18: ["bodyguard"],
            20: ["sorcerer", "augur", "cursed villager(2)"],
            21: ["wolf(3)", "gunner/sharpshooter(2)"],
            23: ["amnesiac", "mayor"],
            24: ["hag"],
        }

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
        self.ROLE_GUIDE = {
            4: ["seer"],
            6: ["cursed villager"],
            7: ["shaman"],
            8: ["harlot"],
            9: ["crazed shaman"],
        }

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
        from src.roles.helper import wolves
        wolves.KILLS[users.Bot] = [tgt]

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
        self.ROLE_GUIDE = {
            8:  ["wolf", "traitor", "oracle", "harlot", "fool", "cursed villager"],
            9:  ["hunter"],
            10: ["wolf(2)"],
            11: ["shaman", "clone"],
            12: ["wolf cub", "gunner/sharpshooter"],
            15: ["sorcerer", "augur", "mayor"],
            17: ["wolf(3)", "harlot(2)"],
            20: ["bodyguard"],
            21: ["traitor(2)"],
            22: ["gunner/sharpshooter(2)"],
            24: ["wolf(4)"],
        }

@game_mode("mad", minp=7, maxp=22, likelihood=5)
class MadMode(GameMode):
    """This game mode has mad scientist and many things that may kill you."""
    def __init__(self, arg=""):
        super().__init__(arg)
        # gunner and sharpshooter always get 1 bullet
        self.SHOTS_MULTIPLIER = 0.0001
        self.SHARPSHOOTER_MULTIPLIER = 0.0001
        self.ROLE_GUIDE = {
            7:  ["seer", "mad scientist", "wolf", "cultist"],
            8:  ["traitor", "-cultist", "gunner/sharpshooter"],
            10: ["werecrow", "cursed villager"],
            12: ["detective", "cultist"],
            14: ["wolf(2)", "vengeful ghost"],
            15: ["harlot"],
            17: ["wolf cub", "jester", "assassin"],
            18: ["hunter"],
            20: ["wolf cub(2)"],
        }

@game_mode("evilvillage", minp=6, maxp=18, likelihood=5)
class EvilVillageMode(GameMode):
    """Majority of the village is wolf aligned, safes must secretly try to kill the wolves."""
    def __init__(self, arg=""):
        self.ABSTAIN_ENABLED = False
        super().__init__(arg)
        self.DEFAULT_ROLE = "cultist"
        self.HIDDEN_ROLE = "cultist"
        self.ROLE_GUIDE = {
            6:  ["wolf", "hunter"],
            8:  ["seer"],
            10: ["minion", "guardian angel", "fool"],
            12: ["shaman"],
            15: ["wolf(2)", "hunter(2)"],
        }

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
        self.ROLE_GUIDE = {
            4:  ["wolf", "seer"],
            6:  ["cursed villager"],
            8:  ["traitor", "harlot", "village drunk"],
            10: ["wolf(2)", "gunner"],
            12: ["werecrow", "detective"],
            15: ["wolf(3)"],
            17: ["bodyguard"],
            18: ["cursed villager(2)"],
            20: ["wolf(4)"],
        }

@game_mode("rapidfire", minp=6, maxp=24, likelihood=0)
class RapidFireMode(GameMode):
    """Many roles that lead to multiple chain deaths."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0
        self.ROLE_GUIDE = {
            6:  ["wolf", "seer", "mad scientist", "cursed villager"],
            8:  ["wolf cub", "hunter", "assassin"],
            10: ["traitor", "matchmaker", "time lord", "sharpshooter"],
            12: ["wolf(2)", "vengeful ghost"],
            15: ["wolf cub(2)", "augur", "amnesiac", "assassin(2)"],
            18: ["wolf(3)", "hunter(2)", "mad scientist(2)", "time lord(2)", "cursed villager(2)"],
            22: ["wolf(4)", "matchmaker(2)", "vengeful ghost(2)"],
        }

    def startup(self):
        events.add_listener("chk_win", self.all_dead_chk_win)

    def teardown(self):
        events.remove_listener("chk_win", self.all_dead_chk_win)

@game_mode("drunkfire", minp=8, maxp=17, likelihood=0)
class DrunkFireMode(GameMode):
    """Most players get a gun, quickly shoot all the wolves!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.DAY_TIME_LIMIT = 480
        self.DAY_TIME_WARN = 360
        self.SHORT_DAY_LIMIT = 240
        self.SHORT_DAY_WARN = 180
        self.NIGHT_TIME_LIMIT = 60
        self.NIGHT_TIME_WARN = 40     #    HIT  MISS  HEADSHOT
        self.GUN_CHANCES              = (  3/7 , 3/7 , 4/5   )
        self.WOLF_GUN_CHANCES         = (  4/7 , 3/7 , 1     )
        self.ROLE_GUIDE = {
            8:  ["wolf", "traitor", "seer", "village drunk", "village drunk(2)", "cursed villager", "gunner", "gunner(2)", "gunner(3)", "sharpshooter", "sharpshooter(2)"],
            10: ["wolf(2)", "village drunk(3)", "gunner(4)"],
            12: ["hag", "village drunk(4)", "crazed shaman", "sharpshooter(3)"],
            14: ["wolf(3)", "seer(2)", "gunner(5)", "assassin"],
            16: ["traitor(2)", "village drunk(5)", "sharpshooter(4)"],
        }

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
        self.ROLE_GUIDE = {
            4:  ["wolf", "seer"],
            6:  ["cursed villager"],
            8:  ["wolf mystic", "mystic"],
            10: ["traitor", "hunter"],
            12: ["wolf(2)", "guardian angel"],
            15: ["werecrow", "detective", "clone"],
            17: ["amnesiac", "lycan", "cursed villager(2)"],
            19: ["wolf(3)"],
        }

@game_mode("lycan", minp=7, maxp=21, likelihood=5)
class LycanMode(GameMode):
    """Many lycans will turn into wolves. Hunt them down before the wolves overpower the village."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            7:  ["wolf", "seer", "hunter", "lycan", "cursed villager"],
            8:  ["traitor"],
            9:  ["clone"],
            10: ["wolf shaman", "hunter(2)", "lycan(2)"],
            11: ["bodyguard", "mayor"],
            12: ["lycan(3)", "cursed villager(2)"],
            15: ["matchmaker", "lycan(4)"],
            17: ["clone(2)", "gunner/sharpshooter"],
            19: ["seer(2)"],
            20: ["lycan(5)"],
        }

@game_mode("valentines", minp=8, maxp=24, likelihood=0)
class MatchmakerMode(GameMode):
    """Love is in the air!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.NIGHT_TIME_LIMIT = 150
        self.NIGHT_TIME_WARN = 105
        self.DEFAULT_ROLE = "matchmaker"
        self.ROLE_GUIDE = {
            8:  ["wolf", "wolf(2)"],
            12: ["monster"],
            13: ["wolf(3)"],
            17: ["wolf(4)"],
            18: ["mad scientist"],
            21: ["wolf(5)"],
            24: ["wolf(6)"],
        }

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
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        for role in self.SECONDARY_ROLES:
            self.SECONDARY_ROLES[role] = All

        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 8, "wolf shaman": 1},
            "protection"    : {"shaman": 6, "wolf shaman": 6},
            "silence"       : {"shaman": 4, "wolf shaman": 3},
            "revealing"     : {"shaman": 2, "wolf shaman": 5},
            "desperation"   : {"shaman": 4, "wolf shaman": 7},
            "impatience"    : {"shaman": 7, "wolf shaman": 2},
            "pacifism"      : {"shaman": 7, "wolf shaman": 2},
            "influence"     : {"shaman": 7, "wolf shaman": 2},
            "narcolepsy"    : {"shaman": 4, "wolf shaman": 3},
            "exchange"      : {"shaman": 1, "wolf shaman": 1},
            "lycanthropy"   : {"shaman": 1, "wolf shaman": 3},
            "luck"          : {"shaman": 6, "wolf shaman": 7},
            "pestilence"    : {"shaman": 3, "wolf shaman": 1},
            "retribution"   : {"shaman": 5, "wolf shaman": 6},
            "misdirection"  : {"shaman": 6, "wolf shaman": 4},
            "deceit"        : {"shaman": 3, "wolf shaman": 6},
        }

        self.ROLE_SETS["gunner/sharpshooter"] = {"gunner": 8, "sharpshooter": 4}

        self.set_default_totem_chances()

    def startup(self):
        events.add_listener("role_attribution", self.role_attribution)
        events.add_listener("chk_win", self.lovers_chk_win)

    def teardown(self):
        events.remove_listener("role_attribution", self.role_attribution)
        events.remove_listener("chk_win", self.lovers_chk_win)

    def role_attribution(self, evt, var, chk_win_conditions, villagers):
        lpl = len(villagers) - 1
        addroles = evt.data["addroles"]
        addroles[random.choice(list(Wolf & Killer))] += 1 # make sure there's at least one wolf role
        roles = list(All - self.SECONDARY_ROLES.keys() - {"villager", "cultist", "amnesiac"})
        while lpl:
            addroles[random.choice(roles)] += 1
            lpl -= 1

        addroles["gunner/sharpshooter"] = random.randrange(int(len(villagers) ** 1.2 / 4))
        addroles["assassin"] = random.randrange(max(int(len(villagers) ** 1.2 / 8), 1))

        rolemap = defaultdict(set)
        mainroles = {}
        i = 0
        for role, count in addroles.items():
            if count > 0:
                for j in range(count):
                    u = users.FakeUser.from_nick(str(i + j))
                    rolemap[role].add(u.nick)
                    if role not in self.SECONDARY_ROLES:
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
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 4},
            "protection"    : {"shaman": 8},
            "silence"       : {"shaman": 2},
            "revealing"     : {"shaman": 0},
            "desperation"   : {"shaman": 1},
            "impatience"    : {"shaman": 0},
            "pacifism"      : {"shaman": 0},
            "influence"     : {"shaman": 0},
            "narcolepsy"    : {"shaman": 0},
            "exchange"      : {"shaman": 0},
            "lycanthropy"   : {"shaman": 0},
            "luck"          : {"shaman": 0},
            "pestilence"    : {"shaman": 1},
            "retribution"   : {"shaman": 4},
            "misdirection"  : {"shaman": 0},
            "deceit"        : {"shaman": 0},
        }

        self.set_default_totem_chances()

        self.ROLE_GUIDE = {
            8:  ["wolf", "traitor", "seer", "shaman", "cursed villager", "cursed villager(2)"],
            10: ["wolf(2)", "matchmaker", "vengeful ghost", "gunner", "assassin"],
            12: ["hag", "guardian angel", "amnesiac"],
            13: ["assassin(2)"],
            14: ["turncoat"],
            15: ["werecrow", "augur", "mayor"],
            17: ["wolf(3)", "hunter"],
            18: ["vengeful ghost(2)"],
            21: ["wolf cub", "time lord"],
        }

@game_mode("alpha", minp=10, maxp=24, likelihood=5)
class AlphaMode(GameMode):
    """Features the alpha wolf who can turn other people into wolves, be careful whom you trust!"""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            10: ["alpha wolf", "traitor", "oracle", "harlot", "doctor", "amnesiac", "lycan", "lycan(2)", "cursed villager"],
            12: ["werecrow", "guardian angel"],
            13: ["matchmaker", "mayor"],
            14: ["wolf"],
            16: ["crazed shaman", "lycan(3)", "cursed villager(2)"],
            17: ["augur"],
            18: ["wolf(2)"],
            19: ["assassin"],
            20: ["clone", "lycan(4)"],
            21: ["vigilante"],
            22: ["wolf(3)", "cursed villager(3)"],
            24: ["wolf(4)", "guardian angel(2)"],
        }

# original idea by Rossweisse, implemented by Vgr with help from woffle and jacob1
@game_mode("guardian", minp=8, maxp=16, likelihood=1)
class GuardianMode(GameMode):
    """Game mode full of guardian angels, wolves need to pick them apart!"""
    def __init__(self, arg=""):
        self.LIMIT_ABSTAIN = False
        super().__init__(arg)
        self.ROLE_GUIDE = {
            8:  ["wolf", "werekitten", "seer", "guardian angel", "village drunk", "cursed villager"],
            10: ["werecrow", "shaman"],
            12: ["alpha wolf", "guardian angel(2)", "cursed villager(2)"],
            13: ["jester", "gunner"],
            15: ["wolf(2)", "bodyguard"],
        }
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 4},
            "protection"    : {"shaman": 8},
            "silence"       : {"shaman": 2},
            "revealing"     : {"shaman": 0},
            "desperation"   : {"shaman": 0},
            "impatience"    : {"shaman": 0},
            "pacifism"      : {"shaman": 0},
            "influence"     : {"shaman": 0},
            "narcolepsy"    : {"shaman": 0},
            "exchange"      : {"shaman": 0},
            "lycanthropy"   : {"shaman": 0},
            "luck"          : {"shaman": 3},
            "pestilence"    : {"shaman": 0},
            "retribution"   : {"shaman": 6},
            "misdirection"  : {"shaman": 4},
            "deceit"        : {"shaman": 0},
        }

        self.set_default_totem_chances()

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
        self.ROLE_GUIDE = {
            6:  ["wolf", "seer", "piper", "cursed villager"],
            8:  ["traitor", "harlot"],
            10: ["werekitten", "shaman", "gunner/sharpshooter"],
            11: ["vengeful ghost"],
            12: ["warlock", "detective"],
            14: ["bodyguard", "mayor"],
            16: ["wolf(2)", "assassin"],
            18: ["bodyguard(2)"],
            19: ["sorcerer"],
            22: ["wolf(3)", "shaman(2)"],
            24: ["gunner/sharpshooter(2)"],
        }
        self.ROLE_SETS = {
            "gunner/sharpshooter": {"gunner": 8, "sharpshooter": 2},
        }

@game_mode("sleepy", minp=10, maxp=24, likelihood=1)
class SleepyMode(GameMode):
    """A small village has become the playing ground for all sorts of supernatural beings."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_GUIDE = {
            10: ["wolf", "werecrow", "traitor", "cultist", "seer", "prophet", "priest", "dullahan", "cursed villager", "blessed villager"],
            12: ["wolf(2)", "vigilante"],
            15: ["wolf(3)", "detective", "vengeful ghost"],
            18: ["wolf(4)", "harlot", "monster"],
            21: ["wolf(5)", "village drunk", "monster(2)", "gunner"],
        }
        # Make sure priest is always prophet AND blessed, and that drunk is always gunner
        self.SECONDARY_ROLES["blessed villager"] = ["priest"]
        self.SECONDARY_ROLES["prophet"] = ["priest"]
        self.SECONDARY_ROLES["gunner"] = ["village drunk"]
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
            add_dying(var, self.having_nightmare[0], "bot", "night_kill")
            self.having_nightmare[0].send(messages["sleepy_nightmare_death"])
            del self.having_nightmare[0]

    def happy_fun_times(self, evt, var, player, all_roles, death_triggers):
        if death_triggers:
            if evt.params.main_role == "priest":
                turn_chance = 3/4
                seers = [p for p in get_players(("seer",)) if random.random() < turn_chance]
                harlots = [p for p in get_players(("harlot",)) if random.random() < turn_chance]
                cultists = [p for p in get_players(("cultist",)) if random.random() < turn_chance]
                channels.Main.send(messages["sleepy_priest_death"])
                for seer in seers:
                    change_role(var, seer, "seer", "doomsayer", message="sleepy_doomsayer_turn")
                for harlot in harlots:
                    change_role(var, harlot, "harlot", "succubus", message="sleepy_succubus_turn")
                for cultist in cultists:
                    change_role(var, cultist, "cultist", "demoniac", message="sleepy_demoniac_turn")

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
        self.MAD_SCIENTIST_SKIPS_DEAD_PLAYERS = 0 # always make it happen
        self.ALWAYS_PM_ROLE = True
        # clone and wild child are pointless in this mode
        # monster and demoniac are nearly impossible to counter and don't add any interesting gameplay
        # succubus keeps around entranced people, who are then unable to win even if there are later no succubi (not very fun)
        self.roles = All - Team_Switcher - Win_Stealer + {"fool", "lycan", "turncoat"} - self.SECONDARY_ROLES.keys()

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

    def on_del_player(self, evt, var, player, all_roles, death_triggers):
        if player.is_fake:
            return

        if player.account is not None:
            self.DEAD_ACCOUNTS.add(player.lower().account)

        if not var.ACCOUNTS_ONLY:
            self.DEAD_HOSTS.add(player.lower().host)

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
        role = random.choice(list(self.roles))
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
        evt = events.Event("new_role", {"messages": [], "role": role, "in_wolfchat": False}, inherit_from=None)
        # Use "player" as old role, to force wolf event to send "new wolf" messages
        evt.dispatch(var, wrapper.source, "player")
        role = evt.data["role"]

        var.ROLES[role].add(wrapper.source)
        var.ORIGINAL_ROLES[role].add(wrapper.source)
        var.FINAL_ROLES[wrapper.source.nick] = role # FIXME: once FINAL_ROLES stores users
        var.MAIN_ROLES[wrapper.source] = role
        var.ORIGINAL_MAIN_ROLES[wrapper.source] = role
        var.LAST_SAID_TIME[wrapper.source.nick] = datetime.now()
        if wrapper.source.nick in var.USERS:
            var.PLAYERS[wrapper.source.nick] = var.USERS[wrapper.source.nick]

        for message in evt.data["messages"]:
            wrapper.pm(message)

        from src.decorators import COMMANDS
        COMMANDS["myrole"][0].caller(wrapper.source.client, wrapper.source.nick, wrapper.target.name, "") # FIXME: New/old API

    def role_attribution(self, evt, var, chk_win_conditions, villagers):
        self.chk_win_conditions = chk_win_conditions
        evt.data["addroles"].update(self._role_attribution(var, villagers, True))
        evt.prevent_default = True

    def transition_night_begin(self, evt, var):
        # don't do this n1
        if var.NIGHT_COUNT == 1:
            return
        villagers = get_players()
        lpl = len(villagers)
        addroles = self._role_attribution(var, villagers, False)

        # shameless copy/paste of regular role attribution
        for rs in var.ROLES.values():
            rs.clear()
        # prevent wolf.py from sending messages about a new wolf to soon-to-be former wolves
        # (note that None doesn't work, so "player" works fine)
        for player in var.MAIN_ROLES:
            var.MAIN_ROLES[player] = "player"
        new_evt = events.Event("new_role", {"messages": [], "role": None, "in_wolfchat": False}, inherit_from=None)
        for role, count in addroles.items():
            selected = random.sample(villagers, count)
            for x in selected:
                villagers.remove(x)
                new_evt.data["role"] = role
                new_evt.dispatch(var, x, var.ORIGINAL_MAIN_ROLES[x])
                var.ROLES[new_evt.data["role"]].add(x)

        # for end of game stats to show what everyone ended up as on game end
        for role, pl in var.ROLES.items():
            if role in self.SECONDARY_ROLES:
                continue
            for p in pl:
                # discard them from all non-secondary roles, we don't have a reliable
                # means of tracking their previous role (due to traitor turning, exchange
                # totem, etc.), so we need to iterate through everything.
                for r in var.ORIGINAL_ROLES.keys():
                    if r in self.SECONDARY_ROLES:
                        continue
                    var.ORIGINAL_ROLES[r].discard(p)
                var.ORIGINAL_ROLES[role].add(p)
                var.FINAL_ROLES[p.nick] = role # FIXME
                var.MAIN_ROLES[p] = role
                var.ORIGINAL_MAIN_ROLES[p] = role

    def _role_attribution(self, var, villagers, do_templates):
        lpl = len(villagers) - 1
        addroles = Counter()
        addroles[random.choice(list(Wolf & Killer))] += 1 # make sure there's at least one wolf role
        roles = list(self.roles)
        while lpl:
            addroles[random.choice(roles)] += 1
            lpl -= 1

        if do_templates:
            addroles["gunner/sharpshooter"] = random.randrange(6)
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
                    if role not in self.SECONDARY_ROLES:
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

        # Actual shaman chances are handled in restore_totem_chances (n1 is a guaranteed death totem)
        self.TOTEM_CHANCES = {
            "death"         : {"shaman": 1, "wolf shaman": 0},
            "protection"    : {"shaman": 0, "wolf shaman": 1},
            "silence"       : {"shaman": 0, "wolf shaman": 0},
            "revealing"     : {"shaman": 0, "wolf shaman": 0},
            "desperation"   : {"shaman": 0, "wolf shaman": 0},
            "impatience"    : {"shaman": 0, "wolf shaman": 0},
            "pacifism"      : {"shaman": 0, "wolf shaman": 0},
            "influence"     : {"shaman": 0, "wolf shaman": 0},
            "narcolepsy"    : {"shaman": 0, "wolf shaman": 0},
            "exchange"      : {"shaman": 0, "wolf shaman": 0},
            "lycanthropy"   : {"shaman": 0, "wolf shaman": 0},
            "luck"          : {"shaman": 0, "wolf shaman": 0},
            "pestilence"    : {"shaman": 0, "wolf shaman": 0},
            "retribution"   : {"shaman": 0, "wolf shaman": 0},
            "misdirection"  : {"shaman": 0, "wolf shaman": 1},
            "deceit"        : {"shaman": 0, "wolf shaman": 0},
        }

        self.set_default_totem_chances()

        self.ROLE_GUIDE = {
            5:  ["wolf", "minion", "investigator"],
            6:  ["guardian angel"],
            7:  ["jester"],
            8:  ["shaman"],
            9:  ["doomsayer", "-minion"],
            10: ["vengeful ghost", "assassin"],
            11: ["wolf(2)"],
            12: ["priest"],
            13: ["wolf shaman"],
            14: ["amnesiac"],
            15: ["succubus"],
        }
        self.recursion_guard = False

    def startup(self):
        events.add_listener("chk_decision", self.chk_decision)
        events.add_listener("daylight_warning", self.daylight_warning)
        events.add_listener("transition_day_begin", self.restore_totem_chances)

    def teardown(self):
        events.remove_listener("chk_decision", self.chk_decision)
        events.remove_listener("daylight_warning", self.daylight_warning)
        events.remove_listener("transition_day_begin", self.restore_totem_chances)

    def restore_totem_chances(self, evt, var):
        if var.NIGHT_COUNT == 1: # don't fire unnecessarily every day
            self.TOTEM_CHANCES["pestilence"]["shaman"] = 1

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

# vim: set sw=4 expandtab:
